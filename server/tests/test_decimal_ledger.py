"""What exact money buys the ledger.

`test_money.py` covers the arithmetic rules in isolation. These check the two
things the conversion was actually for: that the reconciliation comparison can
be exact, and that a schedule or a distribution built by the app adds back to
the figure it started from.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import select

from app.loan_service import create_loan_internal
from app.models import (
    GroupFee,
    Loan,
    LoanInstallment,
    RepaymentFrequency,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.money import ZERO, money
from app.reconciliation import check_account, derived_balance


class TestReconciliationIsExact:
    """The tolerance is gone. This is what replaced it."""

    def test_a_balance_built_from_entries_matches_to_the_ngwee(self, session, account):
        """The case that forced a half-ngwee tolerance when amounts were floats."""
        amounts = ["350.10", "350.10", "275.35", "420.55", "199.99", "350.10"] * 4
        for amount in amounts:
            session.add(
                Transaction(
                    account_id=account.id,
                    amount=Decimal(amount),
                    type=TransactionType.DEPOSIT,
                    status=TransactionStatus.COMPLETED,
                )
            )
            account.balance = money(account.balance) + Decimal(amount)
        session.add(account)
        session.commit()

        assert account.balance == Decimal("7784.76")
        assert check_account(session, account) is None

    def test_one_ngwee_out_is_now_caught(self, session, account):
        """Under the old tolerance this passed silently. It is the whole point.

        A half-ngwee of slack is exactly where a systematic rounding error — one
        that always favours the group over the member — would have hidden.
        """
        session.add(
            Transaction(
                account_id=account.id,
                amount=Decimal("100.00"),
                type=TransactionType.DEPOSIT,
                status=TransactionStatus.COMPLETED,
            )
        )
        account.balance = Decimal("100.01")
        session.add(account)
        session.commit()

        found = check_account(session, account)
        assert found is not None
        assert found.difference == Decimal("0.01")

    def test_derived_balance_returns_exact_decimal(self, session, account):
        entries = [
            Transaction(account_id=account.id, amount=Decimal("0.01"), type=TransactionType.DEPOSIT,
                        status=TransactionStatus.COMPLETED)
            for _ in range(300)
        ]
        assert derived_balance(entries) == Decimal("3.00")


class TestLoanScheduleBalances:
    """A schedule that does not add back to the loan is an audit finding."""

    @pytest.mark.parametrize("principal", ["1000.00", "333.33", "0.07", "99999.99"])
    @pytest.mark.parametrize("months", [1, 3, 7, 12])
    def test_installments_sum_to_the_loan(self, session, group, account, principal, months):
        account.balance = Decimal("999999.99")
        session.add(account)
        session.commit()

        loan = create_loan_internal(
            session=session,
            group_id=group.id,
            borrower_account_id=account.id,
            principal=Decimal(principal),
            term_months=months,
            repayment_frequency=RepaymentFrequency.MONTHLY,
            interest_rate_percent=Decimal("10"),
            description="schedule check",
        )

        installments = session.exec(
            select(LoanInstallment).where(LoanInstallment.loan_id == loan.id)
        ).all()

        principal_due = sum((money(i.principal_due) for i in installments), ZERO)
        interest_due = sum((money(i.interest_due) for i in installments), ZERO)

        assert principal_due == loan.principal
        assert interest_due == loan.outstanding_interest

    def test_an_indivisible_principal_still_balances(self, session, group, account):
        """K100 over 3 months is 33.333... per installment."""
        account.balance = Decimal("10000.00")
        session.add(account)
        session.commit()

        loan = create_loan_internal(
            session=session,
            group_id=group.id,
            borrower_account_id=account.id,
            principal=Decimal("100.00"),
            term_months=3,
            repayment_frequency=RepaymentFrequency.MONTHLY,
            interest_rate_percent=Decimal("10"),
            description="thirds",
        )
        installments = session.exec(
            select(LoanInstallment).where(LoanInstallment.loan_id == loan.id).order_by(LoanInstallment.sequence)
        ).all()
        amounts = sorted(money(i.principal_due) for i in installments)
        assert amounts == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
        assert sum(amounts, ZERO) == Decimal("100.00")


class TestInterestDistributionBalances:
    def test_the_fee_and_the_shares_account_for_every_ngwee(self, client, admin_auth, session, group, account):
        """Interest paid = admin fee + what the members receive. Exactly."""
        from app.models import Account, Membership, MembershipRole
        from app.auth import create_user
        from app.schemas import UserCreate

        # Three members with equal contributions, so the split is indivisible.
        others = []
        for index in range(2):
            user = create_user(
                session,
                UserCreate(email=f"m{index}@example.com", role="member", password="p"),
            )
            other = Account(name=f"Member {index}", group_id=group.id, user_id=user.id, balance=ZERO)
            session.add(other)
            session.commit()
            session.refresh(other)
            session.add(Membership(group_id=group.id, user_id=user.id, account_id=other.id,
                                   role=MembershipRole.MEMBER, accepted_terms_at=datetime.utcnow()))
            others.append(other)
        session.commit()

        for member in [account, *others]:
            session.add(
                Transaction(account_id=member.id, amount=Decimal("100.00"),
                            type=TransactionType.DEPOSIT, status=TransactionStatus.COMPLETED)
            )
            member.balance = Decimal("100.00")
            session.add(member)
        session.commit()

        loan = Loan(
            group_id=group.id,
            borrower_account_id=account.id,
            principal=Decimal("100.00"),
            interest_rate_percent=Decimal("10"),
            admin_fee_percent=Decimal("10"),
            term_months=1,
            outstanding_principal=Decimal("100.00"),
            outstanding_interest=Decimal("12.50"),
        )
        session.add(loan)
        session.commit()
        session.refresh(loan)

        response = client.post(
            f"/loans/{loan.id}/repay",
            json={"amount": 12.50, "interest_component": 12.50, "principal_component": 0},
            headers=admin_auth,
        )
        assert response.status_code == 200, response.text

        fee = sum((money(f.amount) for f in session.exec(select(GroupFee)).all()), ZERO)
        shares = sum(
            (money(t.amount) for t in session.exec(
                select(Transaction).where(Transaction.type == TransactionType.INTEREST)
            ).all()),
            ZERO,
        )
        # K12.50 interest: 10% fee = K1.25, leaving K11.25 shared three ways.
        assert fee == Decimal("1.25")
        assert shares == Decimal("11.25")
        assert fee + shares == Decimal("12.50")
