"""The member on a weak network who taps Pay twice.

These are the tests that matter most in the suite. Every one of them asserts on
how many times Lipila was actually asked to collect, because that number is how
many prompts land on a member's handset and how many times their K300 can leave
their wallet.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from app.idempotency import fingerprint
from app.models import IdempotencyRecord, Transaction, TransactionStatus, TransactionType


def _deposit(account_id: int, amount: float = 300.0) -> dict:
    return {
        "account_id": account_id,
        "amount": amount,
        "type": "deposit",
        "use_lipila": True,
        "channel": "mobile_money",
        "phone_number": "0977123456",
    }


class TestRetryWithSameKey:
    """A lost response, then the identical request again."""

    def test_retry_returns_first_response_without_charging_again(
        self, client, member_auth, account, fake_lipila, session
    ):
        body = _deposit(account.id)
        headers = {**member_auth, "Idempotency-Key": "attempt-1"}

        first = client.post("/transactions", json=body, headers=headers)
        assert first.status_code == 201, first.text

        # The reply was lost; the phone sends exactly the same thing again.
        second = client.post("/transactions", json=body, headers=headers)
        assert second.status_code == 201, second.text

        # Same transaction, not a second one.
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["provider_reference"] == first.json()["provider_reference"]

        # And, the point of the whole exercise: Lipila was asked once.
        assert len(fake_lipila.calls) == 1

        transactions = session.exec(
            select(Transaction).where(Transaction.account_id == account.id)
        ).all()
        assert len(transactions) == 1

    def test_three_retries_still_collect_once(self, client, member_auth, account, fake_lipila):
        body = _deposit(account.id)
        headers = {**member_auth, "Idempotency-Key": "attempt-flaky"}

        responses = [client.post("/transactions", json=body, headers=headers) for _ in range(4)]

        assert [r.status_code for r in responses] == [201, 201, 201, 201]
        assert len({r.json()["id"] for r in responses}) == 1
        assert len(fake_lipila.calls) == 1

    def test_different_keys_are_different_intents(self, client, member_auth, account, fake_lipila):
        """A member genuinely contributing twice must not be blocked.

        The duplicate-collection guard only holds for a few minutes and only for
        an identical amount, so a second, different contribution goes through.
        """
        headers_one = {**member_auth, "Idempotency-Key": "contribution-june"}
        headers_two = {**member_auth, "Idempotency-Key": "contribution-july"}

        first = client.post("/transactions", json=_deposit(account.id, 300), headers=headers_one)
        second = client.post("/transactions", json=_deposit(account.id, 500), headers=headers_two)

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] != second.json()["id"]
        assert len(fake_lipila.calls) == 2


class TestKeyMisuse:
    def test_same_key_with_a_different_body_is_refused(self, client, member_auth, account, fake_lipila):
        """Answering with the first response here would hide a real client bug."""
        headers = {**member_auth, "Idempotency-Key": "reused"}

        first = client.post("/transactions", json=_deposit(account.id, 300), headers=headers)
        assert first.status_code == 201

        second = client.post("/transactions", json=_deposit(account.id, 900), headers=headers)
        assert second.status_code == 422
        assert second.json()["detail"] == "idempotency_key_reused_with_different_body"
        assert len(fake_lipila.calls) == 1

    def test_in_flight_key_is_refused_rather_than_duplicated(
        self, client, member_auth, account, session, fake_lipila
    ):
        """A claim that has not completed means "I am already doing that"."""
        session.add(
            IdempotencyRecord(
                scope=f"POST /transactions|{account.user_id}|busy",
                endpoint="POST /transactions",
                user_id=account.user_id,
                request_fingerprint=fingerprint(
                    {
                        "account_id": account.id,
                        "amount": 300.0,
                        "type": "deposit",
                        "description": None,
                        "custom_fields": {},
                        "status": "pending",
                        "use_lipila": True,
                        "channel": "mobile_money",
                        "phone_number": "0977123456",
                    }
                ),
                state="in_progress",
            )
        )
        session.commit()

        response = client.post(
            "/transactions",
            json=_deposit(account.id),
            headers={**member_auth, "Idempotency-Key": "busy"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "request_already_in_progress"
        assert fake_lipila.calls == []

    def test_a_failed_attempt_gives_the_key_back(self, client, member_auth, account, fake_lipila):
        """A rejected request burned no money, so the same key must work again.

        Otherwise a member who mistypes their number is locked out of retrying
        until their client invents a new key — which it has no reason to do,
        because from its point of view nothing succeeded.
        """
        headers = {**member_auth, "Idempotency-Key": "typo-then-fix"}

        bad = dict(_deposit(account.id), phone_number="123")
        first = client.post("/transactions", json=bad, headers=headers)
        assert first.status_code == 400

        # Same key, corrected number.
        second = client.post("/transactions", json=_deposit(account.id), headers=headers)
        assert second.status_code == 201, second.text
        assert len(fake_lipila.calls) == 1

    def test_a_key_is_scoped_to_its_sender(self, client, member_auth, admin_auth, account, fake_lipila):
        """Two people using the same key value are not one another's retry."""
        body = _deposit(account.id)

        member = client.post(
            "/transactions", json=body, headers={**member_auth, "Idempotency-Key": "shared"}
        )
        admin = client.post(
            "/transactions", json=body, headers={**admin_auth, "Idempotency-Key": "shared"}
        )

        assert member.status_code == 201
        # The admin's request is a different claim; it is stopped by the live
        # collection guard instead, which is the correct protection here.
        assert admin.status_code == 201
        assert admin.json()["id"] == member.json()["id"]
        assert len(fake_lipila.calls) == 1


