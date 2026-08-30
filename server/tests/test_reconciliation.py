"""Proving a stored balance against the entries behind it.

The rules under test mirror `ledger.apply_status_change`, so these double as a
specification of when a transaction is supposed to move a balance and when it
is not.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models import Account, Transaction, TransactionStatus, TransactionType
from app.reconciliation import check_account, check_all, derived_balance, transaction_effect


def _tx(**kwargs) -> Transaction:
    defaults = dict(
        account_id=1,
        amount=100.0,
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.COMPLETED,
        created_at=datetime.utcnow(),
    )
    return Transaction(**{**defaults, **kwargs})


class TestTransactionEffect:
    """What one transaction should have done to a balance."""

    def test_completed_deposit_credits(self):
        assert transaction_effect(_tx(type=TransactionType.DEPOSIT)) == 100.0

    def test_completed_repayment_credits(self):
        assert transaction_effect(_tx(type=TransactionType.LOAN_REPAYMENT)) == 100.0

    def test_completed_interest_credits(self):
        assert transaction_effect(_tx(type=TransactionType.INTEREST)) == 100.0

    def test_completed_fee_debits(self):
        assert transaction_effect(_tx(type=TransactionType.FEE)) == -100.0

    def test_completed_withdrawal_debits(self):
        assert transaction_effect(_tx(type=TransactionType.WITHDRAWAL)) == -100.0

    def test_pending_deposit_moves_nothing(self):
        """Money merely requested is not money received."""
        assert transaction_effect(_tx(status=TransactionStatus.PENDING)) == 0.0

    def test_failed_deposit_moves_nothing(self):
        assert transaction_effect(_tx(status=TransactionStatus.FAILED)) == 0.0

    def test_pending_provider_payout_is_already_debited(self):
        """Payouts reserve their funds when requested, not when they settle.

        Otherwise the same balance could be withdrawn again while the first
        payout is still in flight.
        """
        payout = _tx(
            type=TransactionType.WITHDRAWAL,
            status=TransactionStatus.PENDING,
            provider_reference="VB-ABC",
        )
        assert transaction_effect(payout) == -100.0

    def test_completed_provider_payout_is_not_debited_twice(self):
        payout = _tx(
            type=TransactionType.WITHDRAWAL,
            status=TransactionStatus.COMPLETED,
            provider_reference="VB-ABC",
        )
        assert transaction_effect(payout) == -100.0

    def test_failed_provider_payout_hands_the_money_back(self):
        payout = _tx(
            type=TransactionType.WITHDRAWAL,
            status=TransactionStatus.FAILED,
            provider_reference="VB-ABC",
        )
        assert transaction_effect(payout) == 0.0

    def test_pending_manual_withdrawal_moves_nothing(self):
        """No provider reference means nothing was reserved up front."""
        assert transaction_effect(
            _tx(type=TransactionType.WITHDRAWAL, status=TransactionStatus.PENDING)
        ) == 0.0


class TestDerivedBalance:
    def test_sums_a_history(self):
        history = [
            _tx(amount=500.0, type=TransactionType.DEPOSIT),
            _tx(amount=200.0, type=TransactionType.DEPOSIT),
            _tx(amount=100.0, type=TransactionType.WITHDRAWAL),
            _tx(amount=50.0, type=TransactionType.INTEREST),
            _tx(amount=25.0, type=TransactionType.FEE),
        ]
        assert derived_balance(history) == 625.0

    def test_an_empty_history_is_zero(self):
        assert derived_balance([]) == 0.0


class TestCheckAccount:
    def test_an_explained_balance_is_not_reported(self, session, account):
        account.balance = 300.0
        session.add(account)
        session.add(_tx(account_id=account.id, amount=300.0))
        session.commit()

        assert check_account(session, account) is None

    def test_a_balance_with_no_entry_behind_it_is_reported(self, session, account):
        """The exact shape of a hand-edited balance, or a lost ledger write."""
        account.balance = 300.0
        session.add(account)
        session.commit()

        found = check_account(session, account)
        assert found is not None
        assert found.stored_balance == 300.0
        assert found.derived_balance == 0.0
        assert found.difference == 300.0

    def test_an_entry_with_no_balance_behind_it_is_reported(self, session, account):
        account.balance = 0.0
        session.add(account)
        session.add(_tx(account_id=account.id, amount=300.0))
        session.commit()

        found = check_account(session, account)
        assert found is not None
        assert found.difference == -300.0

    def test_float_noise_is_tolerated(self, session, account):
        """Half a ngwee is representation error, not a disagreement."""
        account.balance = 300.001
        session.add(account)
        session.add(_tx(account_id=account.id, amount=300.0))
        session.commit()

        assert check_account(session, account) is None


class TestCheckAll:
    def test_a_clean_ledger_reports_ok(self, session, account):
        account.balance = 100.0
        session.add(account)
        session.add(_tx(account_id=account.id, amount=100.0))
        session.commit()

        report = check_all(session)
        assert report.ok
        assert report.checked == 1

    def test_a_negative_balance_is_reported_separately(self, session, account):
        """Not a bookkeeping error — a reversal after the money was spent.

        The number is right and must not be "fixed"; it needs a human.
        """
        account.balance = -50.0
        session.add(account)
        session.add(_tx(account_id=account.id, amount=100.0))
        session.add(_tx(account_id=account.id, amount=150.0, type=TransactionType.WITHDRAWAL))
        session.commit()

        report = check_all(session)
        assert not report.ok
        assert len(report.negative_balances) == 1
        assert report.negative_balances[0].stored_balance == -50.0
        # The entries do explain it, so it is not also a mismatch.
        assert report.discrepancies == []

    def test_scoped_to_one_group(self, session, account, group):
        outsider = Account(name="Other group", group_id=999, balance=999.0)
        session.add(outsider)
        account.balance = 0.0
        session.add(account)
        session.commit()

        report = check_all(session, group_id=group.id)
        assert report.checked == 1
        assert report.ok
