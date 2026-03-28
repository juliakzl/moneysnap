import streamlit as st

BASE_URL = "https://api.enablebanking.com"
REDIRECT_URL = "https://localhost:3000/callback"
PRIVATE_KEY_PATH = "private_prod.pem"
DB_PATH = "finance.db"

APP_ID = st.secrets["enable_banking"]["app_id"]

# SESSION_ID and ACCOUNT_NAMES have been migrated to the database.
# They are kept here temporarily so the one-time migration in db.py can seed them.
# Once the app has been started once, these can be removed.
SESSION_ID = st.secrets["enable_banking"]["session_id"]
ACCOUNT_NAMES = {
    st.secrets["accounts"]["personal_id"]: "Personal",
    st.secrets["accounts"]["joint_eur_id"]: "Joint (EUR)",
    st.secrets["accounts"]["joint_gbp_id"]: "Joint (GBP)",
}
