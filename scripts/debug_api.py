import jwt, time, requests, json
from finapp.config import APP_ID, BASE_URL, SESSION_ID, PRIVATE_KEY_PATH

with open(PRIVATE_KEY_PATH) as f:
    private_key = f.read()

def make_token():
    return jwt.encode(
        {"iss": "enablebanking.com", "aud": "api.enablebanking.com",
         "iat": int(time.time()), "exp": int(time.time()) + 3600},
        private_key, algorithm="RS256", headers={"kid": APP_ID}
    )

# Get first account
resp = requests.get(f"{BASE_URL}/sessions/{SESSION_ID}", headers={"Authorization": f"Bearer {make_token()}"})
account_id = resp.json()["accounts"][0]

# Fetch a few transactions
resp = requests.get(
    f"{BASE_URL}/accounts/{account_id}/transactions",
    headers={"Authorization": f"Bearer {make_token()}"},
    params={"date_from": "2023-01-01", "date_to": "2026-01-01"}
)
txs = resp.json().get("transactions", [])
print(f"Got {len(txs)} transactions")
print("\nFirst 2 raw transactions:")
print(json.dumps(txs[:2], indent=2))
