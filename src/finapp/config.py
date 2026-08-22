import streamlit as st

BASE_URL = "https://api.enablebanking.com"
REDIRECT_URL = "https://localhost:3000/callback"
PRIVATE_KEY_PATH = "private_prod.pem"
DB_PATH = "finance.db"
MEMORY_PATH = "agent_memory.md"
MEMORY_EXAMPLE_PATH = "agent_memory.example.md"

APP_ID = st.secrets.get("enable_banking", {}).get("app_id", "")
