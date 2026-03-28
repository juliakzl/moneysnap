import jwt
import time
import json
import requests
from urllib.parse import urlparse, parse_qs
from finapp.config import APP_ID, BASE_URL, PRIVATE_KEY_PATH, REDIRECT_URL
from datetime import date, timedelta
from finapp.db import (init_db, upsert_transactions, get_state, set_state,
                       get_bank_connections, add_bank_connection,
                       get_bank_accounts, upsert_bank_account,
                       get_transactions_for_account, get_internal_transfer_credits,
                       save_wealth_snapshots_batch)


def _make_token():
    with open(PRIVATE_KEY_PATH) as f:
        private_key = f.read()
    return jwt.encode(
        {"iss": "enablebanking.com", "aud": "api.enablebanking.com",
         "iat": int(time.time()), "exp": int(time.time()) + 3600},
        private_key, algorithm="RS256", headers={"kid": APP_ID}
    )


def _headers():
    return {"Authorization": f"Bearer {_make_token()}"}


# --- Bank discovery ---

def list_banks(country: str = None) -> list[dict]:
    """Return list of supported banks from Enable Banking. Each item has 'name' and 'country'."""
    params = {}
    if country:
        params["country"] = country
    resp = requests.get(f"{BASE_URL}/aspsps", headers=_headers(), params=params)
    resp.raise_for_status()
    return resp.json().get("aspsps", [])


# --- OAuth flow ---

def initiate_auth(bank_name: str, bank_country: str) -> str:
    """Start OAuth for a bank. Returns the authorization URL to show to the user."""
    valid_until = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 90 * 86400))
    payload = {
        "access": {"valid_until": valid_until},
        "aspsp": {"name": bank_name, "country": bank_country},
        "state": "finance-app",
        "redirect_url": REDIRECT_URL,
        "psu_type": "personal",
    }
    resp = requests.post(f"{BASE_URL}/auth", headers=_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()["url"]


def complete_auth(redirect_url: str, bank_name: str, bank_country: str,
                  display_name: str) -> tuple[str, int]:
    """
    Exchange the auth code from the redirect URL for a session.
    Discovers accounts and saves everything to the DB.
    Returns (session_id, number_of_accounts_found).
    """
    parsed = urlparse(redirect_url)
    code = parse_qs(parsed.query).get("code", [None])[0]
    if not code:
        raise ValueError("No authorization code found in the redirect URL.")

    resp = requests.post(f"{BASE_URL}/sessions", headers=_headers(), json={"code": code})
    resp.raise_for_status()
    session_data = resp.json()
    session_id = session_data["session_id"]
    raw_accounts = session_data.get("accounts", [])
    raise ValueError(f"DEBUG session_data: {session_data}")

    add_bank_connection(
        session_id=session_id,
        bank_name=bank_name,
        bank_country=bank_country,
        display_name=display_name,
    )

    for i, account_id in enumerate(account_ids):
        iban = ""
        currency = ""
        acc_name = ""
        try:
            r = requests.get(f"{BASE_URL}/accounts/{account_id}", headers=_headers())
            r.raise_for_status()
            acc_data = r.json()
            ident = (acc_data.get("account_identifications") or [{}])[0]
            iban = ident.get("identification", "")
            currency = acc_data.get("currency", "")
            acc_name = acc_data.get("name") or acc_data.get("product") or ""
        except Exception:
            pass

        if acc_name:
            acc_label = acc_name
        elif iban:
            acc_label = f"{display_name} ({iban[-4:]})"
        else:
            acc_label = f"{display_name} {i + 1}"
        if currency:
            acc_label += f" {currency}"
        upsert_bank_account(account_id=account_id, session_id=session_id,
                            display_name=acc_label, iban=iban, currency=currency)

    return session_id, len(account_ids)


# --- Account / balance helpers ---

def get_accounts_for_session(session_id: str) -> list[str]:
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}", headers=_headers())
    resp.raise_for_status()
    raw = resp.json().get("accounts", [])
    return [a["id"] if isinstance(a, dict) else a for a in raw]


def get_account_balance(account_id: str) -> float | None:
    """Fetch current balance for a specific account. Returns None if unavailable."""
    try:
        resp = requests.get(
            f"{BASE_URL}/accounts/{account_id}/balances",
            headers=_headers()
        )
        resp.raise_for_status()
        balances = resp.json().get("balances", [])
        for b in balances:
            if b.get("balance_type") in ("CLBD", "CLAV", "ITBD"):
                return float(b["balance_amount"]["amount"])
        if balances:
            return float(balances[0]["balance_amount"]["amount"])
        return None
    except Exception:
        return None


