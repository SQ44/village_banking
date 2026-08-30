"""Double-entry postings behind every balance that moves.

The stored balance on an account answers "how much". These entries answer
"where from" and "where to", which is what an admin is actually asked in a
meeting. Each test here is a rule the books have to keep:

* every entry balances, to the ngwee;
* the `member_savings` control total equals the sum of member balances;
* money that has not arrived is not posted;
* the same event posted twice moves nothing the second time.

The fee cases matter most. A member paying K100 through Lipila does not put
K100 in the group's hands, and a ledger that records only the gross has a hole
in it that grows with every collection.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlmodel import select

from app import journal
from app.models import (
    Account,
    JournalEntry,
    JournalLine,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.money import money


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _tx(account: Account, **kwargs) -> Transaction:
    defaults = dict(
        account_id=account.id,
        amount=money("100.00"),
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.COMPLETED,
        created_at=datetime.utcnow(),
    )
    return Transaction(**{**defaults, **kwargs})


def _lines(session, entry: JournalEntry) -> list[JournalLine]:
    return list(session.exec(select(JournalLine).where(JournalLine.journal_entry_id == entry.id)).all())


def _by_code(session, entry: JournalEntry) -> dict[str, tuple[Decimal, Decimal]]:
    """{account_code: (debit, credit)} for one entry."""
    return {
        line.account_code: (journal.from_minor(line.debit_minor), journal.from_minor(line.credit_minor))
        for line in _lines(session, entry)
    }


# ----------------------------------------------------------------------


class TestEntriesBalance:
    """No entry may leave the books lopsided."""

    def test_collection_splits_gross_between_settlement_and_fee(self, session, account):
        """A K100 payment with a K2.50 fee puts K97.50 in reach, not K100.

        The member is owed the full K100 they paid. Only K97.50 ever reaches
        the group. The K2.50 difference is an expense, and naming it is the
        only way the books can balance without quietly overstating what the
        group holds.
        """
        transaction = _tx(account, amount=money("100.00"), provider="lipila",
                          provider_reference="VB-FEE1", provider_fee=money("2.50"))
        session.add(transaction)
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _by_code(session, entry)
        assert codes[journal.LIPILA_SETTLEMENT] == (money("97.50"), money("0.00"))
        assert codes[journal.PROVIDER_FEES] == (money("2.50"), money("0.00"))
        assert codes[journal.MEMBER_SAVINGS] == (money("0.00"), money("100.00"))
        assert journal.entry_is_balanced(session, entry)

    def test_zero_fee_collection_still_balances(self, session, account):
        transaction = _tx(account, amount=money("50.00"), provider="lipila",
                          provider_reference="VB-NOFEE")
        session.add(transaction)
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _by_code(session, entry)
        assert codes[journal.LIPILA_SETTLEMENT] == (money("50.00"), money("0.00"))
        assert codes[journal.MEMBER_SAVINGS] == (money("0.00"), money("50.00"))
        assert journal.PROVIDER_FEES not in codes  # No fee, no line.
        assert journal.entry_is_balanced(session, entry)

    def test_cash_contribution_lands_in_cash_not_at_the_provider(self, session, account):
        """Cash in a tin is not money at Lipila, and must not read as if it were."""
        transaction = _tx(account, amount=money("300.00"),
                          custom_fields={"settled_in": "cash"})
        session.add(transaction)
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _by_code(session, entry)
        assert codes[journal.CASH_ON_HAND] == (money("300.00"), money("0.00"))
        assert codes[journal.MEMBER_SAVINGS] == (money("0.00"), money("300.00"))
        assert journal.LIPILA_SETTLEMENT not in codes
        assert journal.entry_is_balanced(session, entry)

    def test_withdrawal_takes_the_fee_from_the_group_not_the_member(self, session, account):
        """A member withdrawing K100 receives K100; the group absorbs the charge."""
        account.balance = money("500.00")
        transaction = _tx(account, amount=money("100.00"), type=TransactionType.WITHDRAWAL,
                          provider="lipila", provider_reference="VB-OUT1",
                          provider_fee=money("1.50"))
        session.add_all([account, transaction])
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _by_code(session, entry)
        assert codes[journal.MEMBER_SAVINGS] == (money("100.00"), money("0.00"))
        assert codes[journal.PROVIDER_FEES] == (money("1.50"), money("0.00"))
        assert codes[journal.LIPILA_SETTLEMENT] == (money("0.00"), money("101.50"))
        assert journal.entry_is_balanced(session, entry)

    def test_interest_credited_to_a_saver_is_an_expense_to_the_group(self, session, account):
        transaction = _tx(account, amount=money("12.34"), type=TransactionType.INTEREST)
        session.add(transaction)
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _by_code(session, entry)
        assert codes[journal.INTEREST_EXPENSE] == (money("12.34"), money("0.00"))
        assert codes[journal.MEMBER_SAVINGS] == (money("0.00"), money("12.34"))
        assert journal.entry_is_balanced(session, entry)

    def test_fee_charged_to_a_member_is_income(self, session, account):
        account.balance = money("100.00")
        transaction = _tx(account, amount=money("5.00"), type=TransactionType.FEE)
        session.add_all([account, transaction])
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _by_code(session, entry)
        assert codes[journal.MEMBER_SAVINGS] == (money("5.00"), money("0.00"))
        assert codes[journal.FEE_INCOME] == (money("0.00"), money("5.00"))
        assert journal.entry_is_balanced(session, entry)


class TestNothingPostedForMoneyThatHasNotMoved:
    """A request for money is not money."""

    @pytest.mark.parametrize("status", [TransactionStatus.PENDING, TransactionStatus.FAILED])
    def test_unsettled_collection_posts_nothing(self, session, account, status):
        transaction = _tx(account, status=status, provider="lipila",
                          provider_reference=f"VB-{status.value.upper()}")
        session.add(transaction)
        session.commit()

        assert journal.post_transaction(session, transaction, account) is None
        session.commit()
        assert session.exec(select(JournalEntry)).all() == []

    def test_failed_payout_posts_nothing(self, session, account):
        """The reservation was handed back, so the books never saw it leave."""
        transaction = _tx(account, amount=money("40.00"), type=TransactionType.WITHDRAWAL,
                          status=TransactionStatus.FAILED, provider="lipila",
                          provider_reference="VB-OUTFAIL")
        session.add(transaction)
        session.commit()

        assert journal.post_transaction(session, transaction, account) is None
        session.commit()
        assert session.exec(select(JournalEntry)).all() == []


class TestPostingTwiceChangesNothing:
    """A redelivered webhook must not double the books."""

    def test_same_transaction_posts_once(self, session, account):
        transaction = _tx(account, amount=money("75.00"), provider="lipila",
                          provider_reference="VB-DUP")
        session.add(transaction)
        session.commit()

        first = journal.post_transaction(session, transaction, account)
        session.commit()
        second = journal.post_transaction(session, transaction, account)
        session.commit()

        assert first is not None
        assert second is None or second.id == first.id
        assert len(session.exec(select(JournalEntry)).all()) == 1
        assert journal.trial_balance(session)[journal.MEMBER_SAVINGS] == money("75.00")


class TestControlTotal:
    """The books and the balances have to tell the same story."""

    def test_member_savings_matches_the_sum_of_balances(self, session, account):
        """The one check that catches the ledger drifting from the accounts."""
        for amount, ref in ((money("100.00"), "VB-C1"), (money("250.50"), "VB-C2")):
            transaction = _tx(account, amount=amount, provider="lipila", provider_reference=ref)
            session.add(transaction)
            session.commit()
            journal.post_transaction(session, transaction, account)
            account.balance = money(account.balance) + amount
            session.add(account)
            session.commit()

        assert journal.trial_balance(session)[journal.MEMBER_SAVINGS] == money("350.50")
        assert journal.control_total_matches(session) is True

    def test_a_balance_edited_behind_the_books_is_caught(self, session, account):
        """Exactly the silent hand on the pot this is meant to expose."""
        transaction = _tx(account, amount=money("100.00"), provider="lipila",
                          provider_reference="VB-EDIT")
        session.add(transaction)
        session.commit()
        journal.post_transaction(session, transaction, account)
        account.balance = money("100.00")
        session.add(account)
        session.commit()
        assert journal.control_total_matches(session) is True

        account.balance = money("999.00")  # No entry behind it.
        session.add(account)
        session.commit()
        assert journal.control_total_matches(session) is False


class TestTrialBalance:
    def test_debits_equal_credits_across_every_entry(self, session, account):
        for amount, ref, fee in (
            (money("100.00"), "VB-T1", money("2.50")),
            (money("60.00"), "VB-T2", money("0.00")),
        ):
            transaction = _tx(account, amount=amount, provider="lipila",
                              provider_reference=ref, provider_fee=fee)
            session.add(transaction)
            session.commit()
            journal.post_transaction(session, transaction, account)
            session.commit()

        assert journal.books_are_balanced(session) is True

    def test_scoped_to_one_group(self, session, account, group):
        transaction = _tx(account, amount=money("80.00"), provider="lipila",
                          provider_reference="VB-G1")
        session.add(transaction)
        session.commit()
        journal.post_transaction(session, transaction, account)
        session.commit()

        assert journal.trial_balance(session, group_id=group.id)[journal.MEMBER_SAVINGS] == money("80.00")
        assert journal.trial_balance(session, group_id=group.id + 999) == {}


class TestStatement:
    """What a member is shown when they ask where their money went."""

    def test_lists_movements_with_a_running_balance(self, session, account):
        deposit = _tx(account, amount=money("100.00"), provider="lipila", provider_reference="VB-S1")
        session.add(deposit)
        session.commit()
        journal.post_transaction(session, deposit, account)
        account.balance = money("100.00")
        session.add(account)
        session.commit()

        withdrawal = _tx(account, amount=money("30.00"), type=TransactionType.WITHDRAWAL,
                         provider="lipila", provider_reference="VB-S2")
        session.add(withdrawal)
        session.commit()
        journal.post_transaction(session, withdrawal, account)
        account.balance = money("70.00")
        session.add(account)
        session.commit()

        statement = journal.statement(session, account_id=account.id)
        assert [line.running_balance for line in statement] == [money("100.00"), money("70.00")]
        assert statement[-1].running_balance == money(account.balance)
