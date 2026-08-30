import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    os.environ["database_url"] = "sqlite:///./smoke_group_loans.db"
    try:
        os.remove("smoke_group_loans.db")
    except OSError:
        pass

    from app.main import app  # noqa: WPS433
    from app.config import get_settings  # noqa: WPS433

    settings = get_settings()
    if not settings.default_admin_email or not settings.default_admin_password:
        raise SystemExit("Set default_admin_email/default_admin_password in server/.env to run this test")

    with TestClient(app) as client:
        # Admin login
        resp = client.post(
            "/auth/login",
            data={"username": settings.default_admin_email, "password": settings.default_admin_password},
        )
        resp.raise_for_status()
        admin_token = resp.json()["access_token"]

        # Create group + configure settings
        resp = client.post(
            "/groups",
            headers=_auth_headers(admin_token),
            json={"name": "Test Group", "terms": "Test terms"},
        )
        resp.raise_for_status()
        group_id = resp.json()["id"]

        resp = client.patch(
            f"/groups/{group_id}/settings",
            headers=_auth_headers(admin_token),
            json={
                "min_monthly_contribution": 1000,
                "admin_fee_percent": 10,
                "loan_interest_percent": 20,
                "enforce_loan_limit": True,
                "loan_limit_multiplier": 5,
            },
        )
        resp.raise_for_status()

        # Add 2 members: 1000 and 3000 contributions
        resp = client.post(
            f"/groups/{group_id}/members",
            headers=_auth_headers(admin_token),
            json={
                "email": "a@example.com",
                "full_name": "Member A",
                "password": "MemberA@123",
                "name": "Member A",
                "min_initial_deposit": 1000,
                "custom_fields": {},
            },
        )
        resp.raise_for_status()
        member_a_account = resp.json()["membership"]["account_id"]

        resp = client.post(
            f"/groups/{group_id}/members",
            headers=_auth_headers(admin_token),
            json={
                "email": "b@example.com",
                "full_name": "Member B",
                "password": "MemberB@123",
                "name": "Member B",
                "min_initial_deposit": 3000,
                "custom_fields": {},
            },
        )
        resp.raise_for_status()
        member_b_account = resp.json()["membership"]["account_id"]

        # Fund the pool. An initial contribution is recorded as owed, not banked,
        # so the deposits the lending logic needs are posted outright here.
        for account_id, amount in ((member_a_account, 1000), (member_b_account, 3000)):
            resp = client.post(
                "/transactions",
                headers=_auth_headers(admin_token),
                json={
                    "account_id": account_id,
                    "amount": amount,
                    "type": "deposit",
                    "status": "completed",
                    "description": "Opening contribution",
                    "use_lipila": False,
                    "custom_fields": {},
                },
            )
            resp.raise_for_status()

        # Members login + accept terms
        resp = client.post("/auth/login", data={"username": "a@example.com", "password": "MemberA@123"})
        resp.raise_for_status()
        token_a = resp.json()["access_token"]
        resp = client.post(f"/groups/{group_id}/accept-terms", headers=_auth_headers(token_a), json={"accepted": True})
        resp.raise_for_status()

        resp = client.post("/auth/login", data={"username": "b@example.com", "password": "MemberB@123"})
        resp.raise_for_status()
        token_b = resp.json()["access_token"]
        resp = client.post(f"/groups/{group_id}/accept-terms", headers=_auth_headers(token_b), json={"accepted": True})
        resp.raise_for_status()

        # Create loan for member A: principal 1000, interest 20% => 200
        resp = client.post(
            f"/loans/group/{group_id}",
            headers=_auth_headers(admin_token),
            json={
                "borrower_account_id": member_a_account,
                "principal": 1000,
                "term_months": 1,
                "repayment_frequency": "monthly",
                "description": "Test loan",
            },
        )
        resp.raise_for_status()
        loan_id = resp.json()["id"]

        # Repay full amount (interest-first): 1200
        resp = client.post(f"/loans/{loan_id}/repay", headers=_auth_headers(token_a), json={"amount": 1200})
        resp.raise_for_status()

        # Validate interest distribution: distributable 180 => A:45, B:135 (1000/4000 and 3000/4000)
        def sum_interest_for(account_id: int) -> float:
            tx_resp = client.get(f"/transactions?account_id={account_id}", headers=_auth_headers(admin_token))
            tx_resp.raise_for_status()
            return round(
                sum(t["amount"] for t in tx_resp.json() if t["type"] == "interest" and t["custom_fields"].get("source") == "loan_interest"),
                2,
            )

        a_interest = sum_interest_for(member_a_account)
        b_interest = sum_interest_for(member_b_account)
        assert a_interest == 45.0, a_interest
        assert b_interest == 135.0, b_interest

        # Validate member summaries surface the same interest numbers.
        resp = client.get("/me/summary", headers=_auth_headers(token_a))
        resp.raise_for_status()
        assert round(resp.json()["interest_earned"], 2) == 45.0

        resp = client.get("/me/summary", headers=_auth_headers(token_b))
        resp.raise_for_status()
        assert round(resp.json()["interest_earned"], 2) == 135.0

        print("OK group loan interest distribution")

    try:
        os.remove("smoke_group_loans.db")
    except OSError:
        pass


if __name__ == "__main__":
    main()

