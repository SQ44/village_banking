"""Money that is stuck, and somebody being told about it.

The states these cover all existed before and appeared nowhere in the product:
a payment parked on `needs_review`, a webhook that could not be matched to any
transaction, a balance the entries do not explain. A member's K500 sitting in
limbo destroys a group's confidence faster than any bug, because nobody can
even say what happened to it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import (
    Account,
    ProviderEvent,
    Transaction,
    TransactionStatus,
    TransactionType,
)


def _pending(session, account, **kwargs) -> Transaction:
    defaults = dict(
        account_id=account.id,
        amount=500.0,
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.PENDING,
        provider="lipila",
        created_at=datetime.utcnow(),
    )
    transaction = Transaction(**{**defaults, **kwargs})
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


class TestStuckPayments:
    def test_a_needs_review_payment_is_surfaced_at_once(self, client, admin_auth, session, account):
        """No grace period: the provider already said something we can't trust."""
        _pending(session, account, provider_status="needs_review", provider_reference="VB-1")

        report = client.get("/operations/attention", headers=admin_auth).json()
        assert len(report["stuck_payments"]) == 1
        assert report["stuck_payments"][0]["reason"] == "needs_review"
        assert report["stuck_payments"][0]["amount"] == 500.0

    def test_a_fresh_pending_payment_is_left_alone(self, client, admin_auth, session, account):
        """The member is probably still reaching for their handset."""
        _pending(session, account, provider_status="pending", provider_reference="VB-2")

        report = client.get("/operations/attention", headers=admin_auth).json()
        assert report["stuck_payments"] == []

    def test_a_payment_pending_past_the_grace_period_is_surfaced(
        self, client, admin_auth, session, account
    ):
        transaction = _pending(session, account, provider_status="pending", provider_reference="VB-3")
        transaction.created_at = datetime.utcnow() - timedelta(hours=2)
        session.add(transaction)
        session.commit()

        report = client.get("/operations/attention", headers=admin_auth).json()
        assert len(report["stuck_payments"]) == 1
        assert report["stuck_payments"][0]["reason"] == "no_confirmation"
        assert report["stuck_payments"][0]["minutes_waiting"] >= 120

    def test_settled_payments_are_not_listed(self, client, admin_auth, session, account):
        _pending(session, account, status=TransactionStatus.COMPLETED, provider_reference="VB-4")
        _pending(session, account, status=TransactionStatus.FAILED, provider_reference="VB-5")

        report = client.get("/operations/attention", headers=admin_auth).json()
        assert report["stuck_payments"] == []

    def test_longest_waiting_first(self, client, admin_auth, session, account):
        """Call back the member who has been in the dark longest."""
        recent = _pending(session, account, provider_status="needs_review", provider_reference="VB-6")
        old = _pending(session, account, provider_status="needs_review", provider_reference="VB-7")
        old.created_at = datetime.utcnow() - timedelta(days=1)
        session.add(old)
        session.commit()

        report = client.get("/operations/attention", headers=admin_auth).json()
        assert [item["transaction_id"] for item in report["stuck_payments"]] == [old.id, recent.id]

    def test_scoped_to_a_group(self, client, admin_auth, session, account, group):
        other_account = Account(name="Elsewhere", group_id=999, balance=0)
        session.add(other_account)
        session.commit()
        session.refresh(other_account)

        _pending(session, account, provider_status="needs_review", provider_reference="VB-8")
        _pending(session, other_account, provider_status="needs_review", provider_reference="VB-9")

        report = client.get(f"/operations/attention?group_id={group.id}", headers=admin_auth).json()
        assert len(report["stuck_payments"]) == 1
        assert report["stuck_payments"][0]["account_name"] == "Mutale"


class TestDeadLetters:
    def test_an_unplaceable_webhook_is_surfaced(self, client, admin_auth, session):
        """Lipila talking about money this system cannot match to anything."""
        session.add(
            ProviderEvent(
                provider="lipila",
                webhook_id="wh-unknown",
                provider_reference="VB-NOT-OURS",
                processing_status="dead_letter",
                payload={"status": "succeeded", "amount": 1000},
            )
        )
        session.commit()

        report = client.get("/operations/attention", headers=admin_auth).json()
        assert len(report["dead_letter_events"]) == 1
        assert report["dead_letter_events"][0]["webhook_id"] == "wh-unknown"
        assert report["dead_letter_events"][0]["payload"]["amount"] == 1000

    def test_processed_webhooks_are_not_listed(self, client, admin_auth, session):
        session.add(
            ProviderEvent(
                provider="lipila",
                webhook_id="wh-fine",
                processing_status="processed",
                payload={},
            )
        )
        session.commit()

        report = client.get("/operations/attention", headers=admin_auth).json()
        assert report["dead_letter_events"] == []


class TestBalanceFindings:
    def test_an_unexplained_balance_is_surfaced(self, client, admin_auth, session, account):
        account.balance = 750.0
        session.add(account)
        session.commit()

        report = client.get("/operations/attention", headers=admin_auth).json()
        assert len(report["balance_discrepancies"]) == 1
        finding = report["balance_discrepancies"][0]
        assert finding["stored_balance"] == 750.0
        assert finding["derived_balance"] == 0.0
        assert finding["difference"] == 750.0

    def test_a_negative_balance_is_surfaced(self, client, admin_auth, session, account):
        account.balance = -25.0
        session.add(account)
        session.commit()

        report = client.get("/operations/attention", headers=admin_auth).json()
        assert len(report["negative_balances"]) == 1
        assert report["negative_balances"][0]["stored_balance"] == -25.0

    def test_a_clean_group_reports_nothing(self, client, admin_auth, session, account):
        report = client.get("/operations/attention", headers=admin_auth).json()
        assert report["stuck_payments"] == []
        assert report["balance_discrepancies"] == []
        assert report["negative_balances"] == []
        assert report["accounts_checked"] == 1


class TestAccess:
    def test_members_cannot_read_the_attention_queue(self, client, member_auth):
        assert client.get("/operations/attention", headers=member_auth).status_code == 403

    def test_it_needs_authentication(self, client):
        assert client.get("/operations/attention").status_code == 401
