import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta, datetime, timezone
from finapp.db import (init_db, get_transactions, upsert_transactions, get_state, set_state, get_goals, upsert_goal,
                       delete_goal, get_summaries, get_savings_accounts, upsert_savings_account,
                       delete_savings_account, get_assets, upsert_asset, delete_asset,
                       save_wealth_snapshot, get_wealth_snapshots, get_account_display_names,
                       get_bank_connections, get_bank_accounts, add_bank_connection,
                       delete_bank_connection, upsert_bank_account, update_bank_account_name, update_bank_account_joint,
                       set_main_account, get_main_account, update_transaction_category,
                       upsert_tr_transactions, get_tr_transactions, sync_tr_portfolio,
                       save_tr_prices, get_tr_prices,
                       get_categories, add_category, delete_category, rename_category)
from finapp.investments.tr_fetcher import (tr_is_logged_in, tr_initiate_weblogin,
                                           tr_complete_weblogin, tr_sync)
import yfinance as yf
from finapp.banking.fetcher import fetch_and_store, get_account_balance, list_banks, initiate_auth, complete_auth, backfill_wealth_snapshots
from finapp.investments.etf_catalog import ETF_CATALOG
from finapp.notifier import send_summary_email, DEFAULT_WEEKLY_PROMPT, DEFAULT_MONTHLY_PROMPT
from finapp.agent import run_agent, auto_categorize, apply_rules
from finapp.rules import RULES as _CATEGORIZATION_RULES

st.set_page_config(page_title="Finance App", page_icon="💰", layout="wide")

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

_DARK_CSS = """
<style>
html, body, [class*="css"], h1, h2, h3, h4, h5, h6 {
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Menlo", monospace !important;
}
.stApp, [data-testid="stAppViewContainer"] {
    background-color: #0d1117 !important;
    color: #e6edf3 !important;
}
[data-testid="stHeader"] {
    background-color: #0d1117 !important;
    border-bottom: 1px solid #30363d !important;
}
section[data-testid="stSidebar"] { background-color: #161b22 !important; }
.block-container { background-color: #0d1117 !important; }
p, span, label, div, h1, h2, h3, h4, h5, h6, li, td, th {
    color: #e6edf3 !important;
}
[data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #8b949e !important; }
[data-testid="stMetricDelta"] { filter: brightness(1.4); }
[data-testid="stTabs"] button { color: #8b949e !important; }
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #e6edf3 !important;
    border-bottom-color: #58a6ff !important;
}
[data-testid="stExpander"] {
    background-color: #161b22 !important;
    border-color: #30363d !important;
}
.stButton > button {
    background-color: #21262d !important;
    color: #c9d1d9 !important;
    border: 1px solid #30363d !important;
}
.stButton > button:hover {
    background-color: #30363d !important;
    border-color: #8b949e !important;
    color: #ffffff !important;
}
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] > div > div > input,
[data-testid="stNumberInput"] > div > div > input,
[data-testid="stTextArea"] textarea {
    background-color: #1c2128 !important;
    color: #e6edf3 !important;
    border-color: #30363d !important;
}
/* ── Selectbox: closed state ── */
[data-baseweb="select"] > div {
    background-color: #1c2128 !important;
    color: #e6edf3 !important;
    border-color: #30363d !important;
}
[data-baseweb="select"] span,
[data-baseweb="select"] div {
    color: #e6edf3 !important;
    background-color: transparent !important;
}

/* ── Selectbox / combobox: open dropdown portal ── */
[data-baseweb="popover"] {
    background-color: #1c2128 !important;
}
[data-baseweb="menu"],
[data-baseweb="menu"] ul {
    background-color: #1c2128 !important;
    border-color: #30363d !important;
}
[data-baseweb="option"],
[role="option"],
[role="listbox"] li {
    background-color: #1c2128 !important;
    color: #e6edf3 !important;
}
[data-baseweb="option"]:hover,
[role="option"]:hover {
    background-color: #30363d !important;
    color: #ffffff !important;
}
[aria-selected="true"][data-baseweb="option"],
[aria-selected="true"][role="option"] {
    background-color: #21262d !important;
    color: #58a6ff !important;
}
[role="listbox"] {
    background-color: #1c2128 !important;
    border-color: #30363d !important;
}

/* ── data_editor SelectboxColumn cell editor ── */
.glide-data-grid-cells .dvn-scroller,
div.dvn-stack {
    background-color: #0d1117 !important;
    color: #e6edf3 !important;
}
/* The inline select that pops up inside the grid cell */
div[class*="cell-editor"] select,
div[class*="Portal"] select {
    background-color: #1c2128 !important;
    color: #e6edf3 !important;
    border-color: #30363d !important;
}
div[class*="Portal"] ul,
div[class*="Portal"] li {
    background-color: #1c2128 !important;
    color: #e6edf3 !important;
}
div[class*="Portal"] li:hover {
    background-color: #30363d !important;
    color: #ffffff !important;
}
[data-testid="stDataFrame"] { background-color: #1c2128 !important; }
[data-testid="stTable"] { background-color: #1c2128 !important; }
div[data-testid="stChatMessage"] { background-color: #161b22 !important; }
.stAlert { background-color: #1c2128 !important; border-color: #30363d !important; }
[data-testid="stMarkdownContainer"] code {
    background-color: #1c2128 !important;
    color: #79c0ff !important;
}
</style>
"""

_LIGHT_CSS = """
<style>
html, body, [class*="css"], h1, h2, h3, h4, h5, h6 {
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Menlo", monospace !important;
}
</style>
"""

_HIGH_CONTRAST = "#e6edf3"

def _plotly_theme():
    if st.session_state.dark_mode:
        return dict(
            template="plotly_dark",
            paper_bgcolor="#161b22",
            plot_bgcolor="#0d1117",
            font=dict(color=_HIGH_CONTRAST, size=12),
            title_font=dict(color=_HIGH_CONTRAST, size=14),
            legend=dict(
                font=dict(color=_HIGH_CONTRAST, size=12),
                bgcolor="#1c2128",
                bordercolor="#444d56",
                borderwidth=1,
            ),
            xaxis=dict(
                tickfont=dict(color=_HIGH_CONTRAST),
                title_font=dict(color=_HIGH_CONTRAST),
                gridcolor="#30363d",
                linecolor="#444d56",
            ),
            yaxis=dict(
                tickfont=dict(color=_HIGH_CONTRAST),
                title_font=dict(color=_HIGH_CONTRAST),
                gridcolor="#30363d",
                linecolor="#444d56",
            ),
            coloraxis=dict(colorbar=dict(
                tickfont=dict(color=_HIGH_CONTRAST),
                title_font=dict(color=_HIGH_CONTRAST),
            )),
        )
    return dict(template="plotly_white")

def _apply_chart_theme(fig):
    fig.update_layout(**_plotly_theme())
    if st.session_state.dark_mode:
        # Force annotation text to high contrast (annotations inherit from font but some charts override)
        for ann in fig.layout.annotations:
            if not ann.font or not ann.font.color:
                ann.font = dict(color=_HIGH_CONTRAST, size=getattr(ann.font, "size", 11) if ann.font else 11)

st.markdown(_DARK_CSS if st.session_state.dark_mode else _LIGHT_CSS, unsafe_allow_html=True)

_title_col, _theme_col, _btn1_col, _btn2_col = st.columns([7, 0.8, 1.2, 1.6])
_title_col.title("💰 Personal Finance Dashboard")

if _theme_col.button("☀️" if st.session_state.dark_mode else "🌙", use_container_width=True):
    st.session_state.dark_mode = not st.session_state.dark_mode
    st.rerun()

if _btn1_col.button("🔄 Sync", use_container_width=True):
    with st.spinner("Fetching from Enable Banking..."):
        try:
            n = fetch_and_store(date_from=str(date.today() - timedelta(days=365)))
            st.success(f"Synced {n} transactions")
        except Exception as e:
            st.error(f"Error: {e}")

if _btn2_col.button("🏷️ Categorize", use_container_width=True):
    with st.spinner("Categorizing..."):
        try:
            n_rules = apply_rules()
            n_ai = auto_categorize(api_key=get_api_key())
            st.success(f"Rules: {n_rules} — AI: {n_ai} merchants")
            st.rerun()
        except Exception as e:
            st.error(f"Categorization error: {e}")

init_db()

def get_api_key() -> str:
    """Return the Anthropic API key — DB takes precedence over secrets.toml. Returns empty string if key looks invalid."""
    key = get_state("anthropic_api_key") or st.secrets.get("anthropic", {}).get("api_key", "") or ""
    return key if len(key) > 20 else ""

# One-time migration: seed savings_accounts from old app_state keys if table is empty
def _migrate_savings():
    existing = get_savings_accounts()
    if not existing.empty:
        return
    flex = get_state("bal_flexible_cash")
    tr   = get_state("bal_trade_republic")
    if flex and float(flex) > 0:
        upsert_savings_account(name="Flexible Cash", type="flexible", balance=float(flex),
                               interest_rate=3.5, notes="Revolut Flexible Cash Fund")
    if tr and float(tr) > 0:
        upsert_savings_account(name="Trade Republic", type="brokerage", balance=float(tr),
                               notes="TR brokerage — ETFs/stocks")

_migrate_savings()

# --- Onboarding state (computed before st.tabs so we can show progress in the tab label) ---
_ob_connections  = get_bank_connections()
_ob_assets_df    = get_assets()
_ob_goals_df     = get_goals()
_ob_salary       = get_state("monthly_salary")
_ob_budget       = get_state("monthly_expense_budget")
_ob_cats         = get_categories()
_ob_has_api_key  = bool(get_api_key())
_ob_has_email    = bool(st.secrets.get("email", {}).get("app_password", ""))
_ob_skip_invest  = get_state("ob_skip_investments") == "1"
_ob_skip_email   = get_state("ob_skip_email") == "1"

