"""Durable markdown memory file for the finance agent.

The file is the agent's long-term picture of the user's financial life —
what "normal" looks like, who merchants are, and how to read unusual months.
It is gitignored and rewritten by the agent as it learns.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import date

import pandas as pd

from finapp.config import MEMORY_EXAMPLE_PATH, MEMORY_PATH
from finapp.db import get_state, get_transactions

SKIP_CATEGORIES = {"Investments", "Joint Account", "Internal Transfer"}
INTERNAL_MERCHANT_HINTS = ("flexible cash",)
LAST_REVIEWED_RE = re.compile(r"Last reviewed:\s*(\d{4}-\d{2}-\d{2}|never)", re.I)

FALLBACK_TEMPLATE = """# Agent memory

Last reviewed: never

## Current situation
Nothing recorded yet.

## Recurring / baseline
- Typical rent, salary timing, and regular subscriptions once known.

## People & merchants
- Names and merchants that need context.

## How to read unusual months
- One-offs, overlapping costs, and credits that are not income.
"""


def _read_file(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return content if content.strip() else None


def _example_contents() -> str:
    return _read_file(MEMORY_EXAMPLE_PATH) or FALLBACK_TEMPLATE


def load_memory() -> str:
    """Return the memory file, seeding it from the example on first use."""
    if not os.path.exists(MEMORY_PATH):
        if os.path.exists(MEMORY_EXAMPLE_PATH):
            shutil.copyfile(MEMORY_EXAMPLE_PATH, MEMORY_PATH)
        else:
            save_memory(FALLBACK_TEMPLATE)
    return _read_file(MEMORY_PATH) or _example_contents()


def save_memory(content: str) -> dict:
    """Write the full memory file. Returns a short status dict."""
    text = (content or "").strip()
    if len(text) < 40:
        return {"error": "Memory content is too short — pass the complete file, not a fragment."}
    tmp_path = MEMORY_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    os.replace(tmp_path, MEMORY_PATH)
    return {
        "ok": True,
        "path": MEMORY_PATH,
        "last_reviewed": get_last_reviewed(text),
        "chars": len(text),
    }


def open_memory_in_editor() -> dict:
    """Open agent_memory.md in the local editor (Cursor if available)."""
    load_memory()
    path = os.path.abspath(MEMORY_PATH)
    candidates = [["cursor", path], ["code", path]]
    if sys.platform == "darwin":
        candidates.append(["open", "-a", "Cursor", path])
        candidates.append(["open", path])
    else:
        candidates.append(["xdg-open", path])

    for cmd in candidates:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"ok": True, "path": path, "opened_with": cmd[0]}
        except FileNotFoundError:
            continue
    return {
        "ok": False,
        "path": path,
        "error": f"Could not open an editor. Open `{MEMORY_PATH}` from the repo root.",
    }


def get_last_reviewed(content: str | None = None) -> str | None:
    text = content if content is not None else load_memory()
    match = LAST_REVIEWED_RE.search(text)
    if not match or match.group(1).lower() == "never":
        return None
    return match.group(1)


def scan_recent_activity(since: str | None = None) -> dict:
    """Flag what stands out since last review, plus this month vs a 3-month baseline."""
    today = date.today()
    last_reviewed = get_last_reviewed()
    if since:
        window_start = since
    elif last_reviewed:
        window_start = last_reviewed
    else:
        window_start = today.replace(day=1).isoformat()

    df = get_transactions()
    if df.empty:
        return {
            "window": {"from": window_start, "to": today.isoformat()},
            "last_reviewed": last_reviewed,
            "message": "No transactions in the database yet.",
        }

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["amount_abs"] = df["amount"].abs()
    df["category"] = df["category"].fillna("").astype(str)
    df["merchant"] = df["merchant"].fillna("").astype(str)

    month_start = today.replace(day=1)
    baseline_from = (month_start - pd.DateOffset(months=3)).to_pydatetime().date()
    since_ts = pd.Timestamp(window_start)
    month_ts = pd.Timestamp(month_start)

    new_df = df[df["date"] >= since_ts]
    month_df = df[df["date"] >= month_ts]
    baseline_df = df[(df["date"] >= pd.Timestamp(baseline_from)) & (df["date"] < month_ts)]

    return {
        "window": {"from": window_start, "to": today.isoformat()},
        "last_reviewed": last_reviewed,
        "this_month": _month_vs_baseline(month_df, baseline_df, month_start),
        "new_since_review": {
            "large_debits": _large_debits(new_df, df),
            "unusual_credits": _unusual_credits(new_df),
            "new_merchants": _new_merchants(new_df, df, since_ts),
            "recurring_extras": _recurring_extras(month_df, baseline_df),
        },
        "hint": (
            "Ask about findings that memory does not already explain. "
            "Do not invent a story. After the user answers, update the memory file."
        ),
    }


def _spend_mask(frame: pd.DataFrame) -> pd.Series:
    return (frame["type"] == "debit") & ~frame["category"].isin(SKIP_CATEGORIES)


def _is_internal_merchant(name: str) -> bool:
    lower = (name or "").lower()
    return any(hint in lower for hint in INTERNAL_MERCHANT_HINTS)


def _month_vs_baseline(month_df: pd.DataFrame, baseline_df: pd.DataFrame, month_start: date) -> dict:
    month_spend = month_df[_spend_mask(month_df)]
    baseline_spend = baseline_df[_spend_mask(baseline_df)]

    month_total = round(float(month_spend["amount_abs"].sum()), 2) if not month_spend.empty else 0.0
    if baseline_spend.empty:
        baseline_monthly = 0.0
    else:
        baseline_spend = baseline_spend.copy()
        baseline_spend["month"] = baseline_spend["date"].dt.to_period("M").astype(str)
        by_month = baseline_spend.groupby("month")["amount_abs"].sum()
        baseline_monthly = round(float(by_month.mean()), 2)

    spikes = []
    if not month_spend.empty:
        month_cats = month_spend.groupby("category")["amount_abs"].sum()
        if not baseline_spend.empty:
            baseline_spend = baseline_spend.copy()
            baseline_spend["month"] = baseline_spend["date"].dt.to_period("M").astype(str)
            baseline_cats = (
                baseline_spend.groupby(["month", "category"])["amount_abs"]
                .sum()
                .groupby("category")
                .mean()
            )
        else:
            baseline_cats = pd.Series(dtype=float)

        for category, spent in month_cats.items():
            if not category.strip():
                continue
            typical = float(baseline_cats.get(category, 0.0))
            if spent < 80:
                continue
            if typical <= 0:
                if spent >= 150:
                    spikes.append({
                        "category": category,
                        "this_month_eur": round(float(spent), 2),
                        "baseline_monthly_avg_eur": 0.0,
                        "note": "little or no spend in this category in the prior 3 months",
                    })
                continue
            ratio = float(spent) / typical
            if ratio >= 1.5 and (spent - typical) >= 80:
                spikes.append({
                    "category": category,
                    "this_month_eur": round(float(spent), 2),
                    "baseline_monthly_avg_eur": round(typical, 2),
                    "ratio": round(ratio, 2),
                })

    spikes.sort(key=lambda row: row["this_month_eur"], reverse=True)
    return {
        "month": month_start.strftime("%Y-%m"),
        "expenses_eur": month_total,
        "baseline_monthly_expenses_eur": baseline_monthly,
        "category_spikes": spikes[:8],
    }


def _large_debits(new_df: pd.DataFrame, all_df: pd.DataFrame, limit: int = 8) -> list[dict]:
    spend = new_df[_spend_mask(new_df)]
    if spend.empty:
        return []

    recent = all_df[_spend_mask(all_df)]
    cutoff = 200.0
    if not recent.empty and len(recent) >= 10:
        cutoff = max(80.0, float(recent["amount_abs"].quantile(0.9)))

    flagged = spend[spend["amount_abs"] >= cutoff].sort_values("amount_abs", ascending=False)
    return _tx_records(flagged.head(limit))


def _unusual_credits(new_df: pd.DataFrame, limit: int = 8) -> list[dict]:
    credits = new_df[new_df["type"] == "credit"].copy()
    if credits.empty:
        return []
    credits = credits[~credits["category"].isin(SKIP_CATEGORIES)]
    credits = credits[~credits["merchant"].map(_is_internal_merchant)]

    salary = float(get_state("monthly_salary") or 0)
    if salary > 0:
        credits = credits[
            (credits["amount_abs"] < salary * 0.8) | (credits["amount_abs"] > salary * 1.2)
        ]

    credits = credits[credits["amount_abs"] >= 50].sort_values("amount_abs", ascending=False)
    return _tx_records(credits.head(limit))


def _new_merchants(new_df: pd.DataFrame, all_df: pd.DataFrame, since_ts: pd.Timestamp, limit: int = 8) -> list[dict]:
    spend = new_df[_spend_mask(new_df)]
    if spend.empty:
        return []
    prior = all_df[(all_df["date"] < since_ts) & _spend_mask(all_df)]
    known = set(prior["merchant"].str.lower().unique()) if not prior.empty else set()

    rows = []
    grouped = spend.groupby(spend["merchant"].str.lower())
    for key, group in grouped:
        if not key or key in known:
            continue
        total = float(group["amount_abs"].sum())
        if total < 50:
            continue
        sample = group.iloc[0]
        rows.append({
            "merchant": sample["merchant"],
            "first_seen": group["date"].min().strftime("%Y-%m-%d"),
            "spend_eur": round(total, 2),
            "category": sample["category"],
            "count": int(len(group)),
        })
    rows.sort(key=lambda row: row["spend_eur"], reverse=True)
    return rows[:limit]


def _recurring_extras(month_df: pd.DataFrame, baseline_df: pd.DataFrame, limit: int = 6) -> list[dict]:
    """Merchants that usually show up about once a month but appeared extra times this month."""
    month_spend = month_df[_spend_mask(month_df)]
    baseline_spend = baseline_df[_spend_mask(baseline_df)]
    if month_spend.empty or baseline_spend.empty:
        return []

    baseline = baseline_spend.copy()
    baseline["month"] = baseline["date"].dt.to_period("M").astype(str)
    typical_counts = (
        baseline.groupby(["merchant", "month"]).size()
        .groupby("merchant")
        .mean()
    )
    typical_counts = typical_counts[typical_counts <= 2.5]
    if typical_counts.empty:
        return []

    month_counts = month_spend.groupby("merchant").size()
    month_totals = month_spend.groupby("merchant")["amount_abs"].sum()

    extras = []
    for merchant, count in month_counts.items():
        typical = float(typical_counts.get(merchant, 0))
        if typical < 0.5 or count < typical + 0.8 or count < 2:
            continue
        spent = float(month_totals.get(merchant, 0))
        if spent < 80:
            continue
        extras.append({
            "merchant": merchant,
            "this_month_count": int(count),
            "typical_monthly_count": round(typical, 1),
            "this_month_eur": round(spent, 2),
        })
    extras.sort(key=lambda row: row["this_month_eur"], reverse=True)
    return extras[:limit]


def _tx_records(frame: pd.DataFrame) -> list[dict]:
    records = []
    for _, row in frame.iterrows():
        records.append({
            "id": row.get("id"),
            "date": row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else None,
            "merchant": row["merchant"],
            "amount_eur": round(float(row["amount"]), 2),
            "category": row["category"],
        })
    return records