class TestWithoutAKey:
    def test_an_old_client_still_works(self, client, member_auth, account, fake_lipila):
        """No header means no protection, not a rejection."""
        response = client.post("/transactions", json=_deposit(account.id), headers=member_auth)
        assert response.status_code == 201
        assert len(fake_lipila.calls) == 1

    def test_an_overlong_key_is_rejected(self, client, member_auth, account):
        response = client.post(
            "/transactions",
            json=_deposit(account.id),
            headers={**member_auth, "Idempotency-Key": "x" * 500},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "invalid_idempotency_key"


class TestDoubleTap:
    """Two presses of the button — two requests, two keys, one member's money."""

    def test_second_press_returns_the_prompt_already_waiting(
        self, client, member_auth, account, fake_lipila
    ):
        first = client.post(
            "/transactions", json=_deposit(account.id), headers={**member_auth, "Idempotency-Key": "tap-1"}
        )
        second = client.post(
            "/transactions", json=_deposit(account.id), headers={**member_auth, "Idempotency-Key": "tap-2"}
        )

        assert first.status_code == 201
        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]
        assert len(fake_lipila.calls) == 1

    def test_a_settled_payment_does_not_block_the_next_contribution(
        self, client, member_auth, account, session, fake_lipila
    ):
        """The guard is for prompts still waiting, not for history."""
        first = client.post(
            "/transactions", json=_deposit(account.id), headers={**member_auth, "Idempotency-Key": "tap-1"}
        )
        assert first.status_code == 201

        settled = session.get(Transaction, first.json()["id"])
        settled.status = TransactionStatus.COMPLETED
        session.add(settled)
        session.commit()

        second = client.post(
            "/transactions", json=_deposit(account.id), headers={**member_auth, "Idempotency-Key": "tap-2"}
        )
        assert second.status_code == 201
        assert second.json()["id"] != first.json()["id"]
        assert len(fake_lipila.calls) == 2

    def test_an_expired_prompt_does_not_block_a_new_one(
        self, client, member_auth, account, session, fake_lipila
    ):
        """Past the window, an unanswered prompt is stale, not live."""
        first = client.post(
            "/transactions", json=_deposit(account.id), headers={**member_auth, "Idempotency-Key": "tap-1"}
        )
        stale = session.get(Transaction, first.json()["id"])
        stale.created_at = datetime.utcnow() - timedelta(minutes=30)
        session.add(stale)
        session.commit()

        second = client.post(
            "/transactions", json=_deposit(account.id), headers={**member_auth, "Idempotency-Key": "tap-2"}
        )
        assert second.json()["id"] != first.json()["id"]
        assert len(fake_lipila.calls) == 2


class TestRepaymentIdempotency:
    def test_a_repaid_loan_is_not_repaid_twice(self, client, admin_auth, session, group, account):
        """A retried repayment would credit the borrower and pay out interest twice."""
        from app.models import Loan, LoanStatus

        account.balance = 1000.0
        session.add(account)
        loan = Loan(
            group_id=group.id,
            borrower_account_id=account.id,
            principal=500.0,
            interest_rate_percent=10.0,
            admin_fee_percent=0.0,
            term_months=1,
            outstanding_principal=500.0,
            outstanding_interest=50.0,
            status=LoanStatus.ACTIVE,
        )
        session.add(loan)
        session.commit()
        session.refresh(loan)

        headers = {**admin_auth, "Idempotency-Key": "repay-once"}
        body = {"amount": 100.0}

        first = client.post(f"/loans/{loan.id}/repay", json=body, headers=headers)
        assert first.status_code == 200, first.text
        outstanding_after_first = first.json()["outstanding_interest"], first.json()["outstanding_principal"]

        second = client.post(f"/loans/{loan.id}/repay", json=body, headers=headers)
        assert second.status_code == 200

        # The retry reports the same state and did not reduce the loan again.
        assert (second.json()["outstanding_interest"], second.json()["outstanding_principal"]) == outstanding_after_first

        session.refresh(loan)
        assert round(loan.outstanding_interest + loan.outstanding_principal, 2) == 450.0
