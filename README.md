# Finance App

A personal finance dashboard that connects to your real bank accounts via Open Banking (PSD2), tracks spending and investments, and lets you chat with an AI agent about your finances. All data is stored locally — nothing leaves your machine except the API calls you explicitly trigger.

## What you get

- **Dashboard** — net worth, spending breakdown, savings rate, month-over-month wealth growth
- **Income & Spending** — categorized transactions, budget tracking, top merchants, projected monthly spend
- **Goals** — track progress toward financial targets (e.g. buy a flat, emergency fund)
- **Chat** — ask questions like "what did I spend on dining last month?" powered by Claude
- **Banks** — connect bank accounts via OAuth, sync Trade Republic portfolio
- **Settings** — manage categories, rules, salary, budgets, email summaries

---

## Quick start

```bash
# 1. Install dependencies
uv sync

# 2. Copy the secrets template and fill in your values
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# 3. Start the app
uv run streamlit run app.py
```

Opens at **http://localhost:8501** — the **Get Started** tab walks you through the rest.

> First time? You'll need `uv` and an Enable Banking account. See [full setup](#setup) below.

---

## Prerequisites

Before you start, you'll need:

- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — Python package manager
- **Python 3.14+** (uv will handle this automatically)
- **An Enable Banking account** — free tier works; needed to connect any PSD2-supported bank (Revolut, N26, most EU banks). Sign up at [enablebanking.com](https://enablebanking.com).
- **An RSA key pair** — used to authenticate with Enable Banking (instructions below)
- Optionally: **Anthropic API key** (for AI chat + categorization), **Trade Republic account**, **Gmail** (for email summaries)

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/juliakzl/moneysnap.git
cd moneysnap
uv sync
```

### 2. Generate an RSA key pair

Enable Banking uses asymmetric key authentication. Generate a key pair:

```bash
openssl genrsa -out private_prod.pem 2048
openssl rsa -in private_prod.pem -pubout -out public_prod.pem
```

- Upload `public_prod.pem` to your Enable Banking dashboard under your application settings
- Keep `private_prod.pem` in the project root — **never commit it** (it's in `.gitignore`)

### 3. Create your secrets file

Copy the example and fill in your values:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

```toml
[app]
user_name = "Your Name"

[enable_banking]
app_id = "your-app-uuid"       # from enablebanking.com → your application
session_id = ""                # leave blank for now; filled in step 5

[accounts]
personal_id = ""               # leave blank for now; filled in step 5
joint_eur_id = ""              # optional — remove if you don't have a joint account
joint_gbp_id = ""              # optional — remove if you don't have a joint account

[anthropic]
api_key = "sk-ant-..."         # from console.anthropic.com — optional, enables AI features

[trade_republic]               # optional — remove section if not using TR
phone_no = "+49176..."
pin = "1234"

[email]                        # optional — remove section if not using email summaries
to = "you@example.com"
user = "you@gmail.com"
app_password = "xxxx xxxx xxxx xxxx"   # Gmail App Password (not your login password)
                                        # Generate at myaccount.google.com → Security → App passwords
```

### 4. Run the initial bank OAuth flow

This one-time script authenticates with Enable Banking, starts the OAuth flow with your bank, and prints the `session_id` and account IDs you need for secrets.toml:

```bash
uv run python src/finapp/banking/fetch_accounts.py
```

It will:
1. Print an authorization URL — open it in your browser
2. You'll be redirected to your bank's login page (e.g. Revolut)
3. After authorizing, you'll be redirected to `https://localhost:3000/callback?code=...`
4. Paste the full redirect URL back into the terminal
5. The script prints your `session_id` and account UUIDs — copy them into `secrets.toml`

### 5. Start the app

```bash
uv run streamlit run app.py
```

Opens at **http://localhost:8501**

---

## First-time setup in the app

Once the app is running, work through these steps (the **Get Started** tab walks you through them):

1. **Connect your bank** — Banks tab → add connection → authorize via OAuth → sync transactions
2. **Connect Trade Republic** (optional) — Banks tab → Trade Republic section → log in with your phone number and PIN
3. **Add investment portfolio** — if not using Trade Republic, go to Settings → Assets → add positions by ticker symbol
4. **Set your monthly salary** — Dashboard → Income & Spending → "Set monthly net salary"
5. **Set a monthly budget** — Dashboard → Income & Spending → "Set monthly expense budget"
6. **Set a financial goal** — Dashboard → Goals → add a goal with a target amount
7. **Configure categories** — Settings → Transaction Categories → add your categories; then edit `src/finapp/rules.py` to add keyword → category rules for automatic matching
8. **Add Anthropic API key** — in `secrets.toml` under `[anthropic]` — enables AI chat and auto-categorization
9. **Set up email summaries** (optional) — in `secrets.toml` under `[email]` with a Gmail App Password

---

## Configuring transaction rules

`src/finapp/rules.py` contains keyword rules for automatic transaction categorization. Rules are matched case-insensitively against the merchant name:

```python
RULES = [
    ("edeka", "Groceries"),
    ("spotify", "Subscriptions"),
    ("your landlord name", "Rent"),
    # add your own...
]
```

Rules run before AI categorization — anything not matched by a rule gets sent to Claude (if API key is set). You can also manually edit categories inline in the Transactions tab.

**Important:** Add a rule matching your own name as it appears in bank transfers (e.g. transfers to your own savings accounts) and assign it to `"Internal Transfer"` — this prevents double-counting in spending stats.

---

## Security notes

- `finance.db` — contains real transaction data, never committed (in `.gitignore`)
- `private_prod.pem` / `private.pem` — RSA private keys, never committed
- `.streamlit/secrets.toml` — all credentials, never committed
- `config.py` — non-secret config only (URLs, file paths)
- The repo should stay **private** on GitHub

---

## Troubleshooting

**App crashes on startup with a KeyError on secrets**
→ Check that all required fields in `secrets.toml` are filled in. The `[enable_banking]` and `[accounts]` sections are required even if values are blank strings.

**"No transactions yet" on the dashboard**
→ Go to the Banks tab, connect your bank, then click "Sync transactions".

**OAuth redirect doesn't work / localhost:3000 shows an error**
→ That's expected — the browser will show an error page, but the URL in the address bar contains the `code=` parameter you need. Copy the full URL from the address bar and paste it into the terminal or app.

**Trade Republic login fails**
→ Make sure `phone_no` includes the country code (e.g. `+49176...`). The 4-digit confirmation code is sent to your TR app or SMS.

**AI features not working**
→ Check that `[anthropic] api_key` is set in `secrets.toml`. The key starts with `sk-ant-`.
