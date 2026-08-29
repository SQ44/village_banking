# Village Banking Platform



Full-stack toolkit for running a customizable village banking / rotating savings program with automated settlements through Lipila. The FastAPI backend keeps a ledger of members, savings products, transactions, and interest accruals while the React dashboard offers an operator-friendly workspace.



## Features

- **Ledger & Members** – Capture members, attach configurable savings products, and maintain running balances per account.

- **Transaction Tracking** – Support deposits, withdrawals, loans, repayments, and manual adjustments. Transactions can be collected or paid out through Lipila with one click.

- **Interest Engine** – Preview or apply interest earnings per member with custom date ranges and compounding rules inherited from their product.

- **Custom Fields Everywhere** – Store flexible metadata (phone numbers, payout accounts, etc.) per member, product, or transaction.

- **Dashboard** – React UI with live stats, ledgers, and workflows for onboarding, payouts, and profit distribution.

- **Secure Access** – JWT-protected API with admin-provisioned operators so only trusted teammates can open the controls.



## Tech Stack

- Backend: FastAPI + SQLModel (SQLite default) with an async HTTP client for Lipila.

- Frontend: React + Vite + TypeScript.

- Integration: Lipila collections and payouts, with HMAC webhook verification and a reconciliation poller.



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

- `lipila_api_key` – Lipila API key. Leave empty and every Lipila route answers `503`; nothing is simulated, so a balance is never moved on a payment that did not happen.

- `lipila_base_url` / `lipila_live_enabled` – sandbox (`https://api.lipila.dev`) or live (`https://blz.lipila.io`). These two must agree or the app refuses to start, so a live key can never be pointed at the sandbox by accident.

- `lipila_webhook_secret_current` / `lipila_webhook_secret_previous` – Base64 of exactly 32 bytes. Both are accepted during a rotation so events signed just before the swap still verify.

- `lipila_callback_base_url` – public origin Lipila must reach to deliver webhooks to `POST /webhooks/lipila`.

- `lipila_card_return_url` – where a card payer lands after Lipila's hosted page.

- `lipila_disbursements_enabled` and the `lipila_disbursement_*_path` settings – payouts, off by default. See the caveat under Lipila Flows.

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

- **Custom Fields JSON** is available on accounts and transactions. Use it to store `customer_email` (collections) and `account_number` / `bank_code` / `recipient_name` (bank payouts).

- **Lipila Flows** – Toggle "Pay with Lipila" in the transaction form, or send `use_lipila=true` with a `channel` in the API payload.

  **Collections** (`deposit`, `loan_repayment`) go out over `mobile_money` or `card` and are written **pending**: the balance does not move until Lipila confirms the payment, whatever `status` the request asked for. A card collection returns `card_redirect_url` — send the payer there to authorise. Confirmation arrives by webhook, or by the reconciliation poller if that webhook is lost.

  **Payouts** (`withdrawal`, `loan_disbursement`) go out over `mobile_money` or `bank` and work the other way round: the funds are debited when the payout is requested, so the same balance cannot be withdrawn twice while one payout is in flight. A payout Lipila reports as failed hands the money straight back.

  > **Payouts are unverified.** The collection calls are ported from an integration that ran against Lipila in production. The disbursement calls are not — no payout request has ever been sent, and the endpoint paths are inferred from the collections API's own convention. They stay behind `lipila_disbursements_enabled=false` until you confirm them against the Lipila dashboard docs. Every path is a setting, so a correction is an `.env` change rather than a code change.

  Both directions refuse a payload whose amount or currency disagrees with the ledger, and mark it `needs_review` instead of settling it.

- **Interest Workflow** – The interest panel previews earnings over arbitrary date ranges and, on apply, posts an `interest` transaction plus an `InterestAccrual` entry.

- **Extending the API** – Each router is isolated under `server/app/routers`. Add new modules (e.g., reporting, group payouts) and include them inside `app/main.py`.

- **Payment states** – The ledger records `pending`/`completed`/`failed`, but Lipila says more than that. Its own word is kept on `provider_status` (`pending`, `succeeded`, `failed`, `expired`, `reversed`, `refunded`, `needs_review`) so an operator can tell an expiry from a refusal. `needs_review` deliberately holds at `pending`: an ambiguous provider answer is not evidence that money moved, nor that it did not.



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

Before first run, create your local env files:

```bash
cp server/.env.example server/.env
```

Set at least `default_admin_email`, `default_admin_password`, and `auth_secret_key` in `server/.env`.

PowerShell helper:

```powershell
powershell -ExecutionPolicy Bypass -File server\\scripts\\bootstrap_env.ps1
```



## Next Steps

- Confirm the Lipila payout endpoints, then enable `lipila_disbursements_enabled`.

- Expand background jobs to push statements/SMS via your preferred provider.

- Deploy backend (Uvicorn/Gunicorn) and serve the React build via CDN or alongside the API behind a reverse proxy.
