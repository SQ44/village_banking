"""A repayment is one event, and interest leaves a trail.

Two fixes are covered here. First, `repay_loan` used to commit four separate
times, so a crash partway through could leave a loan reduced with the members'
share of the interest never paid. Second, the scheduled interest job credited
balances without writing a ledger entry, which is money appearing from nowhere
as far as reconciliation is concerned.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from app.interest import apply_interest, calculate_interest
from app.ledger import InsufficientFunds, apply_status_change, reverse_balance
from app.models import (
    Account,
    GroupFee,
    Loan,
    LoanInstallment,
    LoanStatus,
    SavingsProduct,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.reconciliation import check_account


@pytest.fixture(name="loan")
def loan_fixture(session, group, account) -> Loan:
    account.balance = 1000.0
    session.add(account)
    loan = Loan(
        group_id=group.id,
        borrower_account_id=account.id,
        principal=500.0,
        interest_rate_percent=10.0,
        admin_fee_percent=10.0,
        term_months=2,
        outstanding_principal=500.0,
        outstanding_interest=50.0,
        status=LoanStatus.ACTIVE,
    )
    session.add(loan)
    session.commit()
    session.refresh(loan)

    for sequence in (1, 2):
        session.add(
            LoanInstallment(
                loan_id=loan.id,
                sequence=sequence,
                due_date=datetime.utcnow() + timedelta(days=30 * sequence),
                principal_due=250.0,
                interest_due=25.0,
            )
        )
    session.commit()
    return loan


class TestRepaymentIsOneEvent:
    def test_a_repayment_settles_everything_together(self, client, admin_auth, session, loan, account):
        """Loan, balance, installments and the interest split all move at once."""
        response = client.post(f"/loans/{loan.id}/repay", json={"amount": 275.0}, headers=admin_auth)
        assert response.status_code == 200, response.text

        session.refresh(loan)
        session.refresh(account)

        # 50 interest + 225 principal, per the repayment ordering.
        assert loan.outstanding_interest == 0
        assert loan.outstanding_principal == 275.0

        # The first installment is covered by 275.
        installments = session.exec(
            select(LoanInstallment).where(LoanInstallment.loan_id == loan.id).order_by(LoanInstallment.sequence)
        ).all()
        assert installments[0].status.value == "paid"
        assert installments[1].status.value == "due"

        # The admin fee was taken out of the interest.
        fees = session.exec(select(GroupFee)).all()
        assert len(fees) == 1
        assert fees[0].amount == 5.0

    def test_a_rejected_repayment_leaves_nothing_behind(self, client, admin_auth, session, loan, account):
        """A validation failure must not half-apply the repayment."""
        before_outstanding = loan.outstanding_principal
        before_balance = account.balance

        response = client.post(
            f"/loans/{loan.id}/repay",
            json={"amount": 100.0, "principal_component": 60.0, "interest_component": 10.0},
            headers=admin_auth,
        )
        assert response.status_code == 400

        session.refresh(loan)
        session.refresh(account)
        assert loan.outstanding_principal == before_outstanding
        assert account.balance == before_balance
        assert session.exec(select(Transaction)).all() == []

    def test_the_borrower_balance_and_ledger_agree_afterwards(
        self, client, admin_auth, session, loan, account
    ):
        """The repayment's own entries have to explain the balance it leaves."""
        # Start from a balance the ledger can account for.
        account.balance = 0.0
        session.add(account)
        session.add(
            Transaction(
                account_id=account.id,
                amount=1000.0,
                type=TransactionType.DEPOSIT,
                status=TransactionStatus.COMPLETED,
            )
        )
        account.balance = 1000.0
        session.add(account)
        session.commit()

        client.post(f"/loans/{loan.id}/repay", json={"amount": 275.0}, headers=admin_auth)
        session.refresh(account)

        assert check_account(session, account) is None


class TestInterestLeavesATrail:
    def test_applying_interest_writes_a_ledger_entry(self, session, account):
        """Without this the nightly job created money nothing explained."""
        account.balance = 1000.0
        session.add(account)
        session.commit()

        accrual, transaction = apply_interest(
            session,
            account,
            annual_rate=12.0,
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
        )

        assert transaction is not None
        assert transaction.type == TransactionType.INTEREST
        assert transaction.status == TransactionStatus.COMPLETED
        assert transaction.amount == accrual.amount
        assert transaction.custom_fields["interest_accrual_id"] == accrual.id

    def test_the_balance_still_reconciles_after_interest(self, session, account):
        session.add(
            Transaction(
                account_id=account.id,
                amount=1000.0,
                type=TransactionType.DEPOSIT,
                status=TransactionStatus.COMPLETED,
            )
        )
        account.balance = 1000.0
        session.add(account)
        session.commit()

        apply_interest(
            session,
            account,
            annual_rate=12.0,
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
        )

        assert check_account(session, account) is None

    def test_zero_interest_writes_no_entry(self, session, account):
        """An empty account earns nothing; nothing is not a ledger movement."""
        accrual, transaction = apply_interest(
            session,
            account,
            annual_rate=12.0,
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
        )
        assert accrual.amount == 0
        assert transaction is None

    def test_the_scheduled_job_also_leaves_a_trail(self, session, account, monkeypatch):
        """The nightly path, not just the admin button."""
        product = SavingsProduct(name="Standard", interest_rate=12.0, compounding_days=30)
        session.add(product)
        session.commit()
        session.refresh(product)

        account.product_id = product.id
        account.balance = 1000.0
        account.created_at = datetime.utcnow() - timedelta(days=60)
        session.add(account)
        session.add(
            Transaction(
                account_id=account.id,
                amount=1000.0,
                type=TransactionType.DEPOSIT,
                status=TransactionStatus.COMPLETED,
            )
        )
        session.commit()

        from app import tasks

        monkeypatch.setattr(tasks, "engine", session.get_bind())
        tasks.run_scheduled_interest()

        session.refresh(account)
        interest_entries = session.exec(
            select(Transaction).where(Transaction.type == TransactionType.INTEREST)
        ).all()
        assert len(interest_entries) == 1
        assert check_account(session, account) is None


class TestReversalGoesNegative:
    def test_a_chargeback_after_spending_leaves_a_real_debt(self, session, account):
        """Clamping at zero would invent the difference and hide the debt."""
        deposit = Transaction(
            account_id=account.id,
            amount=300.0,
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.COMPLETED,
        )
        account.balance = 50.0  # 300 in, 250 already spent.
        session.add_all([deposit, account])
        session.commit()

        reverse_balance(account, deposit)
        assert account.balance == -250.0

    def test_nothing_can_be_spent_from_a_negative_balance(self, session, account):
        account.balance = -250.0
        withdrawal = Transaction(
            account_id=account.id,
            amount=10.0,
            type=TransactionType.WITHDRAWAL,
            status=TransactionStatus.PENDING,
        )
        with pytest.raises(InsufficientFunds):
            apply_status_change(account, withdrawal, TransactionStatus.COMPLETED)