_ob_done = [
    not _ob_connections.empty,
    not _ob_assets_df.empty or _ob_skip_invest,
    bool(_ob_salary and float(_ob_salary) > 0),
    bool(_ob_budget and float(_ob_budget) > 0),
    not _ob_goals_df.empty,
    bool(_ob_cats),
    _ob_has_api_key,
    _ob_has_email or _ob_skip_email,
]
_ob_n     = sum(_ob_done)
_ob_all   = all(_ob_done)
_ob_label = "✅ Get Started" if _ob_all else f"Get Started ({_ob_n}/8)"

tab_dashboard, tab_chat, tab_summaries, tab_banks, tab_settings, tab_setup = st.tabs(
    ["Dashboard", "Ask AI", "Summaries", "Banks", "Settings", _ob_label]
)


def _minutes_since(state_key: str) -> float:
    last = get_state(state_key)
    if not last:
        return float("inf")
    delta = datetime.now(timezone.utc) - datetime.fromisoformat(last)
    return delta.total_seconds() / 60


def _touch(state_key: str):
    set_state(state_key, datetime.now(timezone.utc).isoformat())


# --- Auto-fetch: once per hour ---
if _minutes_since("last_sync") > 60:
    month_start = date.today().replace(day=1)
    with st.spinner("Syncing current month..."):
        try:
            fetch_and_store(date_from=str(month_start))
            _touch("last_sync")
        except Exception:
            pass


# --- Account filter (global, from DB) ---
_account_names = get_account_display_names()  # {account_id: display_name}

# --- Load data ---
df = get_transactions()

def effective_balance(acc) -> float:
    """Compute balance + contributions since balance_date + interest accrual."""
    balance = float(acc["balance"])
    balance_date = acc.get("balance_date")
    monthly_contribution = float(acc.get("monthly_contribution") or 0)
    interest_rate = float(acc.get("interest_rate") or 0)

    if not balance_date:
        return balance

    days = (date.today() - date.fromisoformat(balance_date)).days
    if days <= 0:
        return balance

    months = days / 30.44
    balance += monthly_contribution * months

    if interest_rate > 0:
        balance *= (1 + interest_rate / 100) ** (days / 365)

    return balance


# --- Get Started (onboarding) tab ---
with tab_setup:
    if _ob_all:
        st.success("🎉 You're all set! All 8 setup steps are complete.")
        st.caption("You can always return here to review or update your configuration.")
    else:
        st.header("Get Started")
        st.caption(f"{_ob_n} of 8 steps complete — work through these in order.")
        st.progress(_ob_n / 8)

    st.divider()

    # Step 1: Connect a bank account
    with st.container(border=True):
        _s1a, _s1b = st.columns([0.05, 0.95])
        _s1a.markdown("✅" if _ob_done[0] else "⬜")
        _s1b.markdown("**Step 1 — Connect a bank account**")
        if _ob_done[0]:
            _connected = ", ".join(_ob_connections["display_name"].tolist())
            st.caption(f"Connected: {_connected}. Manage in the **Banks** tab.")
        else:
            st.caption("Connect your bank via Open Banking (PSD2). Works with Revolut, N26, and most EU banks.")
            if "banks_list" not in st.session_state:
                try:
                    st.session_state.banks_list = list_banks()
                except Exception:
                    st.session_state.banks_list = []
            _bl = st.session_state.banks_list
            _ob_countries = sorted({b["country"] for b in _bl}) if _bl else []
            _of1, _of2, _of3 = st.columns(3)
            if _ob_countries:
                _ob_sel_country = _of1.selectbox("Country", _ob_countries, key="_ob_country")
                _ob_banks_in = [b["name"] for b in _bl if b["country"] == _ob_sel_country]
                _ob_sel_bank = _of2.selectbox("Bank", sorted(_ob_banks_in), key="_ob_bank")
            else:
                _ob_sel_country = _of1.text_input("Country code (e.g. DE)", key="_ob_country_txt")
                _ob_sel_bank = _of2.text_input("Bank name (e.g. Revolut)", key="_ob_bank_txt")
            _ob_conn_label = _of3.text_input("Label (e.g. My Revolut)", key="_ob_conn_label")
            if st.button("Get authorization link", key="_ob_get_auth") and _ob_sel_bank and _ob_sel_country:
                try:
                    _ob_auth_url = initiate_auth(bank_name=_ob_sel_bank, bank_country=_ob_sel_country)
                    st.session_state._ob_pending_auth = {
                        "url": _ob_auth_url, "bank": _ob_sel_bank,
                        "country": _ob_sel_country, "label": _ob_conn_label or _ob_sel_bank,
                    }
                except Exception as e:
                    st.error(f"Failed to start authorization: {e}")
            if "_ob_pending_auth" in st.session_state:
                _auth = st.session_state._ob_pending_auth
                st.info(f"Authorize **{_auth['bank']}** — open the link below, then paste the redirect URL back here.")
                st.markdown(f"[Open authorization link]({_auth['url']})")
                _ob_redirect = st.text_input("Paste the redirect URL after authorizing", key="_ob_redirect_url")
                if st.button("Complete connection", key="_ob_complete_auth") and _ob_redirect:
                    try:
                        _sid, _n_accs = complete_auth(
                            redirect_url=_ob_redirect,
                            bank_name=_auth["bank"],
                            bank_country=_auth["country"],
                            display_name=_auth["label"],
                        )
                        del st.session_state._ob_pending_auth
                        st.success(f"Connected! Found {_n_accs} account(s). You can rename them in the Banks tab.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Connection failed: {e}")

    # Step 2: Investment portfolio
    with st.container(border=True):
        _s2a, _s2b = st.columns([0.05, 0.95])
        _s2a.markdown("✅" if _ob_done[1] else "⬜")
        _s2b.markdown("**Step 2 — Set up investment portfolio** *(optional)*")
        if _ob_skip_invest:
            st.caption("Skipped. You can add investments later in the Dashboard tab.")
        elif not _ob_assets_df.empty:
            st.caption(f"{len(_ob_assets_df)} position(s) configured. Manage in the **Dashboard** tab.")
        else:
            st.caption("Add your portfolio — Trade Republic syncs automatically, or add positions manually by ticker.")
            _ob_inv_choice = st.radio(
                "How do you invest?",
                ["Trade Republic", "Other broker (add by ticker)", "I don't have investments"],
                key="_ob_inv_choice", horizontal=True,
            )
            if _ob_inv_choice == "Trade Republic":
                _tr_creds = bool(
                    st.secrets.get("trade_republic", {}).get("phone_no") and
                    st.secrets.get("trade_republic", {}).get("pin")
                )
                if _tr_creds:
                    st.info("TR credentials are configured. Go to the **Banks** tab to log in and sync your portfolio.")
                else:
                    st.warning("Add your TR credentials to `.streamlit/secrets.toml` first, then restart the app:")
                    st.code('[trade_republic]\nphone_no = "+49176..."\npin = "1234"', language="toml")
            elif _ob_inv_choice == "Other broker (add by ticker)":
                _ob_etf_opts = ["— Search popular ETFs —"] + [
                    f"{e['name']} ({e['ticker']}) [{e['category']}]" for e in ETF_CATALOG
                ] + ["Other (enter manually)"]
                _ob_cat_pick = st.selectbox("Pick from catalog or enter manually", _ob_etf_opts, key="_ob_etf_pick")
                if _ob_cat_pick not in ("— Search popular ETFs —", "Other (enter manually)"):
                    _ob_idx = _ob_etf_opts.index(_ob_cat_pick) - 1
                    _ob_preset = ETF_CATALOG[_ob_idx]
                    _ob_a_name   = st.text_input("Asset name", value=_ob_preset["name"], key="_ob_a_name")
                    _ob_a_ticker = st.text_input("Yahoo Finance ticker", value=_ob_preset["ticker"], key="_ob_a_ticker")
                else:
                    _ob_a_name   = st.text_input("Asset name", key="_ob_a_name")
                    _ob_a_ticker = st.text_input("Yahoo Finance ticker (e.g. EUNL.DE)", key="_ob_a_ticker",
                                                 help="Append .DE for Xetra, .L for London, etc.")
                _ob_a_shares = st.number_input("Number of shares", min_value=0.0, step=0.01, key="_ob_a_shares")
                if st.button("Add position", key="_ob_save_asset") and _ob_a_name and _ob_a_ticker:
                    upsert_asset(name=_ob_a_name, ticker=_ob_a_ticker, shares=_ob_a_shares)
                    st.success(f"Added {_ob_a_name}. Add more positions in the Dashboard tab.")
                    st.rerun()
            else:
                if st.button("Skip this step", key="_ob_skip_inv"):
                    set_state("ob_skip_investments", "1")
                    st.rerun()

    # Step 3: Monthly salary
    with st.container(border=True):
        _s3a, _s3b = st.columns([0.05, 0.95])
        _s3a.markdown("✅" if _ob_done[2] else "⬜")
        _s3b.markdown("**Step 3 — Set monthly net salary**")
        if _ob_done[2]:
            st.caption(f"€{float(_ob_salary):,.0f}/month. Update in Dashboard → Income & Spending.")
        else:
            st.caption("Used to calculate your savings rate and spending as a % of income.")
            _ob_sal_val = st.number_input("Monthly net salary (€)", min_value=0.0, step=100.0, key="_ob_salary_input")
            if st.button("Save salary", key="_ob_save_salary") and _ob_sal_val > 0:
                set_state("monthly_salary", str(_ob_sal_val))
                st.rerun()

    # Step 4: Monthly budget
    with st.container(border=True):
        _s4a, _s4b = st.columns([0.05, 0.95])
        _s4a.markdown("✅" if _ob_done[3] else "⬜")
        _s4b.markdown("**Step 4 — Set monthly expense budget**")
        if _ob_done[3]:
            st.caption(f"€{float(_ob_budget):,.0f}/month. Update in Dashboard → Income & Spending.")
        else:
            st.caption("Your target monthly spending (excluding investments and transfers).")
            _ob_bud_val = st.number_input("Monthly expense budget (€)", min_value=0.0, step=100.0, key="_ob_budget_input")
            if st.button("Save budget", key="_ob_save_budget") and _ob_bud_val > 0:
                set_state("monthly_expense_budget", str(_ob_bud_val))
                st.rerun()

    # Step 5: Financial goal
    with st.container(border=True):
        _s5a, _s5b = st.columns([0.05, 0.95])
        _s5a.markdown("✅" if _ob_done[4] else "⬜")
        _s5b.markdown("**Step 5 — Set a financial goal**")
        if _ob_done[4]:
            _goal_names = ", ".join(_ob_goals_df["name"].tolist())
            st.caption(f"Goals: {_goal_names}. Manage in the Dashboard.")
        else:
            st.caption("Track progress toward a savings target — emergency fund, home purchase, etc.")
            _ob_g_name   = st.text_input("Goal name", value="Emergency fund", key="_ob_goal_name")
            _ob_g_target = st.number_input("Target amount (€)", min_value=0.0, value=10000.0, step=1000.0, key="_ob_goal_target")
            _ob_g_notes  = st.text_input("Notes (optional)", key="_ob_goal_notes")
            if st.button("Save goal", key="_ob_save_goal") and _ob_g_name:
                upsert_goal(_ob_g_name, _ob_g_target, _ob_g_notes)
                st.rerun()

    # Step 6: Categories & keyword rules
    with st.container(border=True):
        _s6a, _s6b = st.columns([0.05, 0.95])
        _s6a.markdown("✅" if _ob_done[5] else "⬜")
        _s6b.markdown("**Step 6 — Set up transaction categories**")
        if _ob_done[5]:
            st.caption(f"{len(_ob_cats)} categories configured. Manage in Settings.")
        else:
            st.caption("Categories group your transactions (Groceries, Rent, Subscriptions…). Add at least a few to get started.")
            with st.form("_ob_cat_form", clear_on_submit=True):
                _ob_new_cat = st.text_input("Category name (e.g. Groceries)")
                if st.form_submit_button("Add") and _ob_new_cat.strip():
                    add_category(_ob_new_cat.strip())
                    st.rerun()
            if _ob_cats:
                st.caption("Added: " + " · ".join(_ob_cats))
            st.divider()
            st.caption("Also edit `src/finapp/rules.py` to map merchant keywords to categories automatically:")
            st.code('RULES = [\n    ("your landlord name", "Rent"),\n    ("edeka", "Groceries"),\n    ("spotify", "Subscriptions"),\n    # your own name in transfers:\n    ("your full name", "Internal Transfer"),\n]', language="python")
            st.caption("Keyword rules run before AI categorization. Anything unmatched is sent to Claude (if API key is set).")

    # Step 7: Anthropic API key
    with st.container(border=True):
        _s7a, _s7b = st.columns([0.05, 0.95])
        _s7a.markdown("✅" if _ob_done[6] else "⬜")
        _s7b.markdown("**Step 7 — Add Anthropic API key** *(enables AI chat & auto-categorization)*")
        if _ob_has_api_key:
            st.caption("API key configured. AI chat and auto-categorization are active.")
        else:
            st.caption("Add your Anthropic API key in **Settings** to enable AI chat and auto-categorization.")

    # Step 8: Email notifications
    with st.container(border=True):
        _s8a, _s8b = st.columns([0.05, 0.95])
        _s8a.markdown("✅" if _ob_done[7] else "⬜")
        _s8b.markdown("**Step 8 — Set up email summaries** *(optional)*")
        if _ob_has_email:
            st.caption("Email configured. Send summaries from the **Summaries** tab.")
        elif _ob_skip_email:
            st.caption("Skipped. You can configure email later by adding `[email]` to `.streamlit/secrets.toml`.")
        else:
            st.caption("Receive weekly or monthly spending summaries via Gmail.")
            st.code('[email]\nto = "you@example.com"\nuser = "you@gmail.com"\napp_password = "xxxx xxxx xxxx xxxx"', language="toml")
            st.caption("Generate a Gmail App Password at myaccount.google.com → Security → App passwords (requires 2FA).")
            if st.button("Skip — I don't need email", key="_ob_skip_email_btn"):
                set_state("ob_skip_email", "1")
                st.rerun()


