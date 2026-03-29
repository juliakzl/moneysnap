import json
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import anthropic
import pandas as pd
import streamlit as st

from finapp.db import get_transactions, get_budgets, get_state, set_state, get_goals, save_summary, get_savings_accounts, get_main_account, get_bank_accounts
from finapp.banking.fetcher import get_account_balance

INVESTMENT_CATEGORIES = {"Investments", "Joint Account"}
FIXED_CATEGORIES      = {"Rent", "Subscriptions"}


DEFAULT_WEEKLY_PROMPT = """\
You are writing a weekly personal finance summary email for {user_name}.

Here is all their current financial data:
{context}

Write a well-structured email with the following sections. Be specific with numbers, honest, and actionable. Tone: like a smart, direct financial advisor who knows their situation well.

**1. Wealth Overview**
- Total money available across all accounts, and how it changed vs last week
- Runway: how many months they could sustain their current lifestyle without a salary
- Keep it brief — 3-4 sentences

**2. This Month's Expenses (so far)**
- Summarise total spend, split between fixed costs (rent, subscriptions) and variable
- Highlight any big or unexpected purchases — prompt them to reflect: was this planned? worth it?
- Flag any outliers vs typical spending
- Be specific: name the merchants and amounts

**3. Projected Spend vs Budget**
- Based on days elapsed in the month, project end-of-month total
- Compare to last month
- Flag any budget categories at risk of being exceeded

**4. Investment & Savings Strategy**
- Review the current savings split across all accounts
- Which savings vehicle is best for each purpose (emergency fund, savings goal, long-term)?
- Concrete suggestions: any reallocation or changes to monthly contributions?
- Consider the savings rate this month — is it enough?

**5. Path to Savings Goal**
- Current progress toward the savings goal
- At the current savings rate, how long to reach the goal?
- Propose a concrete savings/investment plan to reach the goal within 5 years

End with one motivating sentence.
Do not use markdown — write in plain text suitable for an email.
Use € for all amounts.\
"""

DEFAULT_MONTHLY_PROMPT = """\
You are writing a monthly personal finance review email for {user_name}.

Here is all their current financial data:
{context}

Write a structured monthly review. Be analytical, specific, and forward-looking. Tone: like a smart, direct financial advisor doing an end-of-month debrief.

**1. Month in Review**
- How much did they earn, spend, and save this month?
- How does this compare to last month?
- Did they stay within budget?

**2. Spending Breakdown**
- Full breakdown by category — which categories grew or shrank vs last month?
- Top merchants by spend
- Any patterns worth noting?

**3. Savings & Investments**
- How much went into savings and investments this month?
- Savings rate as a % of salary — is this on track?
- Any changes recommended to the savings split?

**4. Goal Progress**
- Progress toward the savings goal
- Updated projection: at current rate, when will they reach the target?
- What would they need to save per month to reach it in 3 years vs 5 years?

**5. Next Month Action Plan**
- 3 concrete things to focus on next month
- Any spending categories to watch or cut?

Do not use markdown — write in plain text suitable for an email.
Use € for all amounts.\
"""


