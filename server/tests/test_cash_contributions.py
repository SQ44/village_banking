"""Banking a contribution that was handed over in person.

Cash has no provider behind it. An admin is attesting that money changed hands,
and the balance moves on their word alone — the same shape as the hand-made
overrides in `test_audit.py`, and covered here for the same reason. What the
tests care about is that the attestation is recorded, that it cannot be made by
the person who benefits from it, and that the resulting balance is one the
ledger can still explain.
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from app import audit
from app.models import Account, AuditLog, Transaction, TransactionStatus, TransactionType
from app.reconciliation import check_account


def _collect_cash(client, headers, group, account, amount=300.0, reason="Handed over at the June meeting"):
    return client.post(
        f"/groups/{group.id}/members/{account.id}/collect",
        json={"amount": amount, "method": "cash", "cash_reason": reason},
        headers=headers,
    )


class TestBankingCash:
    def test_cash_credits_the_balance_immediately(self, client, admin_auth, session, group, account):
        """Unlike a Lipila collection, there is nothing to wait for."""
        response = _collect_cash(client, admin_auth, group, account)
        assert response.status_code == 201, response.text

        session.refresh(account)
        assert account.balance == 300.0
        assert response.json()["status"] == "completed"

    def test_it_writes_a_completed_deposit(self, client, admin_auth, session, group, account):
        _collect_cash(client, admin_auth, group, account)

        transactions = session.exec(select(Transaction).where(Transaction.account_id == account.id)).all()
        assert len(transactions) == 1
        assert transactions[0].type == TransactionType.DEPOSIT
        assert transactions[0].status == TransactionStatus.COMPLETED
        assert transactions[0].custom_fields["settled_in"] == "cash"
        # No provider was involved, so there is nothing to reconcile against.
        assert transactions[0].provider is None
        assert transactions[0].provider_reference is None

    def test_the_balance_still_reconciles(self, client, admin_auth, session, group, account):
        """A cash credit must not look like an unexplained balance afterwards."""
        _collect_cash(client, admin_auth, group, account)
        session.refresh(account)
        assert check_account(session, account) is None

    def test_it_clears_what_was_owed(self, client, admin_auth, session, group, account):
        """Paid is paid, however it arrived."""
        account.custom_fields = {**account.custom_fields, "initial_contribution_due": 300.0}
        session.add(account)
        session.commit()

        _collect_cash(client, admin_auth, group, account)
        session.refresh(account)
        assert "initial_contribution_due" not in (account.custom_fields or {})


class TestItIsRecorded:
    def test_a_reason_is_required(self, client, admin_auth, session, group, account):
        response = _collect_cash(client, admin_auth, group, account, reason="")
        assert response.status_code == 400
        assert "reason" in response.json()["detail"].lower()

        session.refresh(account)
        assert account.balance == 0

    def test_the_attestation_names_the_admin_and_the_reason(
        self, client, admin_auth, session, group, account, admin
    ):
        _collect_cash(client, admin_auth, group, account, reason="Counted at the June meeting, two witnesses")

        entry = session.exec(select(AuditLog)).first()
        assert entry is not None
        assert entry.action == "cash_contribution_recorded"
        assert entry.actor_user_id == admin.id
        assert entry.actor_email == "admin@example.com"
        assert entry.before == {"balance": "0.00"}
        assert entry.after["balance"] == "300.00"
        assert "two witnesses" in entry.reason

    def test_the_audit_entry_points_at_the_transaction(self, client, admin_auth, session, group, account):
        """So a disputed entry can be traced back to the money it moved."""
        response = _collect_cash(client, admin_auth, group, account)
        entry = session.exec(select(AuditLog)).first()
        assert entry.after["transaction_id"] == response.json()["transaction_id"]

    def test_a_rejected_cash_entry_records_nothing(self, client, admin_auth, session, group, account):
        _collect_cash(client, admin_auth, group, account, reason="")
        assert session.exec(select(AuditLog)).all() == []
        assert session.exec(select(Transaction)).all() == []

    def test_zero_and_negative_amounts_are_refused(self, client, admin_auth, group, account):
        assert _collect_cash(client, admin_auth, group, account, amount=0).status_code == 400
        assert _collect_cash(client, admin_auth, group, account, amount=-50).status_code == 400


class TestWhoMayAttest:
    def test_a_member_cannot_bank_their_own_cash(self, client, member_auth, session, group, account):
        """Otherwise any member could credit themselves by saying they paid."""
        response = _collect_cash(client, member_auth, group, account)
        assert response.status_code == 403

        session.refresh(account)
        assert account.balance == 0
        assert session.exec(select(AuditLog)).all() == []

    def test_a_platform_admin_can(self, client, admin_auth, group, account):
        assert _collect_cash(client, admin_auth, group, account).status_code == 201


class TestCashAtSignUp:
    def test_a_member_can_be_added_with_cash_in_hand(self, client, admin_auth, session, group):
        response = client.post(
            f"/groups/{group.id}/members",
            json={
                "email": "banda@example.com",
                "full_name": "Grace Banda",
                "password": "temp-pass",
                "name": "Grace",
                "min_initial_deposit": 500.0,
                "initial_contribution_method": "cash",
                "cash_reason": "Paid in full at sign-up",
            },
            headers=admin_auth,
        )
        assert response.status_code == 201, response.text
        body = response.json()

        assert body["payment"]["amount"] == 500.0
        assert body["payment"]["status"] == "completed"
        # Settled, so nothing is owed.
        assert body["initial_contribution_due"] is None

        account = session.exec(select(Account).where(Account.email == "banda@example.com")).first()
        assert account.balance == 500.0
        assert check_account(session, account) is None

    def test_cash_at_sign_up_without_a_reason_is_refused(self, client, admin_auth, session, group):
        response = client.post(
            f"/groups/{group.id}/members",
            json={
                "email": "nobody@example.com",
                "password": "temp-pass",
                "name": "Nobody",
                "min_initial_deposit": 500.0,
                "initial_contribution_method": "cash",
            },
            headers=admin_auth,
        )
        assert response.status_code == 400
        assert session.exec(select(AuditLog)).all() == []

    def test_a_retried_sign_up_does_not_bank_the_cash_twice(self, client, admin_auth, session, group):
        """Cash runs inside the same idempotency guard as a Lipila collection."""
        body = {
            "email": "mwansa@example.com",
            "password": "temp-pass",
            "name": "Mwansa",
            "min_initial_deposit": 500.0,
            "initial_contribution_method": "cash",
            "cash_reason": "Paid at sign-up",
        }
        headers = {**admin_auth, "Idempotency-Key": "signup-mwansa"}

        first = client.post(f"/groups/{group.id}/members", json=body, headers=headers)
        second = client.post(f"/groups/{group.id}/members", json=body, headers=headers)

        assert first.status_code == 201
        assert second.status_code == 201
        assert second.json()["payment"]["transaction_id"] == first.json()["payment"]["transaction_id"]

        account = session.exec(select(Account).where(Account.email == "mwansa@example.com")).first()
        assert account.balance == 500.0
        assert len(session.exec(select(AuditLog)).all()) == 1
