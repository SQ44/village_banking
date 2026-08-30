from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlmodel import Session

from .group_finance import net_contributions_by_account
from .money import ZERO, allocate, money, percent_of, rate as as_rate
from .models import (
    Account,
    Group,
    GroupSettings,
    InstallmentStatus,
    Loan,
    LoanInstallment,
    LoanStatus,
    RepaymentFrequency,
    Transaction,
    TransactionStatus,
    TransactionType,
)


def calc_periods(term_months: int, frequency: RepaymentFrequency) -> int:
    if term_months < 1:
        return 1
    return term_months if frequency == RepaymentFrequency.MONTHLY else term_months * 4


def schedule_due_date(start: datetime, *, frequency: RepaymentFrequency, step: int) -> datetime:
    if frequency == RepaymentFrequency.WEEKLY:
        return start + timedelta(days=7 * step)
    # Approximate monthly as 30 days to stay timezone/stdlib-only.
    return start + timedelta(days=30 * step)


def create_loan_internal(
    *,
    session: Session,
    group_id: int,
    borrower_account_id: int,
    principal: Decimal,
    term_months: int,
    repayment_frequency: RepaymentFrequency,
    interest_rate_percent: Decimal | None,
    description: str | None,
) -> Loan:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    settings = session.get(GroupSettings, group_id) or GroupSettings(group_id=group_id)
    borrower = session.get(Account, borrower_account_id)
    if not borrower or borrower.group_id != group_id:
        raise HTTPException(status_code=404, detail="Borrower not found in group")

    loan_rate = as_rate(interest_rate_percent if interest_rate_percent is not None else settings.loan_interest_percent)
    admin_fee_percent = as_rate(settings.admin_fee_percent)
    principal_value = money(principal)
    if principal_value <= ZERO:
        raise HTTPException(status_code=400, detail="Principal must be positive")

    if settings.enforce_loan_limit:
        contributions = net_contributions_by_account(session, group_id=group_id)
        contribution = max(money(contributions.get(borrower.id, 0)), ZERO)
        max_loan = money(contribution * Decimal(settings.loan_limit_multiplier))
        if principal_value > max_loan and max_loan > ZERO:
            raise HTTPException(status_code=400, detail=f"Loan exceeds limit (max {max_loan:.2f})")

    periods = calc_periods(term_months, repayment_frequency)
    total_interest = percent_of(principal_value, loan_rate)

    # Principal and interest are each split across the installments with the
    # same largest-remainder rule used to share interest between members, so the
    # schedule adds back to exactly what was borrowed and exactly what is owed
    # on it. The alternative — divide, round, and let the final payment absorb
    # whatever is left over — also balances, but concentrates every rounding
    # decision on one installment instead of spreading it a ngwee at a time.
    equal_weights = [(index, Decimal(1)) for index in range(1, periods + 1)]
    principal_schedule = dict(allocate(principal_value, equal_weights))
    interest_schedule = dict(allocate(total_interest, equal_weights))

    loan = Loan(
        group_id=group_id,
        borrower_account_id=borrower.id,
        principal=principal_value,
        interest_rate_percent=loan_rate,
        admin_fee_percent=admin_fee_percent,
        term_months=term_months,
        repayment_frequency=repayment_frequency,
        outstanding_principal=principal_value,
        outstanding_interest=total_interest,
        status=LoanStatus.ACTIVE,
        custom_fields={"description": description} if description else {},
        created_at=datetime.utcnow(),
        disbursed_at=datetime.utcnow(),
    )
    session.add(loan)
    # Flushed rather than committed: this assigns `loan.id` for the installments
    # below without publishing a loan that has no schedule and no disbursement.
    # A crash between the two would otherwise leave a borrower owing money the
    # group never handed them.
    session.flush()

    for idx in range(1, periods + 1):
        installment = LoanInstallment(
            loan_id=loan.id,
            sequence=idx,
            due_date=schedule_due_date(loan.disbursed_at, frequency=repayment_frequency, step=idx),
            principal_due=principal_schedule.get(idx, ZERO),
            interest_due=interest_schedule.get(idx, ZERO),
            status=InstallmentStatus.DUE,
        )
        session.add(installment)
    session.flush()

    tx = Transaction(
        account_id=borrower.id,
        amount=principal_value,
        type=TransactionType.LOAN_DISBURSEMENT,
        status=TransactionStatus.COMPLETED,
        description=description or f"Loan disbursement (loan {loan.id})",
        custom_fields={"loan_id": loan.id, "group_id": group_id},
        created_at=datetime.utcnow(),
    )
    borrower.balance = money(borrower.balance) - principal_value
    borrower.updated_at = datetime.utcnow()
    session.add(tx)
    session.add(borrower)
    # The one commit: loan, schedule, disbursement and the borrower's balance
    # all land together or not at all.
    session.commit()
    session.refresh(loan)
    return loan

