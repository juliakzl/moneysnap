import jwt, time, requests, json

APP_ID = "YOUR_ENABLE_BANKING_APP_ID"  # from https://enablebanking.com dashboard
BASE_URL = "https://api.enablebanking.com"
SESSION_ID = "YOUR_SESSION_ID"  # obtained by running fetch_accounts.py first

with open("private_prod.pem") as f:
    private_key = f.read()

def make_token():
    return jwt.encode(
        {"iss": "enablebanking.com", "aud": "api.enablebanking.com",
         "iat": int(time.time()), "exp": int(time.time()) + 3600},
        private_key, algorithm="RS256", headers={"kid": APP_ID}
    )

headers = {"Authorization": f"Bearer {make_token()}"}

# Get session + account IDs
resp = requests.get(f"{BASE_URL}/sessions/{SESSION_ID}", headers=headers)
print(f"Session status: {resp.status_code}")
session = resp.json()
print(json.dumps(session, indent=2))

accounts = session.get("accounts", [])
print(f"\nFound {len(accounts)} account(s)")

# Fetch transactions for each account
for account_id in accounts:
    print(f"\n--- Transactions for account {account_id} ---")
    headers = {"Authorization": f"Bearer {make_token()}"}
    resp = requests.get(
        f"{BASE_URL}/accounts/{account_id}/transactions",
        headers=headers,
        params={"date_from": "2025-01-01", "date_to": "2025-12-31"}
    )
    print(f"Status: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2))
