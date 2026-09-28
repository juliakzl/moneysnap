import json
from datetime import datetime
import pandas as pd
import sqlite3
import streamlit as st
from finapp.config import DB_PATH
from finapp.db import get_uncategorized_merchants, bulk_set_categories, get_state, get_goals, get_savings_accounts, get_main_account, get_bank_accounts
from finapp.banking.fetcher import get_account_balance
from finapp.llm import LLMConfig, complete, complete_text
from finapp.memory import load_memory, save_memory, scan_recent_activity
try:
    from finapp.rules import RULES
except ImportError:
    RULES = []


def _get_personal_id() -> str | None:
    return get_main_account()


def _get_joint_eur_id() -> str | None:
    accs = get_bank_accounts()
    if accs.empty:
        return None
    joint = accs[(accs.get("is_joint", 0) == 1) & (accs.get("currency", "") == "EUR")]
    if joint.empty:
        joint = accs[accs.get("is_joint", 0) == 1]
    return joint.iloc[0]["account_id"] if not joint.empty else None


def get_conn():
    return sqlite3.connect(DB_PATH)


# --- Tool implementations ---

def query_transactions(date_from=None, date_to=None, merchant=None,
                       category=None, tx_type=None, limit=50):
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    if merchant:
        query += " AND merchant LIKE ?"
        params.append(f"%{merchant}%")
    if category:
        query += " AND category = ?"
        params.append(category)
    if tx_type:
        query += " AND type = ?"
        params.append(tx_type)
    query += " ORDER BY date DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        df = pd.read_sql(query, conn, params=params)

    return df.to_dict(orient="records")


def get_spending_summary(date_from=None, date_to=None):
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)

    with get_conn() as conn:
        df = pd.read_sql(query, conn, params=params)

    if df.empty:
        return {"error": "No transactions found for this period"}

    debits = df[df["type"] == "debit"].copy()
    credits = df[df["type"] == "credit"].copy()
    debits["amount_abs"] = debits["amount"].abs()

    total_in = credits["amount"].sum()
    total_out = debits["amount_abs"].sum()
    savings_rate = ((total_in - total_out) / total_in * 100) if total_in > 0 else 0

    top_merchants = (
        debits.groupby("merchant")["amount_abs"]
        .sum().sort_values(ascending=False).head(10)
        .reset_index().to_dict(orient="records")
    )

    by_category = []
    if debits["category"].str.strip().any():
        by_category = (
            debits[debits["category"] != ""]
            .groupby("category")["amount_abs"]
            .sum().sort_values(ascending=False)
            .reset_index().to_dict(orient="records")
        )

    return {
        "period": {"from": date_from, "to": date_to},
        "total_income_eur": round(total_in, 2),
        "total_expenses_eur": round(total_out, 2),
        "savings_rate_pct": round(savings_rate, 1),
        "transaction_count": len(df),
        "top_merchants": top_merchants,
        "by_category": by_category,
    }


def get_budget_status():
    current_month = datetime.now().strftime("%Y-%m")

    with get_conn() as conn:
        budgets = pd.read_sql("SELECT * FROM budgets", conn)
        txs = pd.read_sql(
            "SELECT * FROM transactions WHERE type='debit' AND date LIKE ?",
            conn, params=[f"{current_month}%"]
        )

    if budgets.empty:
        return {"message": "No budgets set yet."}

    txs["amount_abs"] = txs["amount"].abs()
    spending = txs.groupby("merchant")["amount_abs"].sum().reset_index()
    spending.columns = ["category", "spent"]
    merged = budgets.merge(spending, on="category", how="left").fillna(0)
    merged["remaining_eur"] = (merged["monthly_limit"] - merged["spent"]).round(2)
    merged["pct_used"] = (merged["spent"] / merged["monthly_limit"] * 100).round(1)

    return {
        "month": current_month,
        "budgets": merged.to_dict(orient="records")
    }


