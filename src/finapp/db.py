import json
import sqlite3
from datetime import datetime
import pandas as pd
from finapp.config import DB_PATH


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                account_id TEXT,
                date TEXT,
                amount REAL,
                currency TEXT,
                description TEXT,
                merchant TEXT,
                category TEXT,
                type TEXT  -- 'debit' or 'credit'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                monthly_limit REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                notes TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS savings_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 0,
                balance_date TEXT,
                monthly_contribution REAL NOT NULL DEFAULT 0,
                interest_rate REAL,
                duration_months INTEGER,
                maturity_date TEXT,
                notes TEXT
            )
        """)
        # Migrate: add columns if upgrading from older schema
        for col, definition in [
            ("balance_date", "TEXT"),
            ("monthly_contribution", "REAL NOT NULL DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE savings_accounts ADD COLUMN {col} {definition}")
            except Exception:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wealth_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                liquid REAL NOT NULL,
                investments REAL NOT NULL,
                net_worth REAL NOT NULL,
                is_backfill INTEGER NOT NULL DEFAULT 0
            )
        """)
        try:
            conn.execute("ALTER TABLE wealth_snapshots ADD COLUMN is_backfill INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                ticker TEXT NOT NULL,
                shares REAL NOT NULL DEFAULT 0,
                monthly_contribution REAL NOT NULL DEFAULT 0,
                notes TEXT,
                source TEXT
            )
        """)
        try:
            conn.execute("ALTER TABLE assets ADD COLUMN source TEXT")
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tr_transactions (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                title TEXT,
                amount REAL,
                currency TEXT NOT NULL DEFAULT 'EUR',
                type TEXT,
                isin TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bank_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                bank_name TEXT NOT NULL,
                bank_country TEXT NOT NULL,
                display_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bank_accounts (
                account_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                iban TEXT,
                currency TEXT,
                is_main INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                name TEXT PRIMARY KEY
            )
        """)
        # Seed default categories if table is empty
        count = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if count == 0:
            defaults = [
                "Groceries", "Dining", "Transport", "Shopping", "Vinted",
                "Subscriptions", "Health", "Entertainment", "Travel", "Rent",
                "Investments", "Internal Transfer", "Joint Account", "Other",
            ]
            conn.executemany("INSERT OR IGNORE INTO categories (name) VALUES (?)",
                             [(c,) for c in defaults])
        try:
            conn.execute("ALTER TABLE bank_accounts ADD COLUMN is_main INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE bank_accounts ADD COLUMN is_joint INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
    _migrate_bank_connections()


def get_state(key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_state(key: str, value: str):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?,?)", (key, value))


def upsert_transactions(rows: list[dict]):
    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO transactions
                (id, account_id, date, amount, currency, description, merchant, category, type)
            VALUES
                (:id, :account_id, :date, :amount, :currency, :description, :merchant, :category, :type)
            ON CONFLICT(id) DO UPDATE SET
                account_id  = excluded.account_id,
                date        = excluded.date,
                amount      = excluded.amount,
                currency    = excluded.currency,
                description = excluded.description,
                merchant    = excluded.merchant,
                type        = excluded.type
                -- category is intentionally excluded: preserve existing categorization
        """, rows)


def get_uncategorized_merchants() -> list[str]:
    """Return distinct merchant names that have at least one uncategorized transaction."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT merchant FROM transactions
            WHERE (category IS NULL OR category = '') AND type = 'debit'
            ORDER BY merchant
        """).fetchall()
    return [r[0] for r in rows if r[0]]


def bulk_set_categories(merchant_category_map: dict[str, str]):
    """Set category for all transactions of each merchant in the map."""
    with get_conn() as conn:
        for merchant, category in merchant_category_map.items():
            conn.execute(
                "UPDATE transactions SET category=? WHERE merchant=?",
                (category, merchant)
            )


def get_transactions() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM transactions ORDER BY date DESC", conn)


def get_budgets() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM budgets", conn)


def get_goals() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM goals ORDER BY id", conn)


def save_summary(subject: str, body: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO summaries (generated_at, subject, body) VALUES (?,?,?)",
            (datetime.now().isoformat(), subject, body)
        )


def get_summaries() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM summaries ORDER BY generated_at DESC", conn)


def upsert_goal(name: str, target_amount: float, notes: str = "", goal_id: int = None):
    with get_conn() as conn:
        if goal_id:
            conn.execute(
                "UPDATE goals SET name=?, target_amount=?, notes=? WHERE id=?",
                (name, target_amount, notes, goal_id)
            )
        else:
            conn.execute(
                "INSERT INTO goals (name, target_amount, notes) VALUES (?,?,?)",
                (name, target_amount, notes)
            )


def delete_goal(goal_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM goals WHERE id=?", (goal_id,))


def get_savings_accounts() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM savings_accounts ORDER BY id", conn)


def upsert_savings_account(name: str, type: str, balance: float,
                           balance_date: str = None,
                           monthly_contribution: float = 0.0,
                           interest_rate: float = None, duration_months: int = None,
                           maturity_date: str = None, notes: str = "",
                           account_id: int = None):
    if balance_date is None:
        balance_date = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        if account_id:
            conn.execute(
                """UPDATE savings_accounts
                   SET name=?, type=?, balance=?, balance_date=?, monthly_contribution=?,
                       interest_rate=?, duration_months=?, maturity_date=?, notes=?
                   WHERE id=?""",
                (name, type, balance, balance_date, monthly_contribution,
                 interest_rate, duration_months, maturity_date, notes, account_id)
            )
        else:
            conn.execute(
                """INSERT INTO savings_accounts
                   (name, type, balance, balance_date, monthly_contribution,
                    interest_rate, duration_months, maturity_date, notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (name, type, balance, balance_date, monthly_contribution,
                 interest_rate, duration_months, maturity_date, notes)
            )


def delete_savings_account(account_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM savings_accounts WHERE id=?", (account_id,))


def save_wealth_snapshot(liquid: float, investments: float, net_worth: float):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO wealth_snapshots
               (date, liquid, investments, net_worth, is_backfill)
               VALUES (?, ?, ?, ?, 0)""",
            (today, liquid, investments, net_worth)
        )


def get_wealth_snapshots() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM wealth_snapshots ORDER BY date", conn)


def get_assets() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM assets ORDER BY id", conn)


def upsert_asset(name: str, ticker: str, shares: float,
                 monthly_contribution: float = 0.0, notes: str = "",
                 asset_id: int = None):
    with get_conn() as conn:
        if asset_id:
            conn.execute(
                """UPDATE assets
                   SET name=?, ticker=?, shares=?, monthly_contribution=?, notes=?
                   WHERE id=?""",
                (name, ticker, shares, monthly_contribution, notes, asset_id)
            )
        else:
            conn.execute(
                """INSERT INTO assets (name, ticker, shares, monthly_contribution, notes)
                   VALUES (?,?,?,?,?)""",
                (name, ticker, shares, monthly_contribution, notes)
            )


def delete_asset(asset_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))


def upsert_budget(category: str, limit: float):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO budgets (category, monthly_limit)
            VALUES (?, ?)
        """, (category, limit))


# --- Bank connections ---

def _migrate_bank_connections():
    """One-time migration: seed bank_connections from old hardcoded config if table is empty.
    Called at the end of init_db() so the tables exist before we query them."""
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM bank_connections").fetchone()[0]
        if count > 0:
            return
    try:
        from finapp.config import SESSION_ID, ACCOUNT_NAMES  # type: ignore
        add_bank_connection(
            session_id=SESSION_ID,
            bank_name="Revolut",
            bank_country="DE",
            display_name="Revolut",
        )
        for acc_id, name in ACCOUNT_NAMES.items():
            upsert_bank_account(account_id=acc_id, session_id=SESSION_ID,
                                display_name=name, iban="", currency="")
    except Exception:
        pass


def get_bank_connections() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM bank_connections ORDER BY id", conn)


def add_bank_connection(session_id: str, bank_name: str, bank_country: str, display_name: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO bank_connections
               (session_id, bank_name, bank_country, display_name, status, created_at)
               VALUES (?, ?, ?, ?, 'active', ?)""",
            (session_id, bank_name, bank_country, display_name, datetime.now().isoformat()),
        )


def delete_bank_connection(conn_id: int):
    with get_conn() as conn:
        session_id = conn.execute(
            "SELECT session_id FROM bank_connections WHERE id=?", (conn_id,)
        ).fetchone()
        if session_id:
            conn.execute("DELETE FROM bank_accounts WHERE session_id=?", (session_id[0],))
        conn.execute("DELETE FROM bank_connections WHERE id=?", (conn_id,))


def get_bank_accounts() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM bank_accounts ORDER BY session_id, account_id", conn)


def upsert_bank_account(account_id: str, session_id: str, display_name: str,
                        iban: str = "", currency: str = ""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO bank_accounts (account_id, session_id, display_name, iban, currency)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(account_id) DO UPDATE SET
                   session_id   = excluded.session_id,
                   iban         = excluded.iban,
                   currency     = excluded.currency""",
            (account_id, session_id, display_name, iban, currency),
        )


def update_bank_account_name(account_id: str, display_name: str):
    with get_conn() as conn:
        conn.execute("UPDATE bank_accounts SET display_name=? WHERE account_id=?",
                     (display_name, account_id))


def update_bank_account_joint(account_id: str, is_joint: bool):
    with get_conn() as conn:
        conn.execute("UPDATE bank_accounts SET is_joint=? WHERE account_id=?",
                     (1 if is_joint else 0, account_id))


def get_account_display_names() -> dict[str, str]:
    """Returns {account_id: display_name} for all known bank accounts plus synthetic accounts."""
    with get_conn() as conn:
        rows = conn.execute("SELECT account_id, display_name FROM bank_accounts").fetchall()
        result = {r[0]: r[1] for r in rows}
        # Include Trade Republic as a synthetic account if any TR transactions exist
        has_tr = conn.execute(
            "SELECT 1 FROM transactions WHERE account_id='trade_republic' LIMIT 1"
        ).fetchone()
        if has_tr:
            result["trade_republic"] = "Trade Republic"
    return result


def set_main_account(account_id: str):
    """Mark one account as the main account, clearing the flag on all others."""
    with get_conn() as conn:
        conn.execute("UPDATE bank_accounts SET is_main = 0")
        conn.execute("UPDATE bank_accounts SET is_main = 1 WHERE account_id = ?", (account_id,))


def get_main_account() -> str | None:
    """Returns the account_id of the main account, or None if none is set."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT account_id FROM bank_accounts WHERE is_main = 1"
        ).fetchone()
    return row[0] if row else None


def save_wealth_snapshot_if_missing(date_str: str, liquid: float,
                                    investments: float, net_worth: float):
    """Insert a snapshot only if that date doesn't already have one (preserves live snapshots)."""
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO wealth_snapshots (date, liquid, investments, net_worth)
               VALUES (?, ?, ?, ?)""",
            (date_str, liquid, investments, net_worth),
        )


def save_wealth_snapshots_batch(rows: list[tuple]):
    """Batch insert (date, liquid, investments, net_worth) backfill rows.
    Overwrites existing backfilled snapshots but never touches live ones."""
    with get_conn() as conn:
        # Delete existing backfilled snapshots for these dates so we can replace them
        dates = [(r[0],) for r in rows]
        conn.executemany(
            "DELETE FROM wealth_snapshots WHERE date = ? AND is_backfill = 1", dates
        )
        # Insert new backfilled rows, skipping any date that has a live snapshot
        conn.executemany(
            """INSERT OR IGNORE INTO wealth_snapshots
               (date, liquid, investments, net_worth, is_backfill)
               VALUES (?, ?, ?, ?, 1)""",
            rows,
        )


def update_transaction_category(tx_id: str, category: str):
    """Manually set the category for a single transaction."""
    with get_conn() as conn:
        conn.execute("UPDATE transactions SET category=? WHERE id=?", (category, tx_id))


def get_transactions_for_account(account_id: str) -> pd.DataFrame:
    """Returns transactions for an account, excluding internal transfers."""
    with get_conn() as conn:
        return pd.read_sql(
            """SELECT date, amount FROM transactions
               WHERE account_id = ?
               AND (category IS NULL OR category != 'Internal Transfer')
               ORDER BY date""",
            conn, params=(account_id,)
        )


def get_internal_transfer_credits(account_id: str) -> pd.DataFrame:
    """Returns credit transactions tagged as Internal Transfer for an account.
    These represent money moved FROM savings/other accounts INTO this account."""
    with get_conn() as conn:
        return pd.read_sql(
            """SELECT date, amount FROM transactions
               WHERE account_id = ? AND amount > 0 AND category = 'Internal Transfer'
               ORDER BY date""",
            conn, params=(account_id,)
        )


# --- Trade Republic ---

def upsert_tr_transactions(rows: list[dict]):
    """Idempotently insert / replace TR timeline events."""
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO tr_transactions
                   (id, timestamp, title, amount, currency, type, isin)
               VALUES (:id, :timestamp, :title, :amount, :currency, :type, :isin)""",
            rows,
        )