# --- Dashboard tab ---
with tab_dashboard:
    if df.empty:
        st.info("No transactions yet. Click 'Sync transactions' above.")

    # --- Wealth Overview ---
    wo_col, filter_col = st.columns([6, 2])
    wo_col.header("Wealth Overview")
    account_names_list = list(_account_names.values())
    selected_account_names = filter_col.multiselect(
        "Accounts",
        options=account_names_list,
        default=account_names_list,
        label_visibility="collapsed",
    )
    selected_account_ids = [acc_id for acc_id, name in _account_names.items() if name in selected_account_names]

    if len(selected_account_ids) < len(_account_names):
        df = df[df["account_id"].isin(selected_account_ids)]

    # Joint account share factor
    _bank_accs = get_bank_accounts()
    _joint_share_pct = int(get_state("joint_account_share") or 100)
    _joint_account_ids = set(
        r["account_id"] for _, r in _bank_accs.iterrows() if r.get("is_joint", 0)
    )
    _joint_factor = _joint_share_pct / 100.0

    if _joint_account_ids and _joint_factor != 1.0:
        _joint_mask = df["account_id"].isin(_joint_account_ids)
        df = df.copy()
        df.loc[_joint_mask, "amount"] = df.loc[_joint_mask, "amount"] * _joint_factor

    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    current_month = pd.Timestamp.now().to_period("M").strftime("%Y-%m")
    last_month = (pd.Timestamp.now() - pd.DateOffset(months=1)).to_period("M").strftime("%Y-%m")

    all_debits = df[df["type"] == "debit"].copy()
    all_debits["amount_abs"] = all_debits["amount"].abs()

    # API balances — fetched for all known bank accounts, cached per session
    # (_bank_accs already fetched above for joint account detection)
    for _, _ba in _bank_accs.iterrows():
        _key = f"bal_{_ba['account_id']}"
        if _key not in st.session_state:
            st.session_state[_key] = get_account_balance(_ba["account_id"])

    # Split savings accounts: flexible = liquid, everything else = investment
    savings_df = get_savings_accounts()
    liquid_savings_df     = savings_df[savings_df["type"] == "flexible"] if not savings_df.empty else savings_df
    investment_savings_df = savings_df[savings_df["type"] != "flexible"] if not savings_df.empty else savings_df

    api_total = sum(
        (st.session_state.get(f"bal_{r['account_id']}", 0) or 0)
        * (_joint_factor if r["account_id"] in _joint_account_ids else 1.0)
        for _, r in _bank_accs.iterrows()
    )
    liquid_savings_total  = sum(effective_balance(acc) for _, acc in liquid_savings_df.iterrows()) if not liquid_savings_df.empty else 0.0
    liquid_total          = api_total + liquid_savings_total

    # ETF portfolio (prices fetched below)
    assets_df = get_assets()

    @st.cache_data(ttl=900)
    def fetch_prices(tickers: tuple) -> dict:
        prices = {}
        for ticker in tickers:
            price = None
            candidates = [ticker] if "." in ticker else [ticker, ticker + ".DE"]
            for candidate in candidates:
                try:
                    val = yf.Ticker(candidate).fast_info["last_price"]
                    if val:
                        price = val
                        break
                except Exception:
                    continue
            prices[ticker] = price
        return prices

    if not assets_df.empty:
        tickers = tuple(assets_df["ticker"].tolist())
        prices = fetch_prices(tickers)
        # Override with cached TR live prices for TR-synced positions
        tr_prices = get_tr_prices()
        if tr_prices:
            for isin, price in tr_prices.items():
                prices[isin] = price
        assets_df["current_price"] = assets_df["ticker"].map(prices)
        assets_df["current_value"] = assets_df["shares"] * assets_df["current_price"]
        portfolio_value       = assets_df["current_value"].sum()
        monthly_contributions = assets_df["monthly_contribution"].sum()
    else:
        portfolio_value       = 0.0
        monthly_contributions = 0.0

    investment_savings_total = sum(effective_balance(acc) for _, acc in investment_savings_df.iterrows()) if not investment_savings_df.empty else 0.0
    investments_total        = portfolio_value + investment_savings_total
    net_worth                = liquid_total + investments_total

    # Persist for use in Banks tab backfill
    st.session_state["current_liquid_savings"] = liquid_savings_total
    st.session_state["current_investments"]    = investments_total

    # Save daily snapshot once all numbers are known
    if _minutes_since("last_wealth_snapshot") > 60 * 23:
        save_wealth_snapshot(liquid_total, investments_total, net_worth)
        _touch("last_wealth_snapshot")

    # --- Summary row ---
    s1, s2, s3 = st.columns(3)
    s1.metric("Liquid (Bank)", f"€{liquid_total:,.2f}")
    s2.metric("Investments", f"€{investments_total:,.2f}")
    s3.metric("Net Worth", f"€{net_worth:,.2f}")

    # --- Wealth growth chart ---
    snapshots_df = get_wealth_snapshots()
    if len(snapshots_df) > 1:
        snapshots_df["date"] = pd.to_datetime(snapshots_df["date"])

        _wc1, _wc2, _wc3 = st.columns([2, 2, 4])
        _nw_period = _wc1.selectbox(
            "Range", ["This month", "Last 3 months", "Last 6 months", "Custom"],
            key="nw_period", label_visibility="collapsed"
        )
        _now = pd.Timestamp.now()
        if _nw_period == "This month":
            _nw_from = _now.replace(day=1).normalize()
        elif _nw_period == "Last 3 months":
            _nw_from = _now - pd.DateOffset(months=3)
        elif _nw_period == "Last 6 months":
            _nw_from = _now - pd.DateOffset(months=6)
        else:
            _nw_from = pd.Timestamp(_wc2.date_input("From", value=(_now - pd.DateOffset(months=3)).date(), key="nw_from"))

        snap_filtered = snapshots_df[snapshots_df["date"] >= _nw_from]
        if snap_filtered.empty:
            snap_filtered = snapshots_df

        chart_data = snap_filtered[["date", "liquid", "investments"]].melt(
            "date", var_name="type", value_name="amount"
        )
        chart_data["type"] = chart_data["type"].map({"liquid": "Liquid", "investments": "Investments"})
        fig = px.area(chart_data, x="date", y="amount", color="type",
                      title="Net Worth Over Time",
                      labels={"amount": "€", "date": ""},
                      color_discrete_map={"Liquid": "#3498db", "Investments": "#2ecc71"})
        fig.update_layout(hovermode="x unified")
        _apply_chart_theme(fig)
        st.plotly_chart(fig, use_container_width=True)

        # --- Month-over-month growth ---
        _mom_c1, _mom_c2, _mom_c3 = st.columns([2, 2, 4])
        _mom_period = _mom_c1.selectbox(
            "MoM range", ["Last 3 months", "Last 6 months", "Last 12 months", "All time", "Custom"],
            key="mom_period", label_visibility="collapsed"
        )
        if _mom_period == "Last 3 months":
            _mom_from = _now - pd.DateOffset(months=3)
        elif _mom_period == "Last 6 months":
            _mom_from = _now - pd.DateOffset(months=6)
        elif _mom_period == "Last 12 months":
            _mom_from = _now - pd.DateOffset(months=12)
        elif _mom_period == "All time":
            _mom_from = snapshots_df["date"].min()
        else:
            _mom_from = pd.Timestamp(_mom_c2.date_input("From ", value=(_now - pd.DateOffset(months=6)).date(), key="mom_from"))

        # Include one extra month before the range so the first bar has a diff to compute
        _mom_fetch_from = _mom_from - pd.DateOffset(months=1)
        _mom_snap = snapshots_df[snapshots_df["date"] >= _mom_fetch_from]

        _mom_snap = _mom_snap.copy()
        _mom_snap["month"] = _mom_snap["date"].dt.to_period("M")
        monthly = (
            _mom_snap.groupby("month")["net_worth"]
            .last()
            .reset_index()
        )
        monthly["month_str"] = monthly["month"].dt.to_timestamp().dt.strftime("%b %Y")
        if len(monthly) > 1:
            monthly["growth_abs"] = monthly["net_worth"].diff()
            monthly["growth_pct"] = monthly["net_worth"].pct_change() * 100
            _mom_from_period = pd.Period(_mom_from, freq="M")
            monthly_display = monthly[
                monthly["month"] >= _mom_from_period
            ].dropna(subset=["growth_abs"])

            if monthly_display.empty:
                st.info("No data available for the selected range.")
            else:
                _actual_from = monthly_display["month_str"].iloc[0]
                _actual_to   = monthly_display["month_str"].iloc[-1]
                if _mom_period not in ("All time", "Custom") and len(monthly_display) < int(_mom_period.split()[1]):
                    st.caption(f"Showing all available data: {_actual_from} → {_actual_to}")

                fig_mom = px.bar(
                    monthly_display, x="month_str", y="growth_pct",
                    title="Month-over-Month Net Worth Growth (%)",
                    labels={"month_str": "", "growth_pct": "%"},
                    color="growth_pct",
                    color_continuous_scale=["#e74c3c", "#95a5a6", "#2ecc71"],
                    color_continuous_midpoint=0,
                    text=monthly_display["growth_pct"].apply(lambda v: f"{v:+.1f}%"),
                )
                fig_mom.update_traces(textposition="outside")
                fig_mom.update_layout(
                    coloraxis_showscale=False,
                    hovermode="x unified",
                    xaxis=dict(type="category"),
                )
                fig_mom.update_traces(
                    customdata=monthly_display["growth_abs"].values,
                    hovertemplate="%{x}<br>%{y:+.1f}%  (%{customdata:+,.0f} €)<extra></extra>"
                )
                _apply_chart_theme(fig_mom)
                st.plotly_chart(fig_mom, use_container_width=True)

    st.divider()

    # --- Bank Accounts ---
    st.subheader("Bank Accounts")

    _bank_items = []
    for _, _ba in _bank_accs.iterrows():
        _bal = st.session_state.get(f"bal_{_ba['account_id']}")
        _bank_items.append((_ba["display_name"], f"€{_bal:,.2f}" if _bal is not None else "—"))
    for _, acc in liquid_savings_df.iterrows():
        label = acc["name"]
        if acc["interest_rate"]:
            label += f" ({acc['interest_rate']}% p.a.)"
        _bank_items.append((label, f"€{effective_balance(acc):,.2f}"))

    for _row_start in range(0, len(_bank_items), 2):
        _row_items = _bank_items[_row_start:_row_start + 2]
        _row_cols = st.columns(2)
        for _col, (_label, _val) in zip(_row_cols, _row_items):
            _col.metric(_label, _val)

    with st.expander("Manage savings accounts"):
        SAVINGS_TYPES = ["flexible", "festgeld", "brokerage", "other"]

        def _savings_form(prefix: str, acc=None):
            """Render savings account form fields. acc=None means add-new."""
            s_name     = st.text_input("Account name", value=acc["name"] if acc is not None else "", key=f"{prefix}_name")
            s_type     = st.selectbox("Type", SAVINGS_TYPES, index=SAVINGS_TYPES.index(acc["type"]) if acc is not None else 0, key=f"{prefix}_type")
            s_balance  = st.number_input("Current balance (€)", value=float(acc["balance"]) if acc is not None else 0.0, step=100.0, format="%.2f", key=f"{prefix}_balance", help="Set this to today's actual balance — the date will be recorded and contributions/interest will accrue from here.")
            s_contrib  = st.number_input("Monthly contribution (€)", value=float(acc["monthly_contribution"] or 0) if acc is not None else 0.0, min_value=0.0, step=10.0, format="%.2f", key=f"{prefix}_contrib")
            s_rate     = st.number_input("Interest rate (% p.a.)", value=float(acc["interest_rate"] or 0) if acc is not None else 0.0, step=0.1, format="%.2f", key=f"{prefix}_rate") if s_type in ("flexible", "festgeld") else None
            s_duration = st.number_input("Duration (months)", value=int(acc["duration_months"] or 0) if acc is not None else 0, step=1, key=f"{prefix}_duration") if s_type == "festgeld" else None
            s_maturity = st.text_input("Maturity date (YYYY-MM-DD)", value=acc["maturity_date"] or "" if acc is not None else "", key=f"{prefix}_maturity") if s_type == "festgeld" else None
            s_notes    = st.text_input("Notes", value=acc["notes"] or "" if acc is not None else "", key=f"{prefix}_notes")
            return s_name, s_type, s_balance, s_contrib, s_rate, s_duration, s_maturity, s_notes

        # Existing accounts — each with inline Edit / Delete
        for _, acc in savings_df.iterrows():
            acc_id = int(acc["id"])
            c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
            with c1:
                label = f"**{acc['name']}** ({acc['type']})"
                if acc["interest_rate"]:
                    label += f"  ·  {acc['interest_rate']}% p.a."
                if acc["maturity_date"]:
                    label += f"  ·  matures {acc['maturity_date']}"
                st.markdown(label)
            c2.metric("Balance", f"€{acc['balance']:,.2f}")
            if c3.button("Edit", key=f"edit_sav_{acc_id}"):
                st.session_state["editing_savings_id"] = acc_id
            if c4.button("Delete", key=f"del_sav_{acc_id}"):
                delete_savings_account(acc_id)
                st.session_state.pop("editing_savings_id", None)
                st.rerun()

            if st.session_state.get("editing_savings_id") == acc_id:
                with st.container(border=True):
                    s_name, s_type, s_balance, s_contrib, s_rate, s_duration, s_maturity, s_notes = _savings_form(f"sav_edit_{acc_id}", acc)
                    b1, b2 = st.columns(2)
                    if b1.button("Save", key=f"save_sav_{acc_id}"):
                        upsert_savings_account(name=s_name, type=s_type, balance=s_balance,
                                               monthly_contribution=s_contrib,
                                               interest_rate=s_rate or None,
                                               duration_months=int(s_duration) if s_duration else None,
                                               maturity_date=s_maturity or None,
                                               notes=s_notes, account_id=acc_id)
                        st.session_state.pop("editing_savings_id", None)
                        st.rerun()
                    if b2.button("Cancel", key=f"cancel_sav_{acc_id}"):
                        st.session_state.pop("editing_savings_id", None)
                        st.rerun()

        st.divider()
        st.subheader("Add new account")
        s_name, s_type, s_balance, s_contrib, s_rate, s_duration, s_maturity, s_notes = _savings_form("sav_new")
        if st.button("Save account", key="save_sav_new"):
            upsert_savings_account(name=s_name, type=s_type, balance=s_balance,
                                   monthly_contribution=s_contrib,
                                   interest_rate=s_rate or None,
                                   duration_months=int(s_duration) if s_duration else None,
                                   maturity_date=s_maturity or None,
                                   notes=s_notes)
            st.success("Saved")
            st.rerun()

    st.divider()

    # --- Investment Portfolio ---
    st.subheader("Investment Portfolio")

    if assets_df.empty and investment_savings_df.empty:
        st.info("No investments yet. Add ETFs below or add a savings account with type 'brokerage' or 'festgeld'.")
    else:
        # Summary row
        sum_cols = st.columns(2)
        sum_cols[0].metric("Total investments", f"€{investments_total:,.2f}")
        if monthly_contributions > 0:
            sum_cols[1].metric("Monthly contributions", f"€{monthly_contributions:,.2f}")

        st.divider()

        # ETFs & stocks — split by source
        if not assets_df.empty:
            _tr_assets     = assets_df[assets_df["source"] == "tr"]   if "source" in assets_df.columns else pd.DataFrame()
            _manual_assets = assets_df[assets_df["source"] != "tr"]   if "source" in assets_df.columns else assets_df

            def _render_asset_row(asset):
                val       = asset["current_value"]
                price     = asset["current_price"]
                price_str = f"€{price:,.2f}/share" if pd.notna(price) else "price unavailable"
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"{asset['name']} · {asset['ticker']} · {asset['shares']} shares · {price_str}")
                c2.metric("Value", f"€{val:,.2f}" if pd.notna(val) else "—")

            if not _tr_assets.empty:
                st.markdown("**Trade Republic**")
                for _, asset in _tr_assets.iterrows():
                    _render_asset_row(asset)

            if not _manual_assets.empty:
                st.markdown("**Manual**")
                for _, asset in _manual_assets.iterrows():
                    _render_asset_row(asset)

        # Other investment savings accounts grouped by type
        for group_type in investment_savings_df["type"].unique() if not investment_savings_df.empty else []:
            group = investment_savings_df[investment_savings_df["type"] == group_type]
            st.markdown(f"**{group_type.capitalize()}**")
            for _, acc in group.iterrows():
                label = acc["name"]
                if acc["interest_rate"]:
                    label += f" · {acc['interest_rate']}% p.a."
                c1, c2 = st.columns([3, 1])
                c1.markdown(label)
                c2.metric("Value", f"€{effective_balance(acc):,.2f}")

    with st.expander("Manage investments"):
        def _asset_form(prefix: str, asset=None):
            a_shares  = st.number_input("Number of shares", value=float(asset["shares"]) if asset is not None else 0.0, min_value=0.0, step=0.01, format="%.4f", key=f"{prefix}_shares")
            a_contrib = st.number_input("Monthly contribution (€)", value=float(asset["monthly_contribution"]) if asset is not None else 0.0, min_value=0.0, step=10.0, format="%.2f", key=f"{prefix}_contrib")
            a_notes   = st.text_input("Notes", value=asset["notes"] or "" if asset is not None else "", key=f"{prefix}_notes")
            return a_shares, a_contrib, a_notes

        _has_tr_assets     = "source" in assets_df.columns and (assets_df["source"] == "tr").any()
        _has_manual_assets = assets_df.empty or "source" not in assets_df.columns or (assets_df["source"] != "tr").any()

        # --- TR-sourced assets (read-only, delete only) ---
        if _has_tr_assets:
            st.markdown("**Trade Republic positions** — managed by sync, shares are read-only")
            for _, asset in assets_df[assets_df["source"] == "tr"].iterrows():
                asset_id = int(asset["id"])
                c1, c2, c3 = st.columns([5, 2, 1])
                c1.markdown(f"{asset['name']} · `{asset['ticker']}` · {asset['shares']} shares")
                c2.metric("Value", f"€{asset['current_value']:,.2f}" if pd.notna(asset.get("current_value")) else "—")
                if c3.button("Delete", key=f"del_asset_{asset_id}"):
                    delete_asset(asset_id)
                    st.rerun()
            st.divider()

        # --- Manually-added assets (full edit/delete) ---
        _manual_df = assets_df[assets_df["source"] != "tr"] if "source" in assets_df.columns else assets_df
        if not _manual_df.empty:
            st.markdown("**Manually added positions**")
            for _, asset in _manual_df.iterrows():
                asset_id = int(asset["id"])
                c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
                with c1:
                    label = f"**{asset['name']}** · {asset['ticker']} · {asset['shares']} shares"
                    if asset["monthly_contribution"] > 0:
                        label += f"  ·  €{asset['monthly_contribution']:,.0f}/mo"
                    st.markdown(label)
                c2.metric("Value", f"€{asset['current_value']:,.2f}" if pd.notna(asset.get("current_value")) else "—")
                if c3.button("Edit", key=f"edit_asset_{asset_id}"):
                    st.session_state["editing_asset_id"] = asset_id
                if c4.button("Delete", key=f"del_asset_{asset_id}"):
                    delete_asset(asset_id)
                    st.session_state.pop("editing_asset_id", None)
                    st.rerun()

                if st.session_state.get("editing_asset_id") == asset_id:
                    with st.container(border=True):
                        st.caption(f"Editing: {asset['name']} ({asset['ticker']})")
                        a_shares, a_contrib, a_notes = _asset_form(f"asset_edit_{asset_id}", asset)
                        b1, b2 = st.columns(2)
                        if b1.button("Save", key=f"save_asset_{asset_id}"):
                            upsert_asset(name=asset["name"], ticker=asset["ticker"],
                                         shares=a_shares, monthly_contribution=a_contrib,
                                         notes=a_notes, asset_id=asset_id)
                            st.cache_data.clear()
                            st.session_state.pop("editing_asset_id", None)
                            st.rerun()
                        if b2.button("Cancel", key=f"cancel_asset_{asset_id}"):
                            st.session_state.pop("editing_asset_id", None)
                            st.rerun()
            st.divider()

        # --- Add new ---
        st.subheader("Add new ETF / stock")
        _add_source = st.radio(
            "Source",
            ["Manual (Yahoo Finance ticker)", "Trade Republic (auto-synced)"],
            horizontal=True,
            key="asset_add_source",
        )

        if _add_source == "Trade Republic (auto-synced)":
            st.info(
                "Trade Republic positions are synced automatically. "
                "Go to the **Banks** tab → Trade Republic → **Sync Trade Republic data** "
                "to pull the latest positions."
            )
        else:
            catalog_options = ["— Search popular ETFs —"] + [
                f"{e['name']} ({e['ticker']}) [{e['category']}]" for e in ETF_CATALOG
            ] + ["Other (enter manually)"]
            catalog_choice = st.selectbox("Pick from catalog", catalog_options, key="etf_catalog_pick")

            if catalog_choice not in ("— Search popular ETFs —", "Other (enter manually)"):
                idx_cat       = catalog_options.index(catalog_choice) - 1
                preset        = ETF_CATALOG[idx_cat]
                preset_name   = preset["name"]
                preset_ticker = preset["ticker"]
            else:
                preset_name   = ""
                preset_ticker = ""

            a_name   = st.text_input("Asset name", value=preset_name, key="asset_new_name")
            a_ticker = st.text_input("Yahoo Finance ticker", value=preset_ticker, key="asset_new_ticker",
                                     help="Append exchange suffix, e.g. .DE for Xetra. Example: EUNL.DE")
            a_shares, a_contrib, a_notes = _asset_form("asset_new")

            if st.button("Save asset", key="save_asset_new"):
                upsert_asset(name=a_name, ticker=a_ticker, shares=a_shares,
                             monthly_contribution=a_contrib, notes=a_notes)
                st.cache_data.clear()
                st.success("Saved")
                st.rerun()

    st.divider()

    # --- Goals ---
    st.header("Goals")

    goals_df = get_goals()
    current_savings = net_worth

    if goals_df.empty:
        st.info("No goals yet. Add one below.")
    else:
        for _, goal in goals_df.iterrows():
            progress = min(current_savings / goal["target_amount"], 1.0)
            remaining = max(goal["target_amount"] - current_savings, 0)

            with st.container():
                gcol1, gcol2 = st.columns([4, 1])
                with gcol1:
                    st.subheader(f"{goal['name']}")
                    st.caption(goal["notes"] or "")
                    st.progress(progress, text=f"{progress * 100:.1f}%")
                    pcol1, pcol2, pcol3 = st.columns(3)
                    pcol1.metric("Saved", f"€{current_savings:,.0f}")
                    pcol2.metric("Target", f"€{goal['target_amount']:,.0f}")
                    pcol3.metric("Remaining", f"€{remaining:,.0f}")
                with gcol2:
                    if st.button("Delete", key=f"del_goal_{goal['id']}"):
                        delete_goal(int(goal["id"]))
                        st.rerun()

    with st.expander("Add / edit goal"):
        g_name   = st.text_input("Goal name", value="Buy a flat")
        g_target = st.number_input("Target amount (€)", min_value=0.0, value=150000.0, step=1000.0)
        g_notes  = st.text_input("Notes (optional)", value="Down payment + fees for buying an apartment")
        if st.button("Save goal"):
            upsert_goal(g_name, g_target, g_notes)
            st.success("Goal saved")
            st.rerun()

    st.divider()

    # --- Income & Spending ---
    st.header("Income & Spending")

    # Monthly net salary (manually set, persisted)
    monthly_salary = float(get_state("monthly_salary") or 0)
    with st.expander("Set monthly net salary"):
        new_salary = st.number_input("Monthly net salary (€)", value=monthly_salary, step=100.0, format="%.2f")
        if st.button("Save salary"):
            set_state("monthly_salary", str(new_salary))
            monthly_salary = new_salary
            st.success("Saved")
            st.rerun()

    # Monthly expense budget
    monthly_budget = float(get_state("monthly_expense_budget") or 0)
    with st.expander("Set monthly expense budget"):
        new_budget = st.number_input("Monthly expense budget (€)", value=monthly_budget, step=100.0, format="%.2f")
        if st.button("Save budget limit"):
            set_state("monthly_expense_budget", str(new_budget))
            monthly_budget = new_budget
            st.success("Saved")
            st.rerun()

    # Joint account share setting
    if _joint_account_ids:
        _share_options = [100, 50]
        _share_labels = ["100% (full ownership)", "50% (shared equally)"]
        _share_idx = 1 if _joint_share_pct == 50 else 0
        _new_share = st.radio(
            "Joint account ownership share",
            options=_share_options,
            format_func=lambda v: _share_labels[_share_options.index(v)],
            index=_share_idx,
            horizontal=True,
            help="Applies to accounts marked as Joint in the Banks tab. At 50%, balances and transaction amounts from those accounts count as half in wealth and spending calculations.",
        )
        if _new_share != _joint_share_pct:
            set_state("joint_account_share", str(_new_share))
            st.rerun()

    # Internal transfer treatment setting
    transfers_as_expenses = get_state("transfers_as_expenses") == "1"
    new_transfers_as_expenses = st.checkbox(
        "Count Internal Transfers as expenses",
        value=transfers_as_expenses,
        help="When enabled, debit transactions categorized as 'Internal Transfer' are included in your spending totals. Disable to exclude them (useful when transfers between own accounts shouldn't count as spending).",
    )
    if new_transfers_as_expenses != transfers_as_expenses:
        set_state("transfers_as_expenses", "1" if new_transfers_as_expenses else "0")
        transfers_as_expenses = new_transfers_as_expenses
        st.rerun()

    # Split debits into expenses vs investments
    INVESTMENT_CATEGORIES = {"Investments", "Joint Account"}
    TRANSFER_CATEGORY = "Internal Transfer"
    debit_df = df[df["type"] == "debit"].copy()
    debit_df["amount_abs"] = debit_df["amount"].abs()
    debit_df["bucket"] = debit_df["category"].apply(
        lambda c: "invested" if c in INVESTMENT_CATEGORIES else (
            "transfer" if c == TRANSFER_CATEGORY and not transfers_as_expenses else "spent"
        )
    )

    monthly_buckets = (
        debit_df.groupby(["month", "bucket"])["amount_abs"]
        .sum().unstack(fill_value=0).reset_index()
    )
    for col in ("spent", "invested"):
        if col not in monthly_buckets.columns:
            monthly_buckets[col] = 0.0

    # Current month metrics
    this_row = monthly_buckets[monthly_buckets["month"] == current_month]
    this_month_spend    = this_row["spent"].values[0]    if not this_row.empty else 0.0
    this_month_invested = this_row["invested"].values[0] if not this_row.empty else 0.0
    unaccounted = max(monthly_salary - this_month_spend - this_month_invested, 0) if monthly_salary else None
    spent_pct    = this_month_spend    / monthly_salary * 100 if monthly_salary else None
    invested_pct = this_month_invested / monthly_salary * 100 if monthly_salary else None

    budget_remaining = monthly_budget - this_month_spend if monthly_budget else None
    budget_pct = this_month_spend / monthly_budget * 100 if monthly_budget else None

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Monthly Salary",   f"€{monthly_salary:,.0f}" if monthly_salary else "Not set")
    col2.metric("Spent",            f"€{this_month_spend:,.0f}",
                delta=f"{spent_pct:.1f}% of salary" if spent_pct is not None else None,
                delta_color="off")
    col3.metric("Invested / Saved", f"€{this_month_invested:,.0f}",
                delta=f"{invested_pct:.1f}% of salary" if invested_pct is not None else None,
                delta_color="off")
    col4.metric("Budget",           f"€{monthly_budget:,.0f}" if monthly_budget else "Not set")
    col5.metric("Budget Remaining",
                f"€{budget_remaining:,.0f}" if budget_remaining is not None else "—",
                delta=f"{budget_pct:.1f}% used" if budget_pct is not None else None,
                delta_color="inverse" if budget_remaining is not None and budget_remaining >= 0 else "off")

    if monthly_budget:
        with st.container(border=True):
            over = budget_remaining < 0
            bc1, bc2 = st.columns([4, 1])
            with bc1:
                st.progress(min(budget_pct / 100, 1.0), text=f"{'Over budget' if over else 'On track'} · {budget_pct:.1f}% used")
                pc1, pc2, pc3 = st.columns(3)
                pc1.metric("Spent", f"€{this_month_spend:,.0f}")
                pc2.metric("Budget", f"€{monthly_budget:,.0f}")
                pc3.metric("Remaining", f"€{budget_remaining:,.0f}", delta_color="off")


    st.divider()

    # Overview
    st.header("Spending Overview")

    now = pd.Timestamp.now()
    period_options = ["This month", "Last month", "Last 3 months", "Last 6 months", "Manual range"]
    pcol1, pcol2, pcol3 = st.columns([2, 2, 2])
    selected_period = pcol1.selectbox("Period", period_options, label_visibility="collapsed")
    if selected_period == "This month":
        date_from = now.replace(day=1).normalize()
        date_to = now
    elif selected_period == "Last month":
        first_of_this = now.replace(day=1).normalize()
        date_to = first_of_this - pd.Timedelta(days=1)
        date_from = date_to.replace(day=1)
    elif selected_period == "Last 3 months":
        date_from = now - pd.DateOffset(months=3)
        date_to = now
    elif selected_period == "Last 6 months":
        date_from = now - pd.DateOffset(months=6)
        date_to = now
    else:  # Manual range
        date_from = pd.Timestamp(pcol2.date_input("From", value=(now - pd.DateOffset(months=1)).date()))
        date_to = pd.Timestamp(pcol3.date_input("To", value=now.date()))

    # --- Filtered view ---
    filtered_df = df[(df["date"] >= date_from.strftime("%Y-%m-%d")) & (df["date"] <= date_to.strftime("%Y-%m-%d"))]
    debits = filtered_df[filtered_df["type"] == "debit"].copy()
    # Exclude internal transfers from income so moving money between own accounts doesn't inflate stats
    credits = filtered_df[
        (filtered_df["type"] == "credit") &
        (filtered_df["category"] != TRANSFER_CATEGORY)
    ].copy()
    debits["amount_abs"] = debits["amount"].abs()

    col1, col2, col3 = st.columns(3)

    total_in = credits["amount"].sum()
    _expense_mask = ~debits["category"].isin(INVESTMENT_CATEGORIES | (set() if transfers_as_expenses else {TRANSFER_CATEGORY}))
    total_out = debits[_expense_mask]["amount_abs"].sum()
    savings_rate = ((total_in - total_out) / total_in * 100) if total_in > 0 else 0

    range_label = f"{date_from.strftime('%b %d')} – {date_to.strftime('%b %d, %Y')}"
    if selected_period == "This month":
        range_label += " (current month)"
    st.caption(f"Period: {range_label}")

    col1.metric("Total Income", f"€{total_in:,.2f}")
    col2.metric("Total Expenses", f"€{total_out:,.2f}")
    col3.metric("Savings Rate", f"{savings_rate:.1f}%")

    # --- Projected spend (only when period includes today and month is incomplete) ---
    _today = now.date()
    _period_includes_today = date_from.date() <= _today <= date_to.date()
    _is_partial_month = date_from.day == 1 and date_to.date() == _today and date_from.month == date_to.month

    if _period_includes_today and _is_partial_month:
        import calendar
        _days_elapsed = _today.day
        _days_in_month = calendar.monthrange(_today.year, _today.month)[1]
        _days_remaining = _days_in_month - _days_elapsed

        # Only count real living expenses — exclude investments and optionally internal transfers
        _expense_debits = debits[
            ~debits["category"].isin(INVESTMENT_CATEGORIES | (set() if transfers_as_expenses else {TRANSFER_CATEGORY}))
        ]
        _actual_expenses = _expense_debits["amount_abs"].sum()
        _daily_rate = _actual_expenses / _days_elapsed if _days_elapsed > 0 else 0
        _projected = _daily_rate * _days_in_month
        _pct_through = _days_elapsed / _days_in_month * 100

        monthly_budget = float(get_state("monthly_expense_budget") or 0)

        st.markdown("**Projected spend this month**")
        pcol_a, pcol_b, pcol_c = st.columns(3)
        pcol_a.metric("Daily rate", f"€{_daily_rate:,.2f}/day")
        pcol_b.metric("Projected total", f"€{_projected:,.2f}",
                      delta=f"€{_projected - monthly_budget:+,.0f} vs budget" if monthly_budget else None,
                      delta_color="inverse")
        pcol_c.metric("Days remaining", f"{_days_remaining} of {_days_in_month}")

        if monthly_budget:
            _budget_used_pct = min(_actual_expenses / monthly_budget * 100, 100)
            _projected_pct   = min(_projected / monthly_budget * 100, 100)
            st.caption(f"Budget: €{monthly_budget:,.0f}  ·  {_pct_through:.0f}% through month  ·  {_budget_used_pct:.0f}% of budget spent")
            # Two-layer progress bar: actual (solid) vs projected (lighter)
            st.markdown(
                f"""
                <div style="background:#eee;border-radius:6px;height:14px;position:relative;overflow:hidden">
                  <div style="background:#e74c3c;width:{_projected_pct:.1f}%;height:100%;position:absolute;opacity:0.3;border-radius:6px"></div>
                  <div style="background:#e74c3c;width:{_budget_used_pct:.1f}%;height:100%;position:absolute;border-radius:6px"></div>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:0.75rem;color:#888;margin-top:2px">
                  <span>€0</span><span>Spent €{total_out:,.0f}</span><span>Projected €{_projected:,.0f}</span><span>Budget €{monthly_budget:,.0f}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    monthly = filtered_df.groupby(["month", "type"])["amount"].apply(
        lambda x: x.abs().sum()
    ).reset_index()
    monthly.columns = ["month", "type", "amount"]

    fig = px.bar(monthly, x="month", y="amount", color="type",
                 barmode="group", title="Monthly Income vs Expenses",
                 color_discrete_map={"credit": "#2ecc71", "debit": "#e74c3c"})
    _apply_chart_theme(fig)
    st.plotly_chart(fig, use_container_width=True)

    # Where is my money going
    st.header("Where is my money going?")
    include_investments = st.checkbox("Include investments in category charts", value=True, key="cat_include_investments")
    cat_filter = (all_debits["category"].str.strip() != "")
    if not include_investments:
        cat_filter &= ~all_debits["category"].isin(INVESTMENT_CATEGORIES)
    this_month_cat = all_debits[
        (all_debits["date"] >= date_from.strftime("%Y-%m-%d")) &
        (all_debits["date"] <= date_to.strftime("%Y-%m-%d")) &
        cat_filter
    ]
    if not this_month_cat.empty:
        cat_data = (this_month_cat.groupby("category")["amount_abs"].sum().reset_index())
        cat_data.columns = ["category", "amount"]
        fig = px.pie(cat_data, values="amount", names="category",
                     title=f"Spending by Category — {range_label}")
        _apply_chart_theme(fig)
        st.plotly_chart(fig, use_container_width=True)
        categories = sorted(this_month_cat["category"].unique().tolist())
        selected_category = st.selectbox(
            "Show transactions for category",
            ["— select —"] + categories,
            key="cat_drill"
        )
        if selected_category != "— select —":
            cat_txs = this_month_cat[this_month_cat["category"] == selected_category]
            st.dataframe(
                cat_txs[["date", "merchant", "description", "amount_abs"]]
                .rename(columns={"amount_abs": "amount (€)"})
                .sort_values("date", ascending=False),
                use_container_width=True,
                hide_index=True
            )

        # Stacked bar: monthly expenses by category
        cat_monthly = (
            all_debits[cat_filter]
            .groupby(["month", "category"])["amount_abs"]
            .sum().reset_index()
        )
        if not cat_monthly.empty:
            fig = px.bar(cat_monthly, x="month", y="amount_abs", color="category",
                         barmode="stack", title="Monthly Expenses by Category",
                         labels={"amount_abs": "Amount (€)", "month": "Month"})
            monthly_totals = cat_monthly.groupby("month")["amount_abs"].sum().reset_index()
            for _, row in monthly_totals.iterrows():
                fig.add_annotation(
                    x=row["month"], y=row["amount_abs"],
                    text=f"€{row['amount_abs']:,.0f}",
                    showarrow=False, yshift=10, font=dict(size=11)
                )
            _apply_chart_theme(fig)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No categories yet. Ask the AI to categorize your transactions.")


    # Transaction table
    st.header("Transactions")
    KNOWN_CATEGORIES = [""] + get_categories()
    tx_display = (
        df[["id", "date", "merchant", "description", "amount", "currency", "category", "type", "account_id"]]
        .sort_values("date", ascending=False)
        .reset_index(drop=True)
    )
    tx_display["account"] = tx_display["account_id"].map(_account_names).fillna(tx_display["account_id"])
    edited = st.data_editor(
        tx_display.drop(columns=["id", "account_id"]),
        use_container_width=True,
        hide_index=True,
        disabled=["date", "merchant", "description", "amount", "currency", "type", "account"],
        column_config={
            "category": st.column_config.SelectboxColumn(
                "Category",
                options=KNOWN_CATEGORIES,
                required=False,
            )
        },
        key="tx_editor",
    )
    changed = edited["category"].reset_index(drop=True) != tx_display["category"].reset_index(drop=True)
    if changed.any():
        for idx in tx_display.index[changed]:
            update_transaction_category(tx_display.at[idx, "id"], edited.at[idx, "category"] or "")
        st.toast(f"Saved {changed.sum()} category change(s)", icon="✅")
        st.rerun()

# --- Chat tab ---
with tab_chat:
    st.header("Ask about your finances")
    st.caption("Ask anything — spending summaries, top merchants, budget status, or categorize transactions.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []      # display messages
        st.session_state.agent_messages = []    # full API message history

    # Render chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("e.g. How much did I spend last month?"):
        # Show user message
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Run agent
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    st.session_state.agent_messages.append(
                        {"role": "user", "content": prompt}
                    )
                    reply, updated_messages = run_agent(
                        st.session_state.agent_messages,
                        api_key=get_api_key()
                    )
                    st.session_state.agent_messages = updated_messages
                    st.markdown(reply)
                    st.session_state.chat_history.append({"role": "assistant", "content": reply})
                except Exception as e:
                    st.error(f"Agent error: {e}")

    if st.session_state.chat_history:
        if st.button("Clear chat"):
            st.session_state.chat_history = []
            st.session_state.agent_messages = []
            st.rerun()

# --- Summaries tab ---
with tab_summaries:
    st.header("Email Summaries")

    def _summary_section(label: str, prompt_key: str, default_prompt: str, subject_prefix: str):
        st.subheader(label)

        saved_prompt = get_state(prompt_key) or default_prompt
        with st.expander("Edit prompt"):
            edited = st.text_area("Prompt", value=saved_prompt, height=400, key=f"{prompt_key}_editor",
                                  help="Use {context} where you want the financial data JSON inserted.")
            c1, c2 = st.columns(2)
            if c1.button("Save prompt", key=f"{prompt_key}_save"):
                set_state(prompt_key, edited)
                st.success("Prompt saved.")
            if c2.button("Reset to default", key=f"{prompt_key}_reset"):
                set_state(prompt_key, default_prompt)
                st.success("Reset to default.")
                st.rerun()

        active_prompt = get_state(prompt_key) or default_prompt
        subject = f"{subject_prefix} — {pd.Timestamp.now().strftime('%d %b %Y')}"

        if st.button(f"Generate & send {label.lower()}", key=f"{prompt_key}_send"):
            with st.spinner("Generating with Claude..."):
                try:
                    send_summary_email(
                        to_address=st.secrets["email"]["to"],
                        gmail_user=st.secrets["email"]["user"],
                        gmail_app_password=st.secrets["email"]["app_password"],
                        api_key=get_api_key(),
                        prompt_template=active_prompt,
                        subject=subject,
                    )
                    st.success("Sent!")
                except Exception as e:
                    st.error(f"Failed: {e}")

    _summary_section("Weekly summary",  "prompt_weekly",  DEFAULT_WEEKLY_PROMPT,  "Weekly Finance Summary")
    st.divider()
    _summary_section("Monthly summary", "prompt_monthly", DEFAULT_MONTHLY_PROMPT, "Monthly Finance Review")

    st.divider()
    st.subheader("History")
    summaries_df = get_summaries()
    if summaries_df.empty:
        st.info("No summaries sent yet.")
    else:
        for _, row in summaries_df.iterrows():
            generated_at = pd.to_datetime(row["generated_at"]).strftime("%d %b %Y, %H:%M")
            with st.expander(f"📧 {row['subject']}  —  {generated_at}"):
                st.text(row["body"])

# --- Banks tab ---
with tab_banks:
    st.header("Connected Banks")

    connections = get_bank_connections()
    bank_accs = get_bank_accounts()

    if connections.empty:
        st.info("No banks connected yet. Use the form below to add one.")
    else:
        for _, conn_row in connections.iterrows():
            accs = bank_accs[bank_accs["session_id"] == conn_row["session_id"]]
            with st.container(border=True):
                c1, c2, c3 = st.columns([6, 1, 1])
                c1.markdown(f"**{conn_row['display_name']}** — {conn_row['bank_name']} ({conn_row['bank_country']})  \n"
                            f"`{len(accs)} account(s)` · connected {conn_row['created_at'][:10]}")
                if c2.button("Sync accounts", key=f"sync_accs_{conn_row['id']}"):
                    try:
                        from finapp.banking.fetcher import get_accounts_for_session
                        import requests as _requests
                        from finapp.banking.fetcher import _headers
                        from finapp.config import BASE_URL
                        _sid = conn_row["session_id"]
                        _acc_ids = get_accounts_for_session(_sid)
                        _existing_ids = set(accs["account_id"].tolist())
                        _added = 0
                        for _i, _acc_id in enumerate(_acc_ids):
                            _iban = ""
                            _currency = ""
                            _acc_name = ""
                            try:
                                _r = _requests.get(f"{BASE_URL}/accounts/{_acc_id}", headers=_headers())
                                _r.raise_for_status()
                                _acc_data = _r.json()
                                _ident = (_acc_data.get("account_identifications") or [{}])[0]
                                _iban = _ident.get("identification", "")
                                _currency = _acc_data.get("currency", "")
                                _acc_name = _acc_data.get("name") or _acc_data.get("product") or ""
                            except Exception:
                                pass
                            if _acc_name:
                                _label = _acc_name
                            elif _iban:
                                _label = f"{conn_row['display_name']} ({_iban[-4:]})"
                            else:
                                _label = f"{conn_row['display_name']} {_i + 1}"
                            if _currency:
                                _label += f" {_currency}"
                            if _acc_id not in _existing_ids:
                                _added += 1
                            upsert_bank_account(account_id=_acc_id, session_id=_sid,
                                                display_name=_label, iban=_iban, currency=_currency)
                        st.cache_data.clear()
                        st.success(f"Found {len(_acc_ids)} account(s) total, added {_added} new.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to sync accounts: {e}")
                if c3.button("Delete", key=f"del_conn_{conn_row['id']}"):
                    delete_bank_connection(int(conn_row["id"]))
                    st.rerun()

                if not accs.empty:
                    _main_acc = get_main_account()
                    for _, acc in accs.iterrows():
                        a1, a2, a3, a4, a5 = st.columns([3, 2, 1, 1, 1])
                        new_name = a1.text_input("Name", value=acc["display_name"],
                                                 key=f"acc_name_{acc['account_id']}",
                                                 label_visibility="collapsed")
                        a2.caption(acc["iban"] or acc["account_id"][:16] + "…")
                        if a3.button("Save", key=f"acc_save_{acc['account_id']}"):
                            update_bank_account_name(acc["account_id"], new_name)
                            st.cache_data.clear()
                            st.rerun()
                        is_main = acc["account_id"] == _main_acc
                        if is_main:
                            a4.markdown("⭐ main")
                        elif a4.button("Set main", key=f"set_main_{acc['account_id']}"):
                            set_main_account(acc["account_id"])
                            st.rerun()
                        is_joint = bool(acc.get("is_joint", 0))
                        new_joint = a5.checkbox("Joint", value=is_joint,
                                                key=f"acc_joint_{acc['account_id']}",
                                                help="Mark as a joint account — apply share factor to its balances and transactions")
                        if new_joint != is_joint:
                            update_bank_account_joint(acc["account_id"], new_joint)
                            st.cache_data.clear()
                            st.rerun()

    # -----------------------------------------------------------------------
    # Trade Republic
    # -----------------------------------------------------------------------
    st.divider()
    st.subheader("Trade Republic")

    _tr_phone = st.secrets.get("trade_republic", {}).get("phone_no", "")
    _tr_pin   = st.secrets.get("trade_republic", {}).get("pin", "")

    if not _tr_phone or not _tr_pin:
        st.info("Add `[trade_republic]` with `phone_no` and `pin` to `.streamlit/secrets.toml` to enable TR integration.")
    else:
        # Check session validity once per browser session (avoids HTTP call on every rerun)
        if "tr_session_valid" not in st.session_state:
            from pytr.api import TradeRepublicApi
            _check_api = TradeRepublicApi(phone_no=_tr_phone, pin=_tr_pin, save_cookies=True)
            st.session_state["tr_session_valid"] = _check_api.resume_websession()

        _tr_session_valid = st.session_state.get("tr_session_valid", False)

        # -- Status + re-login button --
        _st1, _st2 = st.columns([4, 1])
        if _tr_session_valid:
            _st1.success("Connected to Trade Republic")
        else:
            _st1.warning("Session expired — please log in again")

        if _st2.button("Re-login", key="tr_relogin"):
            st.session_state["tr_login_step"] = "send_code"
            st.session_state["tr_session_valid"] = False
            st.rerun()

        # -- Login state machine --
        _login_step = st.session_state.get("tr_login_step", "idle" if _tr_session_valid else "send_code")

        if _login_step == "send_code":
            if st.button("Send login code to TR app / SMS", key="tr_send_code"):
                with st.spinner("Sending login request…"):
                    try:
                        _tr_api, _countdown = tr_initiate_weblogin(_tr_phone, _tr_pin)
                        st.session_state["tr_pending_api"]       = _tr_api
                        st.session_state["tr_pending_countdown"] = _countdown
                        st.session_state["tr_login_step"]        = "enter_code"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to send code: {e}")

        elif _login_step == "enter_code":
            _countdown = st.session_state.get("tr_pending_countdown", 300)
            st.info(f"Enter the 4-digit code from the Trade Republic app or SMS (valid for {_countdown}s).")
            _code = st.text_input("4-digit code", max_chars=4, key="tr_login_code")
            if st.button("Confirm code", key="tr_confirm_code") and _code:
                with st.spinner("Completing login…"):
                    try:
                        tr_complete_weblogin(st.session_state["tr_pending_api"], _code)
                        st.session_state.pop("tr_pending_api", None)
                        st.session_state["tr_session_valid"] = True
                        st.session_state["tr_login_step"]    = "idle"
                        st.success("Logged in to Trade Republic!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Login failed: {e}")

        # -- Sync --
        if _tr_session_valid:
            if st.button("Sync Trade Republic data", key="tr_sync"):
                with st.spinner("Fetching portfolio, balances and transactions from Trade Republic…"):
                    try:
                        _tr_data = tr_sync(_tr_phone, _tr_pin)

                        # Sync portfolio positions into assets table
                        sync_tr_portfolio(_tr_data["positions"])

                        # Cache live prices for price overlay
                        _tr_price_map = {
                            p["isin"]: p["current_price"]
                            for p in _tr_data["positions"]
                            if p["current_price"]
                        }
                        save_tr_prices(_tr_price_map)

                        # Store TR events in main transactions table
                        if _tr_data["transactions"]:
                            upsert_tr_transactions(_tr_data["transactions"])
                            _main_tx_rows = []
                            for _ev in _tr_data["transactions"]:
                                _amt = float(_ev.get("amount", 0))
                                _main_tx_rows.append({
                                    "id": f"tr-{_ev['id']}",
                                    "account_id": "trade_republic",
                                    "date": (_ev.get("timestamp") or "")[:10],
                                    "amount": _amt,
                                    "currency": _ev.get("currency", "EUR"),
                                    "description": _ev.get("title", ""),
                                    "merchant": _ev.get("isin") or _ev.get("title", ""),
                                    "category": "Investments",
                                    "type": "debit" if _amt < 0 else "credit",
                                })
                            upsert_transactions(_main_tx_rows)

                        # Update TR cash balance in savings_accounts
                        _existing_sav = get_savings_accounts()
                        _tr_sav = _existing_sav[_existing_sav["name"] == "Trade Republic Cash"] if not _existing_sav.empty else pd.DataFrame()
                        if not _tr_sav.empty:
                            upsert_savings_account(
                                name="Trade Republic Cash",
                                type="flexible",
                                balance=_tr_data["cash"],
                                account_id=int(_tr_sav.iloc[0]["id"]),
                            )
                        else:
                            upsert_savings_account(
                                name="Trade Republic Cash",
                                type="flexible",
                                balance=_tr_data["cash"],
                                notes="TR cash account — synced automatically",
                            )

                        st.cache_data.clear()
                        n_pos  = len(_tr_data["positions"])
                        n_txns = len(_tr_data["transactions"])
                        st.success(
                            f"Synced {n_pos} position(s) · "
                            f"€{_tr_data['cash']:,.2f} cash · "
                            f"{n_txns} transaction(s)"
                        )
                        st.rerun()
                    except RuntimeError:
                        st.session_state["tr_session_valid"] = False
                        st.session_state["tr_login_step"]    = "send_code"
                        st.error("Trade Republic session expired. Please log in again.")
                    except Exception as e:
                        st.error(f"Sync failed: {e}")

        # -- Recent TR transactions --
        _tr_txns = get_tr_transactions()
        if not _tr_txns.empty:
            with st.expander(f"TR timeline ({len(_tr_txns)} events)"):
                st.dataframe(
                    _tr_txns[["timestamp", "title", "amount", "type", "isin"]],
                    use_container_width=True,
                    hide_index=True,
                )

    st.divider()
    st.subheader("Connect a new bank")

    # Fetch supported banks (cached)
    if "banks_list" not in st.session_state:
        try:
            st.session_state.banks_list = list_banks()
        except Exception:
            st.session_state.banks_list = []

    banks_list = st.session_state.banks_list
    countries = sorted({b["country"] for b in banks_list}) if banks_list else []

    f1, f2, f3 = st.columns(3)
    if countries:
        selected_country = f1.selectbox("Country", countries)
        banks_in_country = [b["name"] for b in banks_list if b["country"] == selected_country]
        selected_bank = f2.selectbox("Bank", sorted(banks_in_country))
    else:
        selected_country = f1.text_input("Country code (e.g. DE)")
        selected_bank = f2.text_input("Bank name (e.g. Revolut)")
    display_name = f3.text_input("Label (e.g. My Revolut)")

    if st.button("Get authorization link") and selected_bank and selected_country:
        try:
            url = initiate_auth(bank_name=selected_bank, bank_country=selected_country)
            st.session_state.pending_auth = {
                "url": url, "bank": selected_bank,
                "country": selected_country, "label": display_name or selected_bank,
            }
        except Exception as e:
            st.error(f"Failed to start authorization: {e}")

    if "pending_auth" in st.session_state:
        auth = st.session_state.pending_auth
        st.info(f"Authorize **{auth['bank']}** by opening the link below, then paste the redirect URL back here.")
        st.markdown(f"[Open authorization link]({auth['url']})")
        redirect_url = st.text_input("Paste the redirect URL after authorizing")
        if st.button("Complete connection") and redirect_url:
            try:
                session_id, n_accs = complete_auth(
                    redirect_url=redirect_url,
                    bank_name=auth["bank"],
                    bank_country=auth["country"],
                    display_name=auth["label"],
                )
                del st.session_state.pending_auth
                st.success(f"Connected! Found {n_accs} account(s). You can rename them above.")
                st.rerun()
            except Exception as e:
                st.error(f"Connection failed: {e}")

    st.divider()
    st.subheader("Historical data sync")

    _main = get_main_account()
    _all_accs = get_bank_accounts()
    if _main is None:
        st.info("Set a main account above to enable historical sync.")
    else:
        _main_name = _all_accs.loc[_all_accs["account_id"] == _main, "display_name"].values
        _main_label = _main_name[0] if len(_main_name) else _main[:16] + "…"
        st.caption(f"Main account: **{_main_label}**")
        st.write("Reconstructs daily balance from transaction history and backfills the Net Worth chart.")

        _h1, _h2 = st.columns([2, 3])
        _months = _h1.selectbox("How far back", [1, 3, 6, 12, 24], index=2,
                                 format_func=lambda m: f"{m} month{'s' if m > 1 else ''}")
        if _h2.button("Sync historical data", use_container_width=False):
            with st.spinner(f"Backfilling {_months} months of history…"):
                try:
                    n = backfill_wealth_snapshots(
                        _main, _months,
                        current_liquid_savings=st.session_state.get("current_liquid_savings", 0.0),
                        current_investments=st.session_state.get("current_investments", 0.0),
                    )
                    st.success(f"Done — {n} daily snapshots added.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Backfill failed: {e}")

# --- Settings tab ---
with tab_settings:
    st.header("Settings")

    st.subheader("API Keys")
    _settings_api_key = get_api_key()
    if _settings_api_key:
        st.success("Anthropic API key is set.")
        if st.button("Remove key", key="_settings_remove_key"):
            set_state("anthropic_api_key", "")
            st.rerun()
    else:
        st.caption("Paste your Anthropic API key to enable AI chat and auto-categorization. Get one at [console.anthropic.com](https://console.anthropic.com).")
        _settings_key_input = st.text_input("Anthropic API key", type="password", placeholder="sk-ant-...", key="_settings_api_key_input")
        if st.button("Save key", key="_settings_save_key") and _settings_key_input.strip():
            set_state("anthropic_api_key", _settings_key_input.strip())
            st.rerun()

    st.divider()

    st.subheader("Transaction Categories")
    st.caption("These categories appear in the transaction editor and AI categorization.")

    _cats = get_categories()

    # Add new category
    with st.form("add_category_form", clear_on_submit=True):
        _new_cat = st.text_input("New category name")
        if st.form_submit_button("Add") and _new_cat.strip():
            add_category(_new_cat.strip())
            st.rerun()

    # List existing categories with rename + delete
    if not _cats:
        st.info("No categories yet.")
    else:
        for _cat in _cats:
            _c1, _c2, _c3 = st.columns([4, 2, 1])
            _new_name = _c1.text_input(
                "Name", value=_cat, key=f"cat_name_{_cat}", label_visibility="collapsed"
            )
            if _c2.button("Rename", key=f"cat_rename_{_cat}"):
                if _new_name.strip() and _new_name.strip() != _cat:
                    rename_category(_cat, _new_name.strip())
                    st.rerun()
            if _c3.button("Delete", key=f"cat_del_{_cat}"):
                delete_category(_cat)
                st.rerun()

    st.divider()

    st.subheader("Keyword Rules")
    st.caption(
        "Rules automatically assign a category when a transaction's merchant name contains a keyword "
        "(case-insensitive). They run before AI categorization — anything unmatched is sent to Claude."
    )
    st.info("To add or edit rules, open `src/finapp/rules.py` in your editor.", icon="✏️")

