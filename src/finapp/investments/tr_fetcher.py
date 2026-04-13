"""Trade Republic integration via pytr (RealCLanger/pytr@improve-login branch).

Web login flow (keeps mobile app logged in):
  1. tr_initiate_weblogin(phone_no, pin) → (api_instance, countdown_seconds)
     - Launches headless Chromium (Playwright) to obtain AWS WAF token automatically
  2. User enters the 4-digit code from TR app / SMS
  3. tr_complete_weblogin(api_instance, code) → saves session to ~/.pytr/
  4. tr_sync(phone_no, pin) auto-resumes from saved cookies on future calls

Note: requires `playwright install chromium` after `uv sync` (one-time setup).
"""
import asyncio


def _make_api(phone_no: str, pin: str):
    from pytr.api import TradeRepublicApi
    return TradeRepublicApi(phone_no=phone_no, pin=pin, save_cookies=True, waf_token="playwright")


def tr_is_logged_in(phone_no: str, pin: str) -> bool:
    """Check whether a valid saved session exists (no network call needed)."""
    from pathlib import Path
    cookies_file = Path.home() / ".pytr" / f"cookies.{phone_no}.txt"
    return cookies_file.exists()


def tr_initiate_weblogin(phone_no: str, pin: str) -> tuple:
    """
    Start the web login flow.
    Returns (api_instance, countdown_seconds).
    Keep api_instance alive (e.g. in st.session_state) and pass it to
    tr_complete_weblogin once the user has the 4-digit code.
    """
    api = _make_api(phone_no, pin)
    countdown = api.initiate_weblogin()
    return api, countdown


def tr_complete_weblogin(api, code: str) -> None:
    """Complete web login with the 4-digit code. Saves session cookies to disk."""
    api.complete_weblogin(code)


# ---------------------------------------------------------------------------
# Internal async helpers
# ---------------------------------------------------------------------------

def _to_dict(val) -> dict:
    """Normalise a WebSocket response to a dict (handles list-wrapped payloads)."""
    if isinstance(val, dict):
        return val
    if isinstance(val, list) and val and isinstance(val[0], dict):
        return val[0]
    return {}


async def _fetch_portfolio_and_cash(api) -> dict:
    positions = []

    sub_id = await api.compact_portfolio()
    _, _, portfolio_raw = await api.recv()
    await api.unsubscribe(sub_id)

    sub_id = await api.cash()
    _, _, cash_raw = await api.recv()
    await api.unsubscribe(sub_id)

    cash = float(_to_dict(cash_raw).get("amount", 0))

    # portfolio_raw may be a list of positions directly
    if isinstance(portfolio_raw, dict):
        items = portfolio_raw.get("positions", portfolio_raw.get("items", []))
    elif isinstance(portfolio_raw, list):
        items = portfolio_raw
    else:
        items = []

    for pos in items:
        if not isinstance(pos, dict):
            continue
        isin = pos.get("instrumentId", "")
        shares = float(pos.get("netSize", pos.get("size", 0)))
        if not isin:
            continue

        # Instrument name + available exchanges
        sub_id = await api.instrument_details(isin)
        _, _, details_raw = await api.recv()
        await api.unsubscribe(sub_id)
        details = _to_dict(details_raw)
        name = details.get("shortName", isin)
        exchanges = details.get("exchangeIds", [])

        # Live price
        current_price = 0.0
        if exchanges:
            try:
                sub_id = await api.ticker(isin, exchanges[0])
                _, _, ticker_raw = await api.recv()
                await api.unsubscribe(sub_id)
                ticker = _to_dict(ticker_raw)
                last = ticker.get("last", 0)
                current_price = float(last if not isinstance(last, dict) else last.get("price", 0))
            except Exception:
                pass

        positions.append({
            "isin": isin,
            "name": name,
            "shares": shares,
            "current_price": current_price,
            "value": shares * current_price,
        })

    return {"positions": positions, "cash": cash}


async def _fetch_transactions(api, max_items: int = 500) -> list[dict]:
    events: list[dict] = []
    after = None

    for _ in range(20):  # max 20 pages
        sub_id = await api.timeline_transactions(after=after)
        _, _, data = await api.recv()
        await api.unsubscribe(sub_id)

        if not data:
            break

        if isinstance(data, list):
            items = data
            after = None
        else:
            items = data.get("items", [])
            cursors = data.get("cursors", {})
            after = cursors.get("after") if isinstance(cursors, dict) else None

        for item in items:
            amount_field = item.get("amount")
            if isinstance(amount_field, dict):
                amount = float(amount_field.get("value", 0))
            else:
                amount = float(amount_field or 0)

            events.append({
                "id": item.get("id", ""),
                "timestamp": item.get("timestamp", ""),
                "title": item.get("title", ""),
                "amount": amount,
                "currency": "EUR",
                "type": item.get("eventType", item.get("type", "")),
                "isin": item.get("isin", ""),
            })

        if not after or len(events) >= max_items:
            break

    return events


# ---------------------------------------------------------------------------
# Public sync entry point
# ---------------------------------------------------------------------------

def tr_sync(phone_no: str, pin: str) -> dict:
    """
    Fetch portfolio positions, cash balance, and recent transactions from TR.
    Requires an active session (cookies on disk).  Raises RuntimeError if not.

    Returns:
        {
            "positions": [{"isin", "name", "shares", "current_price", "value"}, ...],
            "cash": float,
            "transactions": [{"id", "timestamp", "title", "amount", "currency",
                               "type", "isin"}, ...],
        }
    """
    api = _make_api(phone_no, pin)

    if not api.resume_websession():
        raise RuntimeError(
            "No active Trade Republic session. Please log in first."
        )

    async def _run():
        portfolio = await _fetch_portfolio_and_cash(api)
        txns = await _fetch_transactions(api)
        return {**portfolio, "transactions": txns}

    return asyncio.run(_run())
