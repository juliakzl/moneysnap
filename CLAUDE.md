# Finance App — Project Context for Claude

## What this is
A personal finance dashboard built with Python/Streamlit. Connects to real bank accounts via the Enable Banking API (Open Banking / PSD2), stores data locally in SQLite, and visualizes spending with Plotly. Includes a Claude-powered AI agent for natural language finance queries and auto-categorization.

## Stack
- Python 3.14
- Streamlit 1.45.0 (UI framework, runs on localhost:8501)
- SQLite (`finance.db`) — local database, never committed
- Enable Banking API — PSD2 aggregator for EU bank connections
- Plotly — charts
- `anthropic` — Claude API for AI agent, transaction categorization, email summaries

## Project structure
- `app.py` — main Streamlit app (entry point, ~1400 lines, all tabs defined here)
- `pyproject.toml` — dependencies managed by uv
- `src/finapp/`
  - `config.py` — non-secret config (API base URL, redirect URL, key path)
  - `db.py` — all SQLite read/write logic (~600 lines)
  - `rules.py` — keyword-based transaction categorization rules (edit to customize)
  - `agent.py` — Claude AI agent with tool-use for finance queries
  - `notifier.py` — email summaries via Gmail SMTP
  - `banking/`
    - `fetcher.py` — Enable Banking API wrapper (bank discovery, OAuth, transaction fetch)
    - `fetch_accounts.py` — one-time CLI script for initial bank OAuth setup
    - `fetch_transactions.py` — standalone transaction fetch script
  - `investments/`
    - `tr_fetcher.py` — Trade Republic web login & portfolio sync
    - `etf_catalog.py` — static catalog of popular ETFs
- `scripts/` — one-off debug/setup scripts (not part of the package)

## Database schema

All tables in `finance.db`:

**transactions** — bank transactions from all connected accounts
- `id` TEXT PRIMARY KEY
- `account_id` TEXT — matches `bank_accounts.account_id` or `"trade_republic"`
- `date` TEXT (YYYY-MM-DD)
- `amount` REAL — negative = debit, positive = credit
- `currency` TEXT
- `description` TEXT
- `merchant` TEXT
- `category` TEXT
- `type` TEXT — `'debit'` or `'credit'`

**bank_connections** — one row per connected bank (Enable Banking session)
- `session_id` TEXT PRIMARY KEY
- `bank_name`, `bank_country`, `display_name` TEXT
- `created_at` TEXT

**bank_accounts** — one row per account within a connection
- `account_id` TEXT PRIMARY KEY
- `session_id` TEXT (FK → bank_connections)
- `display_name`, `iban`, `currency` TEXT
- `balance` REAL, `balance_date` TEXT
- `is_main` INTEGER (0/1)

**budgets** — per-category monthly limits (used by AI agent)
- `category` TEXT PRIMARY KEY
- `monthly_limit` REAL

**goals** — financial targets
- `id` INTEGER PRIMARY KEY
- `name`, `notes` TEXT
- `target_amount` REAL

**savings_accounts** — manually tracked savings/investment accounts
- `id` INTEGER PRIMARY KEY
- `name`, `type` TEXT (`'flexible'` = liquid, others = investment)
- `balance` REAL, `balance_date` TEXT
- `monthly_contribution` REAL, `interest_rate` REAL
- `duration_months` INTEGER, `maturity_date` TEXT, `notes` TEXT

**assets** — investment portfolio positions (Trade Republic or manual)
- `id` INTEGER PRIMARY KEY
- `name`, `ticker`, `isin` TEXT
- `quantity` REAL, `purchase_price` REAL
- `asset_type` TEXT

**wealth_snapshots** — daily net worth snapshots
- `date` TEXT PRIMARY KEY
- `liquid` REAL, `investments` REAL, `net_worth` REAL

**tr_transactions** — Trade Republic trade history
- `id` TEXT PRIMARY KEY
- `isin`, `type`, `timestamp` TEXT
- `shares`, `price`, `amount` REAL

**app_state** — key/value store for UI state and settings
- `key` TEXT PRIMARY KEY, `value` TEXT
- Notable keys: `monthly_salary`, `monthly_expense_budget`, `last_wealth_snapshot`