def get_wealth_snapshot():
    """Return current balances, allocation, and savings context."""
    bal_personal = get_account_balance(_get_personal_id()) if _get_personal_id() else None
    bal_joint    = get_account_balance(_get_joint_eur_id()) if _get_joint_eur_id() else None

    savings_df    = get_savings_accounts()
    savings_total = savings_df["balance"].sum() if not savings_df.empty else 0.0
    total = (bal_personal or 0) + (bal_joint or 0) + savings_total

    def pct(val):
        return round(val / total * 100, 1) if total else 0

    # Average monthly savings over last 3 months
    _personal_id = _get_personal_id()
    with get_conn() as conn:
        df = pd.read_sql("""
            SELECT date, amount, type FROM transactions
            WHERE date >= date('now', '-3 months')
              AND account_id = ?
        """, conn, params=[_personal_id]) if _personal_id else pd.DataFrame()

    avg_monthly_savings = 0
    if not df.empty:
        df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
        monthly = df.groupby(["month", "type"])["amount"].apply(
            lambda x: x.abs().sum()
        ).unstack(fill_value=0)
        if "credit" in monthly and "debit" in monthly:
            avg_monthly_savings = round(
                (monthly["credit"] - monthly["debit"]).mean(), 2
            )

    with get_conn() as conn:
        exp_df = pd.read_sql("""
            SELECT amount FROM transactions
            WHERE type='debit' AND date >= date('now', '-3 months')
              AND account_id = ?
        """, conn, params=[_personal_id]) if _personal_id else pd.DataFrame()
    if not exp_df.empty:
        mean_val = exp_df["amount"].abs().mean()
        avg_monthly_expenses = round(mean_val * 30, 2) if pd.notna(mean_val) else None
    else:
        avg_monthly_expenses = None

    savings_accounts_list = []
    if not savings_df.empty:
        for _, acc in savings_df.iterrows():
            entry = {"name": acc["name"], "type": acc["type"], "balance_eur": round(acc["balance"], 2), "allocation_pct": pct(acc["balance"])}
            if pd.notna(acc["interest_rate"]) and acc["interest_rate"]:
                entry["interest_rate_pct"] = acc["interest_rate"]
            try:
                dm = acc["duration_months"]
                if pd.notna(dm) and dm:
                    entry["duration_months"] = int(dm)
            except (ValueError, TypeError):
                pass
            if pd.notna(acc["maturity_date"]) and acc["maturity_date"]:
                entry["maturity_date"] = acc["maturity_date"]
            savings_accounts_list.append(entry)

    return {
        "balances": {
            "personal_eur":   round(bal_personal or 0, 2),
            "joint_eur":      round(bal_joint or 0, 2),
            "savings_eur":    round(savings_total, 2),
            "total_eur":      round(total, 2),
        },
        "allocation_pct": {
            "personal": pct(bal_personal or 0),
            "joint":    pct(bal_joint or 0),
        },
        "savings_accounts": savings_accounts_list,
        "avg_monthly_savings_eur":  avg_monthly_savings,
        "avg_monthly_expenses_eur": avg_monthly_expenses,
        "goals": _get_goals_snapshot(
            current_savings=savings_total,
            avg_monthly_savings=avg_monthly_savings
        ),
        "monthly_salary_eur": float(get_state("monthly_salary") or 0),
    }


def _get_goals_snapshot(current_savings: float, avg_monthly_savings: float) -> list:
    goals_df = get_goals()
    if goals_df.empty:
        return []
    result = []
    for _, g in goals_df.iterrows():
        remaining = max(g["target_amount"] - current_savings, 0)
        months_to_go = None
        if avg_monthly_savings > 0 and remaining > 0:
            months_to_go = round(remaining / avg_monthly_savings, 1)
        result.append({
            "name": g["name"],
            "target_eur": g["target_amount"],
            "current_savings_eur": round(current_savings, 2),
            "remaining_eur": round(remaining, 2),
            "progress_pct": round(current_savings / g["target_amount"] * 100, 1),
            "months_to_goal": months_to_go,
            "notes": g["notes"],
        })
    return result


