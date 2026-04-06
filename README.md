# Money Snap

A personal finance dashboard that connects to your real bank accounts via Open Banking (PSD2), tracks spending and investments, and lets you chat with an AI agent about your finances. All data is stored locally — nothing leaves your machine except the API calls you explicitly trigger. Works best with Revolut & Trade Republic combination.

## What you get

- **Dashboard** — net worth, spending breakdown, savings rate, month-over-month wealth growth
- **Income & Spending** — categorized transactions, budget tracking, top merchants, projected monthly spend
- **Investments** - your investment portfolio (either live pulled from your Trade Republic account or through manual entry/tickers)
- **Goals** — track progress toward financial targets (e.g. buy a flat, emergency fund)
- **Chat** — ask questions like "what did I spend on dining last month?" powered by Claude
- **Weekly and Monthly Summaries** - generate financial summaries on weekly and/or monhtly basis and send them to your email address
- **Banks** — connect bank accounts via OAuth, sync Trade Republic portfolio
- **Settings** — manage categories, rules, salary, budgets, email summaries

---

## Quick start

```bash
# 1. Install dependencies
uv sync

# 2. Copy the secrets template and fill in your values
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# 3. Copy the categorization rules template
cp src/finapp/rules.example.py src/finapp/rules.py

# 4. Start the app
uv run streamlit run app.py
```

Opens at **http://localhost:8501** — the **Get Started** tab walks you through the rest.

> First time? You'll need `uv` and an Enable Banking account. See [full setup](#setup) below.

---

## Prerequisites

Before you start, you'll need:

- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — Python package manager
- **Python 3.13+** (uv will handle this automatically)
- **An Enable Banking account** — free tier works; needed to connect any PSD2-supported bank (Revolut, N26, most EU banks). Setup explained in Step 2.
- **An Enable Banking private key** — generated when you create an application in the Enable Banking dashboard (instructions below)
- Optionally: **Anthropic API key** (for AI chat + categorization), **Trade Republic account**, **Gmail** (for email summaries)

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/juliakzl/moneysnap.git
cd moneysnap
uv sync
```

### 2. Set up your Enable Banking application

Enable Banking is the PSD2 aggregator that handles bank OAuth. You need a registered application to get an `app_id` and a private key.

1. Sign up at [enablebanking.com](https://enablebanking.com) and log in to the dashboard
2. Go to **API Applications** → **Add a new application**
3. Fill in the application form:
   - **Environment:** Production
   - **RSA Key:** select "Generate in browser" — Enable Banking generates the key pair for you
   - **Name:** e.g. "Money Snap"
   - **Redirect URI:** `https://localhost:3000/callback`
   - **Description:** e.g. "Private finance app"
   - **Email for data protection:** your email address
   - **Privacy URL / Terms URL:** `https://localhost:3000/callback` (placeholder is fine)
4. Click **Register** — the private key downloads automatically at this point
5. Save the downloaded file as `private_prod.pem` in the project root — **never commit it** (it's in `.gitignore`)
6. Copy your **Application ID** (UUID on the application detail page) — you'll need it for `secrets.toml`

> **Important:** The private key is shown only once. If you lose it, you'll need to create a new application.

**Activate your application** (required before the API will work):

Enable Banking requires you to link at least one account via their dashboard before your application status changes from Inactive to Active. This is a one-time step — you will connect your bank again inside the Money Snap app later, and that is the connection the app actually uses.

1. In your newly created application, click **Activate by linking accounts**
2. Select your country, bank, and **Personal** under usage type — click **Link**
3. You will be redirected to an authorization page — click **Continue authentication**
4. Complete your bank's authentication (you'll likely need to confirm via your banking app)
5. Select the accounts to share and click **Authorize**
6. Once done, you'll be redirected back to Enable Banking — your application should now show **Active**



### 3. Create your secrets file

Copy the example and fill in your values:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
open .streamlit/secrets.toml   # macOS — opens in your default text editor
# or: nano .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

