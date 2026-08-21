# Bank Transfers Tracker — Research Notes

## Goal
Read incoming transfers from Wise and Revolut, push data to a spreadsheet.

---

## Wise API

### Endpoints for Incoming Transfers
- **Balance Statements:** `GET /v3/profiles/{profileId}/balance-statements/{balanceId}/statement`
  - Filter by CREDIT entries to get incoming transfers
  - Fields: date, amount, currency, senderName, senderAccount, paymentReference, runningBalance
- **Activities:** `GET /v1/profiles/{profileId}/activities` — broader activity feed
- **Balances:** `GET /v4/profiles/{profileId}/balances?types=STANDARD` — list all currency balances

### Authentication
- **Personal API token** (Bearer) — for accessing your own account
- RSA key pair required for Strong Customer Authentication (SCA)
- Generate token in Wise Settings > API tokens
- OAuth 2.0 available for third-party apps (not needed for own account)

### Webhooks
- `balances#credit` — fires when money is received (key event)
- `transfers#state-change` — transfer status changes
- Setup: `POST /v3/profiles/{profileId}/subscriptions`
- Signed with RSA, verify via `X-Signature-SHA256` header

### Sandbox
- URL: `https://api.sandbox.transferwise.tech/`
- Production: `https://api.wise.com/`
- Separate sandbox account at `https://sandbox.transferwise.tech/`

### Pricing
- API is free. No per-call charges.
- Standard Wise fees apply only for initiating transfers.

### Requirements
- Verified Wise account (personal or business)
- Personal token works for own account data
- No special application needed

---

## Revolut

### Path 1: Business API (Business accounts only)

#### Endpoints
- `GET /api/1.0/transactions` — list transactions, filter by date range, type
  - Filter incoming: check `legs[].amount > 0` or `direction`
  - Fields: id, type, state, created_at, reference, legs (amount, currency, counterparty, balance)
- `GET /api/1.0/transaction/{id}` — single transaction

#### Authentication
- RSA key pair → JWT → exchange for access token via `POST /api/1.0/auth/token`
- Access tokens expire (~40 min), use refresh tokens
- Set up in Revolut Business dashboard > Settings > API

#### Webhooks
- `TransactionCreated` — new transaction (including incoming)
- `TransactionStateChanged` — status changes
- Setup: `POST /api/1.0/webhook`

#### Sandbox
- URL: `https://sandbox-b2b.revolut.com`
- Production: `https://b2b.revolut.com`

### Path 2: Open Banking / PSD2 (Personal accounts)

#### How It Works
- Revolut exposes Open Banking AIS endpoints under PSD2 regulation
- You need a licensed AISP or use an aggregator

#### Recommended Aggregators
1. **GoCardless Bank Account Data** (formerly Nordigen)
   - Free tier available
   - Supports Revolut personal accounts
   - Simple flow: create requisition → user consents → poll transactions
2. **TrueLayer** — paid, well-established
3. **Plaid** — paid, supports Revolut in some regions
4. **Yapily** — another option

#### GoCardless Flow
1. Create a requisition (link to Revolut)
2. User redirects to Revolut, grants consent
3. Consent valid for ~90 days (renewable)
4. Poll `GET /accounts/{id}/transactions` for transaction data

---

## Spreadsheet Target: Google Sheets (Recommended)

### Why Google Sheets
- Free, cloud-hosted, real-time updates
- Service account auth = no user interaction needed
- `gspread` Python library = simplest developer experience
- 60 writes/min rate limit is more than enough

### Setup
1. Create Google Cloud project
2. Enable Google Sheets API
3. Create service account, download JSON key
4. Share target spreadsheet with service account email
5. Use `gspread` to write data

### Alternatives Considered
- **Local .xlsx (openpyxl):** No cloud access, good for reports
- **Notion:** 3 req/sec limit, not a real spreadsheet
- **Airtable:** Row limits (50K free), rate limits
- **MS Excel Online:** Complex Azure AD auth, needs M365
- **CSV:** No live viewing, no formatting

---

## Architecture Options

### Option A: Polling Script (Simplest)
```
Cron (every 15-30 min)
  → Python script
    → Fetch new transactions from Wise API
    → Fetch new transactions from Revolut API (Business or GoCardless)
    → Append rows to Google Sheet
    → Track last-seen transaction to avoid duplicates
```

### Option B: Webhook Listener (Real-time)
```
Flask/FastAPI server (HTTPS)
  → Wise webhook (balances#credit)
  → Revolut webhook (TransactionCreated)
  → Append row to Google Sheet on each event
  + Fallback polling for missed events
```

### Option C: Hybrid
- Webhooks for real-time when available
- Polling as fallback/reconciliation
- Most robust but more complex

### Recommendation
Start with **Option A (polling)**. It's simpler, doesn't require a public HTTPS server,
and runs as a cron job. Move to webhooks later if real-time matters.

---

## Tech Stack Decision

| Component | Choice | Why |
|-----------|--------|-----|
| Language | Python 3.11+ | Best library support (gspread, requests) |
| Wise client | `requests` + personal token | No official SDK, REST API is simple |
| Revolut client | `requests` (Business) or GoCardless SDK | Depends on account type |
| Spreadsheet | `gspread` + Google Sheets | Simplest cloud spreadsheet integration |
| Scheduling | cron / systemd timer | Simple, no dependencies |
| Config | `.env` file + `python-dotenv` | Standard for secrets management |

## Data Fields to Capture

| Column | Source |
|--------|--------|
| Date | Transaction timestamp |
| Source | "Wise" or "Revolut" |
| Amount | Transaction amount |
| Currency | Currency code |
| Sender Name | Sender/counterparty name |
| Reference | Payment reference/description |
| Transaction ID | For deduplication |
| Balance After | Running balance (if available) |