def set_category(category, merchant_name=None, transaction_id=None):
    with get_conn() as conn:
        if merchant_name:
            cursor = conn.execute(
                "UPDATE transactions SET category=? WHERE merchant LIKE ?",
                (category, f"%{merchant_name}%")
            )
            return {"updated": cursor.rowcount, "merchant": merchant_name, "category": category}
        elif transaction_id:
            cursor = conn.execute(
                "UPDATE transactions SET category=? WHERE id=?",
                (category, transaction_id)
            )
            return {"updated": cursor.rowcount, "id": transaction_id, "category": category}
        else:
            return {"error": "Provide either merchant_name or transaction_id"}


# --- Tool definitions (Anthropic schema; OpenAI and OpenRouter are converted at call time) ---

MAX_TOOL_ROUNDS = 8

TOOLS = [
    {
        "name": "query_transactions",
        "description": "Query the user's bank transactions with optional filters. Use this to look up specific transactions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                "merchant": {"type": "string", "description": "Merchant name (partial match)"},
                "category": {"type": "string", "description": "Filter by category"},
                "tx_type": {"type": "string", "enum": ["debit", "credit"], "description": "Transaction type"},
                "limit": {"type": "integer", "description": "Max results (default 50)"}
            }
        }
    },
    {
        "name": "get_spending_summary",
        "description": "Get an aggregated financial summary for a period: total income, expenses, savings rate, top merchants, and spending by category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "End date YYYY-MM-DD"}
            }
        }
    },
    {
        "name": "get_budget_status",
        "description": "Get current month spending vs budget limits.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_wealth_snapshot",
        "description": "Get a full picture of current finances: all account balances, allocation percentages, average monthly savings/expenses, and how many months of expenses the Flexible Cash covers. Use this for any question about wealth allocation, investment strategy, or financial health.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "set_category",
        "description": "Assign a category to transactions — either all transactions from a merchant (bulk) or a single transaction by ID. Use standard categories: Groceries, Dining, Transport, Shopping, Vinted, Subscriptions, Health, Entertainment, Travel, Kevin, Other.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category to assign"},
                "merchant_name": {"type": "string", "description": "Categorize all transactions from this merchant"},
                "transaction_id": {"type": "string", "description": "Categorize a single transaction by ID"}
            },
            "required": ["category"]
        }
    },
    {
        "name": "scan_recent_activity",
        "description": "Scan transactions since the last memory review and compare this month to a 3-month baseline. Returns category spikes, large new debits, unusual credits, new merchants, and recurring payments that appeared extra times. Call this at the start of a review, or when spending looks off and memory does not explain it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "since": {
                    "type": "string",
                    "description": "Optional YYYY-MM-DD. Defaults to Last reviewed in the memory file, or the start of this month."
                }
            }
        }
    },
    {
        "name": "update_memory",
        "description": "Rewrite the durable memory file. Always pass the COMPLETE updated markdown, not a fragment. Keep it short. Use this whenever you learn something that should change how future months are read.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Full markdown contents of the memory file."
                }
            },
            "required": ["content"]
        }
    }
]

REVIEW_PROMPT = (
    "Review my finances since your last memory update. "
    "Call scan_recent_activity, compare the findings to your memory file, "
    "and ask me about anything that stands out and is not already explained. "
    "Ask at most 3 questions. After I answer, update the memory file. "
    "If memory already covers everything that stands out, say so briefly "
    "and update Last reviewed to today."
)