```toml
[app]
user_name = "Your Name"

[enable_banking]
app_id = "your-app-uuid"       # from enablebanking.com → your application

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

### 4. Set up your categorization rules

```bash
cp src/finapp/rules.example.py src/finapp/rules.py
```

Edit `src/finapp/rules.py` and add keyword → category rules for your own merchants. This file is gitignored — it won't be overwritten when you pull updates.

**Important:** add a rule matching your own name as it appears in bank transfer descriptions and assign it to `"Internal Transfer"` — this prevents transfers between your own accounts from inflating income and expense totals.

### 5. Start the app

```bash
uv run streamlit run app.py
```

Opens at **http://localhost:8501**

---

## First-time setup in the app

Once the app is running, work through these steps (the **Get Started** tab walks you through them):

1. **Connect your bank** — go to the Banks tab → select your country and bank → click "Get authorization link" → authorize in your bank's interface. Your browser will then redirect to `https://localhost:3000/callback?code=...` and show a connection error — **that's expected**. Copy the full URL from the address bar and paste it into the app to complete the connection. Then click "Sync transactions".
2. **Connect Trade Republic** (optional) — see [Trade Republic setup](#trade-republic-setup) below
3. **Add investment portfolio** — if not using Trade Republic, go to Settings → Assets → add positions by ticker symbol
4. **Set your monthly salary** — Dashboard → Income & Spending → "Set monthly net salary"
5. **Set a monthly budget** — Dashboard → Income & Spending → "Set monthly expense budget"
6. **Set a financial goal** — Dashboard → Goals → add a goal with a target amount
7. **Configure categories** — Settings → Transaction Categories → add your categories; then edit `src/finapp/rules.py` to add keyword → category rules for automatic matching (copy from `rules.example.py` if you haven't already)
8. **Add Anthropic API key** — in `secrets.toml` under `[anthropic]` — enables AI chat and auto-categorization
9. **Set up email summaries** (optional) — requires a Gmail App Password (not your regular login password):
   1. Enable 2-Step Verification on your Google account if not already on ([myaccount.google.com/security](https://myaccount.google.com/security))
   2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   3. Create a new app password — name it anything (e.g. "Finance App")
   4. Copy the generated 16-character password and paste it into `secrets.toml` under `[email] app_password`

---

## Trade Republic setup

Trade Republic integration syncs your portfolio positions and trade history directly from your TR account.

### 1. Add credentials to secrets.toml

```toml
[trade_republic]
phone_no = "+4917612345678"   # your full phone number including country code
pin = "1234"                  # your 4-digit Trade Republic PIN
```

Restart the app after saving.

### 2. Log in inside the app

Go to the **Banks** tab → scroll down to the **Trade Republic** section:

1. Click **Send login code to TR app / SMS** — Trade Republic sends a 4-digit confirmation code to your TR app or via SMS
2. Enter the code and click **Confirm code**
3. Once connected, click **Sync portfolio** to import your positions and trade history

The session is saved as a cookie (`~/.pytr/`) so you won't need to log in again unless the session expires. If it does, a "Re-login" button appears in the same section.

> **Note:** Trade Republic uses 2FA by design — your PIN alone is not enough. The 4-digit code step is always required on first login.

---

## Configuring transaction rules

Copy the example file and customize it:

```bash
cp src/finapp/rules.example.py src/finapp/rules.py
```

`src/finapp/rules.py` is gitignored — it won't be overwritten when you pull updates. Edit it to add keyword → category mappings for your own merchants:

```python
RULES = [
    ("edeka", "Groceries"),
    ("spotify", "Subscriptions"),
    ("your landlord name", "Rent"),
    # add your own...
]
```

Rules are matched case-insensitively against the transaction merchant name and run before AI categorization — anything not matched gets sent to Claude (if API key is set). You can also manually edit categories inline in the Transactions tab.

**Important:** Add a rule matching your own name as it appears in bank transfer descriptions and assign it to `"Internal Transfer"` — this prevents transfers between your own accounts from double-counting in income and spending stats.

---

## Security notes

- `finance.db` — contains real transaction data, never committed (in `.gitignore`)
- `private_prod.pem` — RSA private key provided by Enable Banking, never committed
- `.streamlit/secrets.toml` — all credentials, never committed
- `config.py` — non-secret config only (URLs, file paths)
- The repo should stay **private** on GitHub

---

## Troubleshooting

**App crashes on startup with a KeyError on secrets**
→ Check that `[enable_banking]` with `app_id` is present in `secrets.toml`. All other sections are optional.

**"No transactions yet" on the dashboard**
→ Go to the Banks tab, connect your bank, then click "Sync transactions".

**OAuth redirect doesn't work / localhost:3000 shows an error**
→ That's expected — the browser will show an error page, but the URL in the address bar contains the `code=` parameter you need. Copy the full URL from the address bar and paste it into the terminal or app.

**Trade Republic login fails**
→ Make sure `phone_no` includes the country code (e.g. `+49176...`). The 4-digit confirmation code is sent to your TR app or SMS.

**AI features not working**
→ Check that `[anthropic] api_key` is set in `secrets.toml`. The key starts with `sk-ant-`.
