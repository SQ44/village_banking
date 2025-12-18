# Village Banking Platform



Full-stack toolkit for running a customizable village banking / rotating savings program with automated settlements through Lenco Pay. The FastAPI backend keeps a ledger of members, savings products, transactions, and interest accruals while the React dashboard offers an operator-friendly workspace.



## Features

- **Ledger & Members** – Capture members, attach configurable savings products, and maintain running balances per account.

- **Transaction Tracking** – Support deposits, withdrawals, loans, repayments, and manual adjustments. Transactions can be settled through Lenco Pay with one click.

- **Interest Engine** – Preview or apply interest earnings per member with custom date ranges and compounding rules inherited from their product.

- **Custom Fields Everywhere** – Store flexible metadata (phone numbers, payout accounts, etc.) per member, product, or transaction.

- **Dashboard** – React UI with live stats, ledgers, and workflows for onboarding, payouts, and profit distribution.

- **Secure Access** – JWT-protected API with admin-provisioned operators so only trusted teammates can open the controls.



## Tech Stack

- Backend: FastAPI + SQLModel (SQLite default) with async HTTP client for Lenco Pay.

- Frontend: React + Vite + TypeScript.

- Integration: Lenco Pay client wrapper with webhook verification helper.



## Getting Started



### 1. Backend API

```bash

cd server

python -m venv .venv

. .venv/bin/activate  # PowerShell: .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

cp .env.example .env  # update secrets

uvicorn app.main:app --reload

```



Key environment variables (see `server/.env.example`):

- `database_url` – connection string, default SQLite file `villagebank.db`.

- `lenco_pay_base` – base URL for the local `lenco_pay` gateway (e.g. `http://localhost:8001/api/v1`); when set, settlement calls are proxied through it.

- `lenco_api_base` – base URL for Lenco Pay.

- `lenco_api_key` – secret for live calls; leave empty to work in simulation mode.

- `lenco_webhook_secret` – used to verify Lenco callbacks.

- `interest_compound_days` – default compounding period in days.

- `auth_secret_key` / `default_admin_*` – auth materials for seeding the first admin.

- `scheduler_timezone` – timezone applied to background jobs.
- `smtp_*` - SMTP credentials used by the weekly statement mailer (`app/notifications.py`).



### 2. Frontend Dashboard

```bash

cd client

npm install

cp .env.example .env  # configure VITE_API_URL if backend not on localhost:8000

npm run dev  # open http://localhost:5173

```



The dashboard talks directly to the FastAPI service. Ensure `VITE_API_URL` points to the backend origin.



## Authentication

- On startup, the API seeds a default admin user from `default_admin_email` / `default_admin_password` when the table is empty. These values are **required** in `.env` and must be unique per environment.

- Obtain a JWT by POSTing form data (`username` + `password`) to `/auth/login`. The React UI prompts for these credentials before it makes any API calls.

- Provision additional operators via `/auth/register` (admin token required). Their `role` is returned in `/auth/me` and can be used for additional authorization logic - create one per teammate before granting dashboard access.



## Customization Notes

- **Savings Products** (`POST /products`) let you set interest rates, compounding cadence, minimum balances, and any auxiliary fields (e.g., meeting days). Attach a product when creating an account via the UI or API.

- **Custom Fields JSON** is available on accounts and transactions. Use it to store `customer_email` / `customer_phone` (collections) and `account_number` / `bank_code` (transfers).

- **Lenco Pay Flows** – Toggle "Trigger Lenco Pay" in the transaction form, or send `use_lenco=true` in the API payload. Deposits/repayments initiate a payment (provide `customer_email` or `customer_phone`), while withdrawals/loan disbursements initiate a transfer (provide `account_number`; if `lenco_pay_base` is set also provide `bank_code`, with optional `recipient_name`). Without API keys, the system records simulated responses for testing.

- **Interest Workflow** – The interest panel previews earnings over arbitrary date ranges and, on apply, posts an `interest` transaction plus an `InterestAccrual` entry.

- **Extending the API** – Each router is isolated under `server/app/routers`. Add new modules (e.g., reporting, group payouts) and include them inside `app/main.py`.

- **Lenco Core API** – The `lenco_pay` folder contains the lower-level API, rate-limiting, anti-fraud, and webhook retry logic you've already invested in. Point this dashboard at that service to reuse all the battle-tested plumbing.



## Scheduled Jobs & Statements

- APScheduler runs inside FastAPI (`schedule_jobs`) to handle:

  - **Daily interest accrual scans** – Accounts exceeding their product's compounding window automatically trigger `apply_interest`.

  - **Weekly statement digests** - Every Friday at 06:00 UTC, the ledger is aggregated and emailed to each member with a configured `account.email` (or `custom_fields.statement_email`). Configure the `smtp_*` variables in `.env` to enable delivery; otherwise the job logs warnings so you can wire up SMS or Celery-based delivery later.

- Adjust cadence and timezone via `.env` or swap `send_email` in `app/notifications.py` for a Celery/SMS gateway when you outgrow the built-in SMTP helper.



## Helpful Commands

- List accounts: `curl http://localhost:8000/accounts`

- Create account: `curl -X POST http://localhost:8000/accounts -H "Content-Type: application/json" -d '{"name":"Ada","initial_deposit":200}'`

- Preview interest: `curl -X POST http://localhost:8000/interest/preview ...`

## Docker (Build + Run)

From the repo root:

```bash
docker compose build
docker compose up
```

- API: `http://localhost:8000/health`
- Dashboard: `http://localhost:5173`

The SQLite database is persisted in the `api-data` Docker volume.



## Next Steps

- Plug in production Lenco credentials plus webhook endpoint for state reconciliation.

- Expand background jobs to push statements/SMS via your preferred provider.

- Deploy backend (Uvicorn/Gunicorn) and serve the React build via CDN or alongside the API behind a reverse proxy.