def _build_system_prompt() -> str:
    user_name = st.secrets.get("app", {}).get("user_name", "the user")
    savings_goal = st.secrets.get("app", {}).get("savings_goal", "")
    savings_goal_line = f"- The user's savings goal: {savings_goal}. Always factor this into allocation advice" if savings_goal else ""
    memory = load_memory()
    return f"""You are a personal finance assistant for {user_name}. You have full access to their real financial data.

Account structure:
- Personal account: daily expenses — salary, rent, groceries, subscriptions
- Joint account: shared account for joint expenses
- Flexible Cash / savings: instant-access savings, low yield (~3-4% p.a.)
- Brokerage account: long-term investments — ETFs and stocks

Your capabilities:
- Query and summarize transactions
- Analyse spending patterns and trends
- Check budget status
- Categorize transactions
- Scan recent activity for things that stand out
- Maintain a durable memory file across conversations
- Provide wealth allocation analysis and financial advice using get_wealth_snapshot

Guidelines:
- Always use € for amounts
- Be concise and specific — give numbers, not vague advice
- For wealth/investment questions: always call get_wealth_snapshot first
- For spending questions: use get_spending_summary first for an overview, then read memory before interpreting the numbers
- When giving investment advice: consider emergency fund needs (3-6 months expenses), liquidity, and risk profile
{savings_goal_line}
- The Flexible Cash Fund is liquid but low-yield — flag if the balance is excessive vs monthly expenses
- Brokerage is for long-term wealth building — ETFs preferred over individual stocks for diversification
- When categorizing, use: Groceries, Dining, Transport, Shopping, Vinted, Subscriptions, Health, Entertainment, Travel, Rent, Investments, Joint Account, Other
- Never expose raw account UUIDs in responses
- Today's date is {datetime.now().strftime("%Y-%m-%d")}

## Durable memory
You keep a markdown memory file across conversations. It is your long-term picture of this person's financial life — overlapping costs, one-off trips, who people are, and what a normal month looks like. Categories describe *what* the money is; memory describes *why*.

Current memory:
---
{memory}
---

Memory rules:
- Read memory before interpreting spending. If a month looks high, check whether memory already explains it.
- When you learn something that would change how you read future months, call update_memory immediately. Do not wait to be asked.
- Always pass the complete file to update_memory. Keep it short (aim under 80 lines). Facts and names, not transaction dumps.
- Keep these sections: Current situation, Recurring / baseline, People & merchants, How to read unusual months.
- Always keep a `Last reviewed: YYYY-MM-DD` line. After a review, set it to today.
- Move stale "current situation" items out once they no longer apply.
- If something stands out and memory does not explain it, ASK. Do not invent a story.
- Ask at most 2–3 questions at a time, then write the answers back into memory."""


def apply_rules() -> int:
    """
    Apply deterministic rules with first-match-wins logic.
    Re-categorizes all debit transactions so updated rules take effect.
    Returns number of transactions updated.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, LOWER(merchant) FROM transactions WHERE type = 'debit'"
        ).fetchall()

        updates = {}
        for tx_id, merchant_lower in rows:
            for pattern, category in RULES:
                if pattern.lower() in merchant_lower:
                    updates[tx_id] = category
                    break  # first match wins

        total = 0
        for tx_id, category in updates.items():
            cursor = conn.execute(
                "UPDATE transactions SET category=? WHERE id=? AND category!=?",
                (category, tx_id, category)
            )
            total += cursor.rowcount

        # Credit transactions: label as Reimbursement if currently miscategorized
        # with a spending category, or uncategorized
        spending_categories = (
            "Groceries", "Dining", "Transport", "Shopping", "Vinted",
            "Subscriptions", "Health", "Entertainment", "Travel",
            "Rent", "Other", "Investments", "Kevin"
        )
        placeholders = ",".join("?" * len(spending_categories))
        cursor = conn.execute(
            f"""UPDATE transactions
               SET category = 'Income / Reimbursement'
               WHERE type = 'credit'
               AND (category IS NULL OR category = '' OR category IN ({placeholders}))""",
            list(spending_categories)
        )
        total += cursor.rowcount
    return total


def _tool_fns() -> dict:
    return {
        "query_transactions": query_transactions,
        "get_spending_summary": get_spending_summary,
        "get_budget_status": get_budget_status,
        "get_wealth_snapshot": get_wealth_snapshot,
        "set_category": set_category,
        "scan_recent_activity": scan_recent_activity,
        "update_memory": lambda content="": save_memory(content),
    }


def _dispatch(name: str, arguments: dict) -> dict:
    fn = _tool_fns().get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        result = fn(**arguments)
    except Exception as exc:
        return {"error": str(exc)}
    return result if isinstance(result, dict) else {"result": result}


def _parse_json_object(text: str) -> dict:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Model did not return a JSON object")
    return parsed


def _categorize_batch(cfg: LLMConfig, merchants: list) -> dict:
    text = complete_text(
        f"""Categorize each merchant name into exactly one of these categories:
