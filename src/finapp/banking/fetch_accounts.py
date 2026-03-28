import jwt, time, requests, json, sys, tomllib, pathlib

secrets_path = pathlib.Path(".streamlit/secrets.toml")
if not secrets_path.exists():
    print("Error: .streamlit/secrets.toml not found. Run from the project root.")
    sys.exit(1)

with open(secrets_path, "rb") as f:
    secrets = tomllib.load(f)

APP_ID = secrets["enable_banking"]["app_id"]
BASE_URL = "https://api.enablebanking.com"
REDIRECT_URL = "https://localhost:3000/callback"

with open("private_prod.pem") as f:
    private_key = f.read()

def make_token():
    return jwt.encode(
        {"iss": "enablebanking.com", "aud": "api.enablebanking.com",
         "iat": int(time.time()), "exp": int(time.time()) + 3600},
        private_key, algorithm="RS256", headers={"kid": APP_ID}
    )

headers = {"Authorization": f"Bearer {make_token()}"}

# Step 1: verify auth works
resp = requests.get(f"{BASE_URL}/application", headers=headers)
print(f"App status: {resp.status_code}")
if resp.status_code != 200:
    print(resp.text)
    sys.exit(1)
print(json.dumps(resp.json(), indent=2))

# Step 2: initiate auth for Revolut Germany
print("\n--- Initiating Revolut authorization ---")
auth_payload = {
    "access": {
        "valid_until": (
            time.strftime("%Y-%m-%dT%H:%M:%SZ",
                          time.gmtime(time.time() + 90 * 86400))
        )
    },
    "aspsp": {
        "name": "Revolut",
        "country": "DE"
    },
    "state": "my-finance-app",
    "redirect_url": REDIRECT_URL,
    "psu_type": "personal"
}

resp = requests.post(f"{BASE_URL}/auth", headers=headers, json=auth_payload)
print(f"Auth status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2))

if resp.status_code == 200:
    auth_url = resp.json().get("url")
    print(f"\n>>> Open this URL in your browser:\n{auth_url}")
    print("\nAfter authorizing, your browser will redirect to localhost and show an error.")
    print("Copy the full URL from the address bar and paste it here:")
    redirect = input("Paste redirect URL: ").strip()

    # Extract code from URL
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(redirect)
    code = parse_qs(parsed.query).get("code", [None])[0]
    if not code:
        print("No code found in URL")
        sys.exit(1)

    print(f"\nGot code: {code[:20]}...")

    # Step 3: create session
    headers = {"Authorization": f"Bearer {make_token()}"}
    resp = requests.post(f"{BASE_URL}/sessions", headers=headers, json={"code": code})
    print(f"\nSession status: {resp.status_code}")
    session_data = resp.json()
    print(json.dumps(session_data, indent=2))

    if resp.status_code == 200:
        session_id = session_data.get("session_id")
        print(f"\n>>> Session ID: {session_id}")
        print("Save this — we'll use it to fetch transactions next.")
