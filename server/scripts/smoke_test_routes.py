import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient


def _require(value: str | None, name: str) -> str:
    if not value:
        raise SystemExit(f"Missing required setting: {name}")
    return value


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    # Ensure `server/app` is importable when running as a script.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    # Isolate the smoke test from any existing DB data.
    os.environ.setdefault("database_url", "sqlite:///./smoke_test.db")
    try:
        os.remove("smoke_test.db")
    except OSError:
        pass

    from app.main import app  # noqa: WPS433
    from app.config import get_settings  # noqa: WPS433

    settings = get_settings()
    admin_email = _require(settings.default_admin_email, "default_admin_email")
    admin_password = _require(settings.default_admin_password, "default_admin_password")

    with TestClient(app) as client:
        results: list[tuple[str, int]] = []

        def record(label: str, resp, expected: set[int] | None = None) -> None:
            """Record a call. `expected` allows a route whose correct answer is
            an error — an unconfigured provider, or a refused unsigned webhook."""
            results.append((label, resp.status_code))
            if expected is not None:
                if resp.status_code not in expected:
                    raise AssertionError(
                        f"{label} returned {resp.status_code}, expected one of {sorted(expected)}: {resp.text}"
                    )
                return
            if resp.status_code >= 400:
                raise AssertionError(f"{label} failed: {resp.status_code} {resp.text}")

        # Public route
        resp = client.get("/health")
        record("GET /health", resp)

        # Login as default admin
        resp = client.post("/auth/login", data={"username": admin_email, "password": admin_password})
        record("POST /auth/login (admin)", resp)
        admin_token = resp.json()["access_token"]

        # Whoami
        resp = client.get("/auth/me", headers=_auth_headers(admin_token))
        record("GET /auth/me (admin)", resp)

        # Register an operator and login
        operator_email = "operator@example.com"
        operator_password = "Operator@123"
        resp = client.post(
            "/auth/register",
            headers=_auth_headers(admin_token),
            json={
                "email": operator_email,
                "full_name": "Operator",
                "role": "operator",
                "password": operator_password,
            },
        )
        record("POST /auth/register (admin)", resp)

        resp = client.post("/auth/login", data={"username": operator_email, "password": operator_password})
        record("POST /auth/login (operator)", resp)
        operator_token = resp.json()["access_token"]

        # Operator cannot register users
        resp = client.post(
            "/auth/register",
            headers=_auth_headers(operator_token),
            json={
                "email": "blocked@example.com",
                "full_name": "Blocked",
                "role": "operator",
                "password": "Blocked@123",
            },
        )
        if resp.status_code != 403:
            raise AssertionError(f"Expected 403 for operator register, got {resp.status_code}: {resp.text}")
        results.append(("POST /auth/register (operator forbidden)", resp.status_code))

        # Products CRUD
        resp = client.get("/products/", headers=_auth_headers(admin_token))
        record("GET /products/", resp)

        resp = client.post(
            "/products/",
            headers=_auth_headers(admin_token),
            json={
                "name": "Standard",
                "description": "Standard savings product",
                "interest_rate": 10.0,
                "compounding_days": 30,
                "min_balance": 0,
                "custom_fields": {},
            },
        )
        record("POST /products/", resp)
        product_id = resp.json()["id"]

        resp = client.get(f"/products/{product_id}", headers=_auth_headers(admin_token))
        record("GET /products/{id}", resp)

        resp = client.post(
            "/products/",
            headers=_auth_headers(admin_token),
            json={
                "name": "Temp Delete",
                "description": "Disposable product",
                "interest_rate": 5.0,
                "compounding_days": 30,
                "min_balance": 0,
                "custom_fields": {},
            },
        )
        record("POST /products/ (delete fixture)", resp)
        delete_product_id = resp.json()["id"]

        resp = client.delete(f"/products/{delete_product_id}", headers=_auth_headers(admin_token))
        if resp.status_code != 204:
            raise AssertionError(f"DELETE /products/{delete_product_id} failed: {resp.status_code} {resp.text}")
        results.append((f"DELETE /products/{delete_product_id}", resp.status_code))

        # Accounts CRUD
        resp = client.post(
            "/accounts/",
            headers=_auth_headers(admin_token),
            json={
                "name": "Test Member",
                "email": "member@example.com",
                "group_name": "Test Group",
                "product_id": product_id,
                "custom_fields": {"phone": "+2348000000", "bank_account": "0123456789", "bank_code": "044"},
                "initial_deposit": 100,
            },
        )
        record("POST /accounts/", resp)
        account_id = resp.json()["id"]

        resp = client.get("/accounts/", headers=_auth_headers(admin_token))
        record("GET /accounts/", resp)

        resp = client.get(f"/accounts/{account_id}", headers=_auth_headers(admin_token))
        record("GET /accounts/{id}", resp)

        resp = client.patch(
            f"/accounts/{account_id}",
            headers=_auth_headers(admin_token),
            json={"name": "Test Member", "custom_fields": {"statement_email": "member@example.com"}},
        )
        record("PATCH /accounts/{id}", resp)

        # Transactions: list + create + patch
        resp = client.get("/transactions/", headers=_auth_headers(admin_token))
        record("GET /transactions/", resp)

        resp = client.post(
            "/transactions/",
            headers=_auth_headers(admin_token),
            json={
                "account_id": account_id,
                "amount": 5,
                "type": "deposit",
                "status": "pending",
                "description": "Pending deposit",
                "use_lipila": False,
                "custom_fields": {},
            },
        )
        record("POST /transactions/ (pending)", resp)
        pending_tx_id = resp.json()["id"]

        resp = client.patch(
            f"/transactions/{pending_tx_id}",
            headers=_auth_headers(admin_token),
            # Changing a transaction by hand now has to say why — the audit log
            # exists precisely to catch unexplained balance changes.
            json={"status": "completed", "reason": "Smoke test: confirming a pending deposit"},
        )
        record("PATCH /transactions/{id}", resp)

        # Lipila mobile money collection. Without lipila_api_key this returns
        # 503, which is the correct answer and still exercises the route.
        resp = client.post(
            "/transactions/",
            headers=_auth_headers(admin_token),
            json={
                "account_id": account_id,
                "amount": 10,
                "type": "deposit",
                "description": "Deposit with Lipila",
                "use_lipila": True,
                "channel": "mobile_money",
                "phone_number": "0977123456",
                "custom_fields": {"customer_email": "member@example.com", "currency": "ZMW"},
            },
        )
        record("POST /transactions/ (lipila mobile money collection)", resp, expected={201, 503})

        # Lipila payout. Off until the disbursement paths are confirmed, so a
        # 503 here is the configured behaviour rather than a failure.
        resp = client.post(
            "/transactions/",
            headers=_auth_headers(admin_token),
            json={
                "account_id": account_id,
                "amount": 10,
                "type": "withdrawal",
                "description": "Withdrawal with Lipila",
                "use_lipila": True,
                "channel": "mobile_money",
                "phone_number": "0977123456",
                "custom_fields": {"currency": "ZMW"},
            },
        )
        record("POST /transactions/ (lipila payout)", resp, expected={201, 503})

        # An unsigned webhook must be refused.
        resp = client.post("/webhooks/lipila", json={"referenceId": "VB-UNSIGNED", "status": "success"})
        record("POST /webhooks/lipila (unsigned)", resp, expected={401, 503})

        # Interest preview/apply
        start = datetime.utcnow() - timedelta(days=30)
        end = datetime.utcnow()
        resp = client.post(
            "/interest/preview",
            headers=_auth_headers(admin_token),
            json={"account_id": account_id, "start": start.isoformat(), "end": end.isoformat()},
        )
        record("POST /interest/preview", resp)

        resp = client.post(
            "/interest/apply",
            headers=_auth_headers(admin_token),
            json={"account_id": account_id, "start": start.isoformat(), "end": end.isoformat()},
        )
        record("POST /interest/apply", resp)

        # Dashboard
        resp = client.get("/dashboard/summary", headers=_auth_headers(admin_token))
        record("GET /dashboard/summary", resp)

        for label, code in results:
            print(f"{code} {label}")

    # Cleanup the isolated DB file (best-effort).
    try:
        os.remove("smoke_test.db")
    except OSError:
        pass


if __name__ == "__main__":
    main()
