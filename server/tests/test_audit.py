"""Nobody moves the pot unobserved.

A village banking group adopts software to stop trusting one person with the
money. These cover the two paths where a person can still move a balance
directly: overriding a payment's status, and editing a balance by hand.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlmodel import select

from app import audit
from app.models import AuditLog, Transaction, TransactionStatus, TransactionType


@pytest.fixture(name="pending_deposit")
def pending_deposit_fixture(session, account) -> Transaction:
    transaction = Transaction(
        account_id=account.id,
        amount=250.0,
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.PENDING,
        created_at=datetime.utcnow(),
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


class TestTransactionOverride:
    def test_a_reason_is_required(self, client, admin_auth, pending_deposit):
        """"Who" without "why" does not settle an argument."""
        response = client.patch(
            f"/transactions/{pending_deposit.id}",
            json={"status": "completed"},
            headers=admin_auth,
        )
        assert response.status_code == 400
        assert "reason" in response.json()["detail"].lower()

    def test_nothing_moves_when_the_reason_is_missing(self, client, admin_auth, pending_deposit, session, account):
        client.patch(
            f"/transactions/{pending_deposit.id}",
            json={"status": "completed"},
            headers=admin_auth,
        )
        session.refresh(account)
        session.refresh(pending_deposit)
        assert account.balance == 0
        assert pending_deposit.status == TransactionStatus.PENDING

    def test_an_override_is_recorded_with_actor_and_reason(
        self, client, admin_auth, pending_deposit, session, account, admin
    ):
        response = client.patch(
            f"/transactions/{pending_deposit.id}",
            json={"status": "completed", "reason": "Member showed the SMS receipt at the meeting"},
            headers=admin_auth,
        )
        assert response.status_code == 200

        entries = session.exec(select(AuditLog)).all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.action == audit.TRANSACTION_STATUS_CHANGED
        assert entry.actor_user_id == admin.id
        assert entry.actor_email == "admin@example.com"
        assert entry.entity_id == str(pending_deposit.id)
        assert entry.reason == "Member showed the SMS receipt at the meeting"

    def test_the_entry_captures_the_balance_either_side(
        self, client, admin_auth, pending_deposit, session, account
    ):
        client.patch(
            f"/transactions/{pending_deposit.id}",
            json={"status": "completed", "reason": "Confirmed by the treasurer"},
            headers=admin_auth,
        )
        entry = session.exec(select(AuditLog)).first()
        # Stringified decimals, not floats: the audit record has to reproduce
        # the exact figure, and a JSON column cannot hold a Decimal.
        assert entry.before == {"status": "pending", "account_balance": "0.00"}
        assert entry.after == {"status": "completed", "account_balance": "250.00"}

    def test_a_member_cannot_override_their_own_payment(self, client, member_auth, pending_deposit, session):
        response = client.patch(
            f"/transactions/{pending_deposit.id}",
            json={"status": "completed", "reason": "I definitely paid"},
            headers=member_auth,
        )
        assert response.status_code == 403
        assert session.exec(select(AuditLog)).all() == []

    def test_a_no_op_change_records_nothing(self, client, admin_auth, pending_deposit, session):
        response = client.patch(
            f"/transactions/{pending_deposit.id}",
            json={"status": "pending", "reason": "no change"},
            headers=admin_auth,
        )
        assert response.status_code == 200
        assert session.exec(select(AuditLog)).all() == []


class TestBalanceEdit:
    def test_setting_a_balance_needs_a_reason(self, client, admin_auth, account):
        response = client.patch(
            f"/accounts/{account.id}",
            json={"name": account.name, "balance": 5000.0},
            headers=admin_auth,
        )
        assert response.status_code == 400

    def test_setting_a_balance_is_recorded(self, client, admin_auth, account, session):
        response = client.patch(
            f"/accounts/{account.id}",
            json={
                "name": account.name,
                "balance": 5000.0,
                "reason": "Correcting a migration error, see ticket VB-12",
            },
            headers=admin_auth,
        )
        assert response.status_code == 200

        entry = session.exec(select(AuditLog)).first()
        assert entry is not None
        assert entry.action == audit.ACCOUNT_BALANCE_CHANGED
        assert entry.before == {"balance": "0.00"}
        assert entry.after == {"balance": "5000.00"}
        assert "VB-12" in entry.reason

    def test_editing_other_fields_is_not_audited(self, client, admin_auth, account, session):
        """Only money is the audit log's business."""
        response = client.patch(
            f"/accounts/{account.id}",
            json={"name": "Mutale Banda"},
            headers=admin_auth,
        )
        assert response.status_code == 200
        assert session.exec(select(AuditLog)).all() == []

    def test_a_member_cannot_set_their_own_balance(self, client, member_auth, account, session):
        """The balance field is stripped for non-admins before it is applied."""
        response = client.patch(
            f"/accounts/{account.id}",
            json={"name": account.name, "balance": 99999.0},
            headers=member_auth,
        )
        assert response.status_code == 200
        session.refresh(account)
        assert account.balance == 0
        assert session.exec(select(AuditLog)).all() == []


class TestAuditEndpoint:
    def test_admins_can_read_the_trail(self, client, admin_auth, pending_deposit):
        client.patch(
            f"/transactions/{pending_deposit.id}",
            json={"status": "completed", "reason": "Receipt shown at the meeting"},
            headers=admin_auth,
        )
        response = client.get("/operations/audit", headers=admin_auth)
        assert response.status_code == 200
        entries = response.json()
        assert len(entries) == 1
        assert entries[0]["reason"] == "Receipt shown at the meeting"
        assert entries[0]["actor_email"] == "admin@example.com"

    def test_members_cannot(self, client, member_auth):
        """An audit log readable by the audited is not much of a control."""
        response = client.get("/operations/audit", headers=member_auth)
        assert response.status_code == 403

    def test_newest_first(self, client, admin_auth, account, session):
        for index in range(3):
            client.patch(
                f"/accounts/{account.id}",
                json={"name": account.name, "balance": 100.0 * (index + 1), "reason": f"step {index}"},
                headers=admin_auth,
            )
        entries = client.get("/operations/audit", headers=admin_auth).json()
        assert [e["reason"] for e in entries] == ["step 2", "step 1", "step 0"]

    def test_filterable_by_entity_type(self, client, admin_auth, account, pending_deposit):
        client.patch(
            f"/accounts/{account.id}",
            json={"name": account.name, "balance": 10.0, "reason": "account edit"},
            headers=admin_auth,
        )
        client.patch(
            f"/transactions/{pending_deposit.id}",
            json={"status": "failed", "reason": "transaction edit"},
            headers=admin_auth,
        )
        entries = client.get("/operations/audit?entity_type=transaction", headers=admin_auth).json()
        assert len(entries) == 1
        assert entries[0]["reason"] == "transaction edit"
