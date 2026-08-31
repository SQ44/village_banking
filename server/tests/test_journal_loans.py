"""How lending shows up in the books.

A repayment is two movements, not one. The loan router already separates them —
principal restores the borrower's savings, interest is taken from them — but the
journal was booking both against the loan and calling the interest an ordinary
fee. Interest earned on lending is the group's income and the main reason the
pot grows; recording it as a service charge hid the one number members meet to
hear.

These tests pin the distinction down, and then prove it end to end through the
real repayment endpoint, because the split is only worth anything if it survives
the path an actual repayment takes.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import select

from app import journal
from app.models import (
    Account,
    JournalEntry,
    Loan,
    LoanStatus,
    RepaymentFrequency,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.money import money


def _tx(account: Account, **kwargs) -> Transaction:
    defaults = dict(
        account_id=account.id,
        amount=money("100.00"),
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.COMPLETED,
        created_at=datetime.utcnow(),
    )
    return Transaction(**{**defaults, **kwargs})


def _codes(session, entry: JournalEntry) -> dict[str, tuple]:
    from app.models import JournalLine

    return {
        line.account_code: (journal.from_minor(line.debit_minor), journal.from_minor(line.credit_minor))
        for line in session.exec(
            select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
        ).all()
    }


class TestInterestIsIncomeNotAFee:
    def test_the_interest_half_of_a_repayment_is_income(self, session, account):
        """What the group earned by lending, told apart from what it charged."""
        transaction = _tx(
            account,
            amount=money("15.00"),
            type=TransactionType.FEE,
            description="Loan repayment (interest)",
            custom_fields={"loan_id": 1, "component": "interest"},
        )
        session.add(transaction)
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _codes(session, entry)
        assert codes[journal.MEMBER_SAVINGS] == (money("15.00"), money("0.00"))
        assert codes[journal.INTEREST_INCOME] == (money("0.00"), money("15.00"))
        assert journal.FEE_INCOME not in codes
        assert journal.entry_is_balanced(session, entry)

    def test_an_ordinary_charge_is_still_a_fee(self, session, account):
        transaction = _tx(account, amount=money("5.00"), type=TransactionType.FEE,
                          description="Late charge")
        session.add(transaction)
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _codes(session, entry)
        assert codes[journal.FEE_INCOME] == (money("0.00"), money("5.00"))
        assert journal.INTEREST_INCOME not in codes


class TestPrincipalMovesSavingsNotIncome:
    def test_a_principal_repayment_restores_savings(self, session, account):
        """The borrower's own savings funded the loan, so repaying returns them.

        No income arises: the group is no better off for being paid back what it
        lent. Only the interest is a gain.
        """
        transaction = _tx(
            account,
            amount=money("100.00"),
            type=TransactionType.LOAN_REPAYMENT,
            custom_fields={"loan_id": 1, "component": "principal"},
        )
        session.add(transaction)
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _codes(session, entry)
        assert codes[journal.MEMBER_SAVINGS] == (money("0.00"), money("100.00"))
        assert journal.INTEREST_INCOME not in codes
        assert journal.FEE_INCOME not in codes
        assert journal.entry_is_balanced(session, entry)

    def test_a_disbursement_draws_the_savings_down(self, session, account):
        account.balance = money("500.00")
        transaction = _tx(account, amount=money("200.00"),
                          type=TransactionType.LOAN_DISBURSEMENT,
                          custom_fields={"loan_id": 1})
        session.add_all([account, transaction])
        session.commit()

        entry = journal.post_transaction(session, transaction, account)
        session.commit()

        codes = _codes(session, entry)
        assert codes[journal.MEMBER_SAVINGS] == (money("200.00"), money("0.00"))
        assert journal.entry_is_balanced(session, entry)


class TestARealRepayment:
    """Through the endpoint a borrower actually uses."""

    def _loan(self, session, account, principal="1000.00", interest="100.00") -> Loan:
        loan = Loan(
            group_id=account.group_id,
            borrower_account_id=account.id,
            principal=money(principal),
            interest_rate_percent=money("10.00"),
            admin_fee_percent=money("0.00"),
            term_months=3,
            repayment_frequency=RepaymentFrequency.MONTHLY,
            outstanding_principal=money(principal),
            outstanding_interest=money(interest),
            status=LoanStatus.ACTIVE,
            created_at=datetime.utcnow(),
            disbursed_at=datetime.utcnow(),
            custom_fields={},
        )
        session.add(loan)
        session.commit()
        session.refresh(loan)
        return loan

    def test_interest_first_then_principal_reaches_the_books(
        self, client, session, account, admin_auth
    ):
        """A K150 repayment against K100 interest owed: K100 income, K50 principal."""
        loan = self._loan(session, account, principal="1000.00", interest="100.00")
        account.balance = money("0.00")
        session.add(account)
        session.commit()

        response = client.post(
            f"/loans/{loan.id}/repay",
            headers=admin_auth,
            json={"amount": "150.00"},
        )
        assert response.status_code == 200, response.text

        balances = journal.trial_balance(session)
        assert balances[journal.INTEREST_INCOME] == money("100.00")
        assert balances.get(journal.FEE_INCOME, money("0.00")) == money("0.00")
        assert journal.books_are_balanced(session) is True
        assert journal.control_total_matches(session) is True

    def test_interest_income_accumulates_across_repayments(
        self, client, session, account, admin_auth
    ):
        loan = self._loan(session, account, principal="1000.00", interest="100.00")
        account.balance = money("0.00")
        session.add(account)
        session.commit()

        for amount in ("40.00", "35.00"):
            response = client.post(
                f"/loans/{loan.id}/repay", headers=admin_auth, json={"amount": amount}
            )
            assert response.status_code == 200, response.text

        assert journal.trial_balance(session)[journal.INTEREST_INCOME] == money("75.00")
        assert journal.books_are_balanced(session) is True

    def test_an_explicit_split_is_respected(self, client, session, account, admin_auth):
        loan = self._loan(session, account, principal="1000.00", interest="100.00")
        account.balance = money("0.00")
        session.add(account)
        session.commit()

        response = client.post(
            f"/loans/{loan.id}/repay",
            headers=admin_auth,
            json={"amount": "100.00", "interest_component": "30.00", "principal_component": "70.00"},
        )
        assert response.status_code == 200, response.text

        balances = journal.trial_balance(session)
        assert balances[journal.INTEREST_INCOME] == money("30.00")
        assert journal.books_are_balanced(session) is True
        assert journal.control_total_matches(session) is True


class TestLoanFiguresReadTheRightWayRound:
    """A stat card showing negative money out on loan would be nonsense."""

    def test_no_receivable_is_invented_by_a_disbursement(self, session, account):
        """The borrower funded their own loan, so the group is owed nothing new.

        Booking a receivable here produced a negative figure for money out on
        loan — money the group had supposedly lent, shown as less than nothing.
        """
        account.balance = money("500.00")
        disbursement = _tx(account, amount=money("200.00"),
                           type=TransactionType.LOAN_DISBURSEMENT,
                           custom_fields={"loan_id": 1})
        session.add_all([account, disbursement])
        session.commit()
        journal.post_transaction(session, disbursement, account)
        session.commit()

        assert journal.LOANS_RECEIVABLE not in journal.trial_balance(session)

    def test_money_out_on_loan_is_read_from_the_loans(self, client, session, account, admin_auth):
        """What is genuinely still owed, and never a negative number."""
        from app.models import Loan, LoanStatus, RepaymentFrequency

        session.add(
            Loan(
                group_id=account.group_id,
                borrower_account_id=account.id,
                principal=money("300.00"),
                interest_rate_percent=money("10.00"),
                admin_fee_percent=money("0.00"),
                term_months=3,
                repayment_frequency=RepaymentFrequency.MONTHLY,
                outstanding_principal=money("180.00"),
                outstanding_interest=money("20.00"),
                status=LoanStatus.ACTIVE,
                created_at=datetime.utcnow(),
                disbursed_at=datetime.utcnow(),
                custom_fields={},
            )
        )
        session.commit()

        body = client.get("/operations/trial-balance", headers=admin_auth).json()
        assert money(body["loans_outstanding"]) == money("180.00")

    def test_a_loan_lent_and_repaid_leaves_savings_whole(self, session, account):
        """Out and back again: the member ends where they started."""
        account.balance = money("500.00")
        session.add(account)
        session.commit()

        out = _tx(account, amount=money("200.00"), type=TransactionType.LOAN_DISBURSEMENT,
                  custom_fields={"loan_id": 1})
        session.add(out)
        session.commit()
        journal.post_transaction(session, out, account)
        session.commit()

        back = _tx(account, amount=money("200.00"), type=TransactionType.LOAN_REPAYMENT,
                   custom_fields={"loan_id": 1, "component": "principal"})
        session.add(back)
        session.commit()
        journal.post_transaction(session, back, account)
        session.commit()

        assert journal.trial_balance(session)[journal.MEMBER_SAVINGS] == money("0.00")
        assert journal.books_are_balanced(session) is True