def get_account_map() -> dict[str, str]:
    """Returns {account_id: iban} mapping, fetched from API and cached in DB."""
    cached = get_state("account_map")
    if cached:
        return json.loads(cached)

    account_map = {}
    connections = get_bank_connections()
    active = connections[connections["status"] == "active"] if not connections.empty else connections
    for _, row in active.iterrows():
        try:
            for account_id in get_accounts_for_session(row["session_id"]):
                try:
                    resp = requests.get(f"{BASE_URL}/accounts/{account_id}", headers=_headers())
                    resp.raise_for_status()
                    data = resp.json()
                    iban = (data.get("account_identifications") or [{}])[0].get("identification", "")
                    if iban:
                        account_map[account_id] = iban
                except Exception:
                    pass
        except Exception:
            pass

    if account_map:
        set_state("account_map", json.dumps(account_map))
    return account_map


# --- Transaction fetching ---

def _parse_transaction(tx: dict, account_id: str) -> dict:
    amount = tx.get("transaction_amount", {})
    value = float(amount.get("amount", 0))
    indicator = tx.get("credit_debit_indicator", "DBIT").upper()
    if indicator == "DBIT":
        value = -abs(value)
        tx_type = "debit"
    else:
        value = abs(value)
        tx_type = "credit"

    remittance = tx.get("remittance_information", [])
    description = remittance[0] if remittance else ""

    creditor = tx.get("creditor", {}) or {}
    merchant = creditor.get("name", "") or description

    date = tx.get("booking_date") or tx.get("value_date") or ""

    return {
        "id": tx.get("entry_reference") or f"{account_id}-{date}-{value}",
        "account_id": account_id,
        "date": date,
        "amount": value,
        "currency": amount.get("currency", "EUR"),
        "description": description,
        "merchant": merchant,
        "category": "",
        "type": tx_type,
    }


def backfill_wealth_snapshots(account_id: str, months_back: int,
                              current_liquid_savings: float = 0.0,
                              current_investments: float = 0.0) -> int:
    """
    Reconstruct daily net worth from transaction history and save as wealth snapshots.

    Main account balance is reconstructed by walking backwards from current API balance.
    Liquid savings balance is reconstructed by adding back any Internal Transfer credits
    that happened after each target date (i.e. money that was in savings but has since
    been moved to the main account).
    Investments are carried as a constant (no historical data available).

    Returns the number of snapshots written.
    """
    current_balance = get_account_balance(account_id)
    if current_balance is None:
        raise ValueError("Could not fetch current balance from the API.")

    txs = get_transactions_for_account(account_id)
    if txs.empty:
        raise ValueError("No transactions found for this account.")
    txs["date"] = txs["date"].astype(str)

    transfers = get_internal_transfer_credits(account_id)
    transfers["date"] = transfers["date"].astype(str)

    today = date.today()
    requested_start = today - timedelta(days=months_back * 30)
    first_tx_date = date.fromisoformat(txs["date"].min())
    start = max(requested_start, first_tx_date)
    total_days = (today - start).days + 1

    rows = []
    for days_ago in range(total_days):
        target = today - timedelta(days=days_ago)
        target_str = target.strftime("%Y-%m-%d")

        # Main account: subtract all non-transfer transactions that happened after target date
        future_tx = txs[txs["date"] > target_str]["amount"].sum()
        bank_balance = current_balance - future_tx

        # Savings: add back any transfers FROM savings that happened after target date
        # (before those transfers, savings had that money)
        future_transfers = transfers[transfers["date"] > target_str]["amount"].sum()
        savings_balance = current_liquid_savings + future_transfers

        liquid = bank_balance + savings_balance
        net_worth = liquid + current_investments
        rows.append((target_str, liquid, current_investments, net_worth))

    save_wealth_snapshots_batch(rows)
    return len(rows)


def fetch_and_store(date_from="2024-01-01", date_to=None):
    if date_to is None:
        date_to = time.strftime("%Y-%m-%d")

    init_db()
    connections = get_bank_connections()
    active = connections[connections["status"] == "active"] if not connections.empty else connections

    if active.empty:
        return 0

    total = 0
    for _, conn_row in active.iterrows():
        try:
            account_ids = get_accounts_for_session(conn_row["session_id"])
        except Exception:
            continue

        for account_id in account_ids:
            continuation_key = None
            while True:
                params = {"date_from": date_from, "date_to": date_to}
                if continuation_key:
                    params["continuation_key"] = continuation_key

                resp = requests.get(
                    f"{BASE_URL}/accounts/{account_id}/transactions",
                    headers=_headers(),
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                txs = data.get("transactions", [])
                rows = [_parse_transaction(tx, account_id) for tx in txs]
                upsert_transactions(rows)
                total += len(rows)

                continuation_key = data.get("continuation_key")
                if not continuation_key:
                    break

    return total