def _collect_financial_context() -> dict:
    """Gather all financial data needed for summaries."""
    now        = pd.Timestamp.now()
    month_str  = now.strftime("%Y-%m")
    last_month = (now - pd.DateOffset(months=1)).strftime("%Y-%m")

    main_account_id = get_main_account()
    accounts_df = get_bank_accounts()

    df = get_transactions()
    df = df.copy()
    df["date"]       = pd.to_datetime(df["date"])
    df["month"]      = df["date"].dt.to_period("M").astype(str)
    df["amount_abs"] = df["amount"].abs()

    this_month_df = df[df["month"] == month_str]
    last_month_df = df[df["month"] == last_month]

    debits_this = this_month_df[this_month_df["type"] == "debit"].copy()
    debits_last = last_month_df[last_month_df["type"] == "debit"].copy()

    expenses_this = debits_this[~debits_this["category"].isin(INVESTMENT_CATEGORIES)]
    invested_this = debits_this[debits_this["category"].isin(INVESTMENT_CATEGORIES)]
    expenses_last = debits_last[~debits_last["category"].isin(INVESTMENT_CATEGORIES)]

    by_category = (
        expenses_this.groupby("category")["amount_abs"]
        .sum().sort_values(ascending=False)
        .reset_index().to_dict(orient="records")
    )
    by_merchant = (
        expenses_this.groupby("merchant")["amount_abs"]
        .sum().sort_values(ascending=False).head(15)
        .reset_index().to_dict(orient="records")
    )

    fixed_spend    = expenses_this[expenses_this["category"].isin(FIXED_CATEGORIES)]["amount_abs"].sum()
    variable_spend = expenses_this[~expenses_this["category"].isin(FIXED_CATEGORIES)]["amount_abs"].sum()

    days_elapsed  = now.day
    days_in_month = pd.Timestamp(now.year, now.month, 1).days_in_month
    total_expenses_this = expenses_this["amount_abs"].sum()
    projected = round(total_expenses_this / days_elapsed * days_in_month, 2) if days_elapsed > 0 else 0

    avg_by_merchant = debits_last.groupby("merchant")["amount_abs"].mean()
    outliers = []
    for _, row in expenses_this.iterrows():
        merchant = row["merchant"]
        avg = avg_by_merchant.get(merchant, None)
        if avg and row["amount_abs"] > avg * 2:
            outliers.append({
                "merchant": merchant,
                "amount": round(row["amount_abs"], 2),
                "avg_last_month": round(avg, 2),
                "date": str(row["date"].date()),
            })
    big_purchases = expenses_this[
        (expenses_this["amount_abs"] > 100) &
        (~expenses_this["category"].isin(FIXED_CATEGORIES))
    ][["date", "merchant", "category", "amount_abs"]].copy()
    big_purchases["date"] = big_purchases["date"].astype(str)
    big_purchases = big_purchases.sort_values("amount_abs", ascending=False).to_dict(orient="records")

    budgets    = get_budgets()
    month_sp   = expenses_this.groupby("merchant")["amount_abs"].sum().reset_index()
    month_sp.columns = ["category", "spent"]
    budget_status = []
    if not budgets.empty:
        merged = budgets.merge(month_sp, on="category", how="left").fillna(0)
        budget_status = merged.to_dict(orient="records")

    bal_personal  = get_account_balance(main_account_id) if main_account_id else 0
    joint_ids     = accounts_df[accounts_df["is_joint"] == 1]["account_id"].tolist() if not accounts_df.empty and "is_joint" in accounts_df.columns else []
    bal_joint     = sum(get_account_balance(aid) or 0 for aid in joint_ids)
    savings_df    = get_savings_accounts()
    savings_total = savings_df["balance"].sum() if not savings_df.empty else 0.0
    total_wealth  = (bal_personal or 0) + bal_joint + savings_total

    prev_snapshot = json.loads(get_state("weekly_wealth_snapshot") or "null")
    wealth_change = round(total_wealth - prev_snapshot["total"], 2) if prev_snapshot else None
    set_state("weekly_wealth_snapshot", json.dumps({
        "total": round(total_wealth, 2),
        "date": str(now.date())
    }))

    avg_monthly_expenses = expenses_last["amount_abs"].sum() or total_expenses_this
    runway_months = round(total_wealth / avg_monthly_expenses, 1) if avg_monthly_expenses > 0 else None

    monthly_salary   = float(get_state("monthly_salary") or 0)
    invested_amount  = round(invested_this["amount_abs"].sum(), 2)
    savings_rate_pct = round(invested_amount / monthly_salary * 100, 1) if monthly_salary > 0 else None

    goals_df = get_goals()
    goals = []
    for _, g in goals_df.iterrows():
        remaining   = max(g["target_amount"] - savings_total, 0)
        months_away = round(remaining / invested_amount, 1) if invested_amount > 0 else None
        goals.append({
            "name":             g["name"],
            "target_eur":       g["target_amount"],
            "saved_eur":        round(savings_total, 2),
            "remaining_eur":    round(remaining, 2),
            "progress_pct":     round(savings_total / g["target_amount"] * 100, 1) if g["target_amount"] else 0,
            "months_at_current_rate": months_away,
        })

    account_meta = []
    if not accounts_df.empty:
        for _, acc in accounts_df.iterrows():
            account_meta.append({
                "name":       acc.get("display_name") or acc["account_id"],
                "is_main":    bool(acc.get("is_main", 0)),
                "is_joint":   bool(acc.get("is_joint", 0)),
                "currency":   acc.get("currency", "EUR"),
                "note":       "primary account — salary and most day-to-day transactions" if acc.get("is_main", 0) else (
                              "joint account" if acc.get("is_joint", 0) else "other account"
                ),
            })

    return {
        "report_date":          str(now.date()),
        "month":                month_str,
        "days_elapsed":         days_elapsed,
        "days_in_month":        days_in_month,
        "accounts":             account_meta,
        "balances": {
            "personal_eur":  round(bal_personal or 0, 2),
            "joint_eur":     round(bal_joint, 2),
            "savings_eur":   round(savings_total, 2),
            "savings_accounts": [
                {"name": r["name"], "type": r["type"], "balance_eur": round(r["balance"], 2)}
                for _, r in savings_df.iterrows()
            ] if not savings_df.empty else [],
            "total_eur":     round(total_wealth, 2),
            "change_vs_last_week_eur": wealth_change,
        },
        "runway_months":        runway_months,
        "monthly_salary_eur":   monthly_salary,
        "this_month": {
            "total_expenses_eur":     round(total_expenses_this, 2),
            "fixed_expenses_eur":     round(fixed_spend, 2),
            "variable_expenses_eur":  round(variable_spend, 2),
            "invested_eur":           invested_amount,
            "projected_expenses_eur": projected,
            "by_category":            by_category,
            "by_merchant":            by_merchant,
            "big_purchases":          big_purchases,
            "outliers_vs_last_month": outliers,
        },
        "budget_status":        budget_status,
        "savings_rate_pct":     savings_rate_pct,
        "goals":                goals,
        "last_month_expenses":  round(expenses_last["amount_abs"].sum(), 2),
    }


def generate_summary(api_key: str, prompt_template: str) -> str:
    """Generate a summary email using Claude with the given prompt template.
    Use {context} in the template as a placeholder for the financial data JSON."""
    ctx = _collect_financial_context()
    user_name = st.secrets.get("app", {}).get("user_name", "the user")
    prompt = prompt_template.replace("{context}", json.dumps(ctx, indent=2)).replace("{user_name}", user_name)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}]
    )
    return next(b.text for b in response.content if b.type == "text")


def send_summary_email(to_address: str, gmail_user: str, gmail_app_password: str,
                       api_key: str, prompt_template: str, subject: str):
    body = generate_summary(api_key, prompt_template)

    msg = MIMEMultipart()
    msg["From"]    = gmail_user
    msg["To"]      = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, to_address, msg.as_string())

    save_summary(subject=subject, body=body)
    return body