Groceries, Dining, Transport, Shopping, Subscriptions, Health, Entertainment, Travel, Other

Merchants:
{json.dumps(merchants, indent=2)}

Respond with a single JSON object mapping each merchant name exactly as given to its category.
Output only the JSON, no explanation.""",
        cfg=cfg,
        model=cfg.categorize_model,
        max_tokens=4096,
    )
    return _parse_json_object(text)


def auto_categorize(cfg: LLMConfig) -> int:
    """
    Categorize all uncategorized debit transactions, batching merchants to avoid
    truncated JSON responses when there are many unique merchants.
    Returns the number of merchants categorized.
    """
    merchants = get_uncategorized_merchants()
    if not merchants:
        return 0

    batch_size = 50
    mapping = {}
    for i in range(0, len(merchants), batch_size):
        batch = merchants[i:i + batch_size]
        mapping.update(_categorize_batch(cfg, batch))

    bulk_set_categories(mapping)
    return len(mapping)


def _coerce_history(messages: list) -> list:
    """Drop legacy Anthropic content blocks so a saved chat can continue."""
    if not any(isinstance(message.get("content"), list) for message in messages):
        return messages
    cleaned = []
    for message in messages:
        content = message.get("content")
        role = message.get("role")
        if role == "assistant" and isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])
                elif getattr(block, "type", None) == "text" and getattr(block, "text", None):
                    texts.append(block.text)
            if texts:
                cleaned.append({"role": "assistant", "content": "\n".join(texts)})
        elif role in {"user", "assistant"} and isinstance(content, str):
            item = {"role": role, "content": content}
            if message.get("tool_calls"):
                item["tool_calls"] = message["tool_calls"]
            cleaned.append(item)
        elif role == "tool" and isinstance(content, str):
            cleaned.append({
                "role": "tool",
                "tool_call_id": message.get("tool_call_id"),
                "content": content,
            })
    return cleaned


def _stop_for_tool_limit(messages: list, tool_calls: list) -> tuple[str, list]:
    for call in tool_calls:
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps({"error": "Tool round limit reached"}),
        })
    note = "Stopped after too many tool calls. Ask a narrower question."
    messages.append({"role": "assistant", "content": note})
    return note, messages


def run_agent(messages: list, cfg: LLMConfig) -> tuple[str, list]:
    messages = _coerce_history(messages)
    system = _build_system_prompt()
    tool_rounds = 0

    while True:
        turn = complete(
            messages,
            cfg=cfg,
            model=cfg.model,
            system=system,
            tools=TOOLS,
            max_tokens=4096,
            thinking=cfg.provider == "anthropic",
        )
        messages.append(turn.assistant_message)
        if not turn.tool_calls:
            return turn.text, messages

        tool_rounds += 1
        if tool_rounds > MAX_TOOL_ROUNDS:
            return _stop_for_tool_limit(messages, turn.tool_calls)

        for call in turn.tool_calls:
            if call.arguments is None:
                result = {"error": "Could not parse tool arguments"}
            else:
                result = _dispatch(call.name, call.arguments)
                if call.name == "update_memory" and result.get("ok"):
                    system = _build_system_prompt()
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })
