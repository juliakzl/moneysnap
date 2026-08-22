"""Trade Republic integration via pytr.

Web login uses the v2 flow (pytr 0.4.10+ / --v2):
  1. tr_initiate_weblogin(phone_no, pin) → (api_instance, countdown_seconds)
     - POSTs /api/v2/auth/web/login; TR sends a push to the mobile app
  2. User confirms the login in the TR app (or enters an authenticator code)
  3. tr_complete_weblogin(api_instance) polls until confirmed, then saves ~/.pytr/
  4. tr_sync(phone_no, pin) auto-resumes from saved cookies on future calls
"""
import asyncio


def _trade_republic_api_cls():
    """Return TradeRepublicApi, reloading pytr if this process still has 0.4.9."""
    import inspect
    from importlib import reload
    import pytr.api as api_mod

    if "use_v2_login" not in inspect.signature(api_mod.TradeRepublicApi.__init__).parameters:
        api_mod = reload(api_mod)
    cls = api_mod.TradeRepublicApi
    if "use_v2_login" not in inspect.signature(cls.__init__).parameters:
        raise RuntimeError(
            "pytr 0.4.10 is required for TR login. Stop the app and restart with "
            "`uv run streamlit run app.py`."
        )
    return cls


def _make_api(phone_no: str, pin: str):
    TradeRepublicApi = _trade_republic_api_cls()
    return TradeRepublicApi(phone_no=phone_no, pin=pin, save_cookies=True, use_v2_login=True)


def tr_session_is_alive(phone_no: str, pin: str) -> bool:
    """True if saved cookies still resume a live Trade Republic session."""
    try:
        api = _make_api(phone_no, pin)
        return bool(api.resume_websession())
    except Exception:
        return False


def tr_is_logged_in(phone_no: str, pin: str) -> bool:
    """Check whether a valid saved session exists (no network call needed)."""
    from pathlib import Path
    cookies_file = Path.home() / ".pytr" / f"cookies.{phone_no}.txt"
    return cookies_file.exists()


def tr_initiate_weblogin(phone_no: str, pin: str) -> tuple:
    """
    Start the v2 web login flow (push approval in the TR app).
    Returns (api_instance, countdown_seconds).
    Keep api_instance alive and pass it to tr_complete_weblogin after the
    user confirms in the app, or with an authenticator code if required.
    """
    api = _make_api(phone_no, pin)
    countdown = api.initiate_weblogin()
    return api, countdown


def tr_weblogin_needs_authenticator(api) -> bool:
    """True when this login must be finished with an authenticator-app code."""
    return bool(getattr(api, "weblogin_needs_authenticator", False))


def tr_complete_weblogin(api, code: str | None = None) -> None:
    """Finish v2 login: poll for app confirmation, or submit a TOTP code."""
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


def _extract_positions(portfolio_raw) -> list[dict]:
    """Flatten compactPortfolioByType payload (pytr #361 / PR #362).

    Positions are grouped under categories[].positions[]; the new API uses
    ``isin`` where the old compactPortfolio topic used ``instrumentId``.
    """
    if isinstance(portfolio_raw, list):
        return [p for p in portfolio_raw if isinstance(p, dict)]
    if not isinstance(portfolio_raw, dict):
        return []
    categories = portfolio_raw.get("categories")
    if isinstance(categories, list):
        items: list[dict] = []
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            for pos in cat.get("positions", []):
                if not isinstance(pos, dict):
                    continue
                if "isin" in pos and "instrumentId" not in pos:
                    pos["instrumentId"] = pos["isin"]
                items.append(pos)
        return items
    return [
        p
        for p in portfolio_raw.get("positions", portfolio_raw.get("items", []))
        if isinstance(p, dict)
    ]


async def _fetch_portfolio_and_cash(api) -> dict:
    positions = []

    # pytr 0.4.10+ subscribes to compactPortfolioByType with secAccNo (#361)
    sub_id = await api.compact_portfolio()
    _, _, portfolio_raw = await api.recv()
    await api.unsubscribe(sub_id)

    sub_id = await api.cash()
    _, _, cash_raw = await api.recv()
    await api.unsubscribe(sub_id)

    cash = float(_to_dict(cash_raw).get("amount", 0))
    items = _extract_positions(portfolio_raw)

    for pos in items:
        # new payload uses "isin"; legacy used "instrumentId"
        isin = pos.get("isin") or pos.get("instrumentId", "")
        shares = float(pos.get("netSize", pos.get("size", 0)))
        if not isin:
            continue

        # Instrument name + available exchanges
        sub_id = await api.instrument_details(isin)
        _, _, details_raw = await api.recv()
        await api.unsubscribe(sub_id)
        details = _to_dict(details_raw)
        name = details.get("shortName") or pos.get("name") or isin
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
