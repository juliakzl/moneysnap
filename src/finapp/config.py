import streamlit as st

BASE_URL = "https://api.enablebanking.com"
REDIRECT_URL = "https://localhost:3000/callback"
PRIVATE_KEY_PATH = "private_prod.pem"
DB_PATH = "finance.db"

APP_ID = st.secrets.get("enable_banking", {}).get("app_id", "")

# SESSION_ID and ACCOUNT_NAMES have been migrated to the database.
# They are kept here temporarily so the one-time migration in db.py can seed them.
# Once the app has been started once, these can be removed.
_eb = st.secrets.get("enable_banking", {})
SESSION_ID = _eb.get("session_id", "")
_accounts = st.secrets.get("accounts", {})
ACCOUNT_NAMES = {
    v: label
    for v, label in [
        (_accounts.get("personal_id", ""), "Personal"),
        (_accounts.get("joint_eur_id", ""), "Joint (EUR)"),
        (_accounts.get("joint_gbp_id", ""), "Joint (GBP)"),
    ]
    if v  # skip entries with missing/empty IDs
}
