import json
from datetime import datetime
import anthropic
import pandas as pd
import sqlite3
import streamlit as st
from finapp.config import DB_PATH
from finapp.db import get_uncategorized_merchants, bulk_set_categories, get_state, get_goals, get_savings_accounts, get_main_account, get_bank_accounts
from finapp.banking.fetcher import get_account_balance
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


# --- Tool definitions for Claude ---

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
    }
]

def _build_system_prompt() -> str:
    user_name = st.secrets.get("app", {}).get("user_name", "the user")
    savings_goal = st.secrets.get("app", {}).get("savings_goal", "")
    savings_goal_line = f"- The user's savings goal: {savings_goal}. Always factor this into allocation advice" if savings_goal else ""
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
- Provide wealth allocation analysis and financial advice using get_wealth_snapshot

Guidelines:
- Always use € for amounts
- Be concise and specific — give numbers, not vague advice
- For wealth/investment questions: always call get_wealth_snapshot first
- For spending questions: use get_spending_summary first for an overview
- When giving investment advice: consider emergency fund needs (3-6 months expenses), liquidity, and risk profile
{savings_goal_line}
- The Flexible Cash Fund is liquid but low-yield — flag if the balance is excessive vs monthly expenses
- Brokerage is for long-term wealth building — ETFs preferred over individual stocks for diversification
- When categorizing, use: Groceries, Dining, Transport, Shopping, Vinted, Subscriptions, Health, Entertainment, Travel, Rent, Investments, Joint Account, Other
- Never expose raw account UUIDs in responses
- Today's date is {datetime.now().strftime("%Y-%m-%d")}"""

SYSTEM_PROMPT = _build_system_prompt()


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


def _categorize_batch(client, merchants: list) -> dict:
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""Categorize each merchant name into exactly one of these categories:
Groceries, Dining, Transport, Shopping, Subscriptions, Health, Entertainment, Travel, Other

Merchants:
{json.dumps(merchants, indent=2)}

Respond with a single JSON object mapping each merchant name exactly as given to its category.
Output only the JSON, no explanation."""
        }]
    )
    text = next(b.text for b in response.content if b.type == "text")
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def auto_categorize(api_key: str) -> int:
    """
    Categorize all uncategorized debit transactions, batching merchants to avoid
    truncated JSON responses when there are many unique merchants.
    Returns the number of merchants categorized.
    """
    merchants = get_uncategorized_merchants()
    if not merchants:
        return 0

    client = anthropic.Anthropic(api_key=api_key)
    batch_size = 50
    mapping = {}
    for i in range(0, len(merchants), batch_size):
        batch = merchants[i:i + batch_size]
        mapping.update(_categorize_batch(client, batch))

    bulk_set_categories(mapping)
    return len(mapping)


def run_agent(messages: list, api_key: str) -> tuple[str, list]:
    client = anthropic.Anthropic(api_key=api_key)

    while True:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if b.type == "text"), "")
            return text, messages

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if block.name == "query_transactions":
                    result = query_transactions(**block.input)
                elif block.name == "get_spending_summary":
                    result = get_spending_summary(**block.input)
                elif block.name == "get_budget_status":
                    result = get_budget_status()
                elif block.name == "get_wealth_snapshot":
                    result = get_wealth_snapshot()
                elif block.name == "set_category":
                    result = set_category(**block.input)
                else:
                    result = {"error": f"Unknown tool: {block.name}"}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str)
                })

            messages.append({"role": "user", "content": tool_results})