def get_tr_transactions() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query(
            "SELECT * FROM tr_transactions ORDER BY timestamp DESC", conn
        )


def sync_tr_portfolio(positions: list[dict]):
    """
    Sync TR portfolio positions into the assets table.
    - Updates shares for existing TR-sourced rows (matched by ISIN / ticker).
    - Inserts new rows for previously-unseen positions.
    - Does NOT touch manually-added assets (source IS NULL).
    """
    with get_conn() as conn:
        for pos in positions:
            isin = pos["isin"]
            existing = conn.execute(
                "SELECT id FROM assets WHERE ticker=? AND source='tr'", (isin,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE assets SET name=?, shares=? WHERE id=?",
                    (pos["name"], pos["shares"], existing[0]),
                )
            else:
                conn.execute(
                    """INSERT INTO assets
                           (name, ticker, shares, monthly_contribution, notes, source)
                       VALUES (?, ?, ?, 0, 'Synced from Trade Republic', 'tr')""",
                    (pos["name"], isin, pos["shares"]),
                )


def save_tr_prices(prices: dict):
    """Persist live TR prices {isin: price} in app_state."""
    set_state("tr_prices", json.dumps(prices))


def get_tr_prices() -> dict:
    """Return cached TR live prices {isin: price}."""
    raw = get_state("tr_prices")
    return json.loads(raw) if raw else {}


# --- Categories ---

def get_categories() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    return [r[0] for r in rows]


def add_category(name: str):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))


def delete_category(name: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM categories WHERE name=?", (name,))


def rename_category(old_name: str, new_name: str):
    with get_conn() as conn:
        conn.execute("UPDATE categories SET name=? WHERE name=?", (new_name, old_name))
        conn.execute("UPDATE transactions SET category=? WHERE category=?", (new_name, old_name))
        conn.execute("UPDATE budgets SET category=? WHERE category=?", (new_name, old_name))
