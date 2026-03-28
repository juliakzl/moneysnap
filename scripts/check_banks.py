import jwt, time, requests

APP_ID = "7b9ead7b-7efe-4d06-a1dd-51f03da5676e"

with open("private_prod.pem") as f:
    private_key = f.read()

token = jwt.encode(
    {"iss": "enablebanking.com", "aud": "api.enablebanking.com",
     "iat": int(time.time()), "exp": int(time.time()) + 3600},
    private_key, algorithm="RS256", headers={"kid": APP_ID}
)

resp = requests.get(
    "https://api.enablebanking.com/aspsps",
    headers={"Authorization": f"Bearer {token}"},
    params={"sandbox": "false"}
)

print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")
data = resp.json()
print(f"Total banks: {len(data.get('aspsps', []))}")
print()

for bank in data.get("aspsps", []):
    name = bank.get("name", "").lower()
    if any(term in name for term in ["revolut", "trade republic", "traderepublic", "trade_republic"]):
        print(bank)

# Print all banks with their country
print("\n--- All banks with country ---")
for bank in data.get("aspsps", []):
    print(f"{bank.get('country', '?'):5} | {bank.get('name')}")