**categories** — user-defined transaction category names
- `name` TEXT PRIMARY KEY

## Secrets & security rules
- Private RSA keys: `private.pem`, `private_prod.pem` — NEVER commit, in .gitignore
- Database: `finance.db` — real financial data, NEVER commit
- All secrets in `.streamlit/secrets.toml` — NEVER in source files, NEVER committed
- `config.py` holds non-secret config only (paths, URLs)
- Keep the repo private on GitHub

## Secrets structure (`.streamlit/secrets.toml`)
```toml
[app]
user_name = "..."

[enable_banking]
app_id = "..."       # Enable Banking application UUID
session_id = "..."   # obtained via fetch_accounts.py; migrated to DB after first run

[accounts]           # account UUIDs from fetch_accounts.py; migrated to DB after first run
personal_id = "..."
joint_eur_id = "..."
joint_gbp_id = "..."

[anthropic]
api_key = "sk-ant-..."

[trade_republic]
phone_no = "+49..."
pin = "1234"

[email]
to = "..."
user = "...@gmail.com"
app_password = "..."
```

**Note on `[enable_banking]` and `[accounts]`:** These were used for the original author's initial setup. For new users connecting banks fresh through the UI, these fields are still required by `config.py` at import time (migration code). They can be left as empty strings if the user hasn't run `fetch_accounts.py` yet, but the keys must exist to prevent a `KeyError`. A future improvement is to make these optional.

## Key conventions
- All monetary amounts displayed in EUR (€)
- Debits stored as negative amounts, credits as positive
- `type` field is `'debit'` or `'credit'` (redundant with amount sign, kept for clarity)
- Date format: YYYY-MM-DD strings in DB
- `INSERT OR REPLACE` for idempotent transaction upserts
- Account filter in the dashboard (multiselect) filters `df` client-side via pandas `.isin()` — the DB always returns all rows

## How spending calculations work
- All transactions loaded: `SELECT * FROM transactions`
- Filtered client-side by account multiselect
- Debits/credits split by `type` field
- `INVESTMENT_CATEGORIES = {"Investments", "Joint Account"}` — excluded from "spent" bucket
- `TRANSFER_CATEGORY = "Internal Transfer"` — excluded from both income and spending stats
- Savings rate = `(total_income - total_expenses) / total_income`
- Projected monthly spend = `(actual_expenses / days_elapsed) * days_in_month`

## How wealth is calculated
Three components, always shown across all accounts (not filtered by account selector):
1. **Liquid** = all bank API balances + flexible savings accounts
2. **Investments** = portfolio value (assets table, priced via yfinance) + non-flexible savings
3. **Net worth** = Liquid + Investments
Savings account balances projected forward using `monthly_contribution` + compound `interest_rate` from `balance_date`.

## Running the app
```bash
uv sync
uv run streamlit run app.py
```

## Helping a new user get set up

If a user opens this repo for the first time, guide them through these steps in order:

1. **Install uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. **`uv sync`** — installs dependencies
3. **Generate RSA key pair** and upload public key to Enable Banking dashboard
4. **Create `.streamlit/secrets.toml`** from the `.example` file — at minimum fill in `[app]`, `[enable_banking]`, and `[accounts]` keys (even as empty strings to avoid `KeyError` on startup)
5. **Run `fetch_accounts.py`** to do initial OAuth and get `session_id` + account UUIDs, then update `secrets.toml`
6. **`uv run streamlit run app.py`** — opens at localhost:8501
7. **In-app:** connect bank → sync transactions → set salary → set budget → set goal → configure categories
8. **Optional:** add Anthropic key (AI features), Trade Republic credentials, email settings

The app has a **Get Started** tab that shows onboarding progress and surfaces these steps inline — direct new users there first.

## What NOT to suggest
- Do not suggest committing `finance.db`, `secrets.toml`, or any `.pem` files
- Do not hardcode secrets or account IDs in source files — always use `st.secrets`
- Do not add per-user auth/login — this is a single-user local app by design
- Do not change `INSERT OR REPLACE` patterns in db.py — idempotency is intentional
