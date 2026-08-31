"""How the group is doing, as opposed to what it currently holds.

The dashboard used to answer "what is in the pot right now". That is a balance,
not a performance: a group with K50,000 saved and half its loans in arrears
looks identical to a healthy one until somebody opens the loans page and reads
every row.

The measures here are the ordinary ones for a lending institution, chosen so an
auditor recognises them rather than having to reverse-engineer a house metric:

1.  **Portfolio at risk.** The outstanding principal of every loan carrying at
    least one installment past its due date, over the outstanding principal of
    all active loans. It is measured on balances, not on counts, because one
    large delinquent loan endangers the pool more than three small ones. Loans
    are contaminated whole: a loan with one missed installment puts its entire
    remaining balance at risk, not just the overdue part. Reported at one day
    (any arrears at all) and at thirty (the conventional benchmark).

2.  **On-time repayment.** Installments settled on or before their due date over
    all settled installments. PAR says how much is at risk today; this says
    whether the group's members have a habit of paying, which is what predicts
    tomorrow.

3.  **Utilisation.** Principal lent out over the pool. Money sitting idle earns
    the group nothing, and money lent past the constitution's cap leaves members
    unable to withdraw. Both ends are failures, so the cap is reported with it.

4.  **Cycle movement.** Deposits, withdrawals and collections inside the current
    withdrawal cycle, with the previous cycle alongside for comparison. A single
    period's figure says nothing about direction.

Ratios whose denominator is zero are returned as None rather than as zero. A
group with no loans has no portfolio at risk, and reporting that as "0.00%
at risk" would claim a clean bill of health it has not earned.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from .models import (
    Account,
    GroupFee,
    GroupSettings,
    InstallmentStatus,
    Loan,
    LoanInstallment,
    LoanRequest,
    LoanRequestStatus,
    LoanStatus,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from .money import ZERO, money, rate

# The conventional arrears benchmark. Thirty days is where the microfinance
# sector draws the line between "late" and "a problem".
PAR_BENCHMARK_DAYS = 30


def _percent(part: Decimal, whole: Decimal) -> Optional[Decimal]:
    """Part over whole as a percentage, or None when there is nothing to divide.

    A ratio with no denominator is not zero, it is unknown, and the difference
    matters: 0% at risk reads as a clean portfolio rather than as no portfolio.
    """
    if whole <= ZERO:
        return None
    return rate(part / whole * Decimal(100))


def _sum(session: Session, statement) -> Decimal:
    return money(session.exec(statement).one() or 0)


def _group_account_ids(group_id: int):
    return select(Account.id).where(Account.group_id == group_id)


def _movement(
    session: Session,
    *,
    group_id: int,
    types: Iterable[TransactionType],
    start: datetime,
    end: datetime,
) -> Decimal:
    """Completed money of the given kinds that moved inside a window.

    Pending and failed transactions are excluded: money a member has been
    prompted for but has not approved has not moved, and counting it would let
    an abandoned payment inflate the group's growth.
    """
    return _sum(
        session,
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id.in_(_group_account_ids(group_id)),
            Transaction.type.in_(list(types)),
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= start,
            Transaction.created_at < end,
        ),
    )


def portfolio_at_risk(session: Session, *, group_id: int, now: datetime, days: int = 0) -> tuple[Decimal, int]:
    """Outstanding principal on active loans with an installment `days` overdue.

    Returns the at-risk balance and how many loans make it up.
    """
    cutoff = now - timedelta(days=days)
    overdue_loan_ids = select(LoanInstallment.loan_id).where(
        LoanInstallment.status == InstallmentStatus.DUE,
        LoanInstallment.due_date < cutoff,
    )
    rows = session.exec(
        select(Loan.outstanding_principal).where(
            Loan.group_id == group_id,
            Loan.status == LoanStatus.ACTIVE,
            Loan.id.in_(overdue_loan_ids),
        )
    ).all()
    return money(sum((money(value) for value in rows), ZERO)), len(rows)


def build_group_performance(session: Session, *, group_id: int, now: Optional[datetime] = None):
    """Every figure the overview needs, in one pass over the group's data."""
    from .schemas import (
        CyclePerformance,
        EarningsPerformance,
        GroupPerformance,
        LiquidityPerformance,
        PortfolioPerformance,
    )

    now = now or datetime.utcnow()
    settings = session.get(GroupSettings, group_id)
    cycle_days = max(1, int(getattr(settings, "withdrawal_cycle_days", 30) or 30))
    cap_percent = rate(getattr(settings, "liquidity_max_outstanding_percent", 80) or 0)

    cycle_start = now - timedelta(days=cycle_days)
    previous_start = cycle_start - timedelta(days=cycle_days)

    # --- The pool -------------------------------------------------------
    member_count = int(
        session.exec(select(func.count(Account.id)).where(Account.group_id == group_id)).one() or 0
    )
    pool = _sum(
        session,
        select(func.coalesce(func.sum(Account.balance), 0)).where(Account.group_id == group_id),
    )

    # --- Portfolio ------------------------------------------------------
    active_loans = session.exec(
        select(Loan).where(Loan.group_id == group_id, Loan.status == LoanStatus.ACTIVE)
    ).all()
    outstanding_principal = money(sum((money(loan.outstanding_principal) for loan in active_loans), ZERO))
    outstanding_interest = money(sum((money(loan.outstanding_interest) for loan in active_loans), ZERO))
    closed_loans = int(
        session.exec(
            select(func.count(Loan.id)).where(Loan.group_id == group_id, Loan.status == LoanStatus.CLOSED)
        ).one()
        or 0
    )

    at_risk, at_risk_count = portfolio_at_risk(session, group_id=group_id, now=now, days=0)
    at_risk_benchmark, _ = portfolio_at_risk(session, group_id=group_id, now=now, days=PAR_BENCHMARK_DAYS)

    # Arrears: the overdue money itself, as distinct from the contaminated
    # balances above. Both are worth knowing — one is what is late, the other is
    # what that lateness endangers.
    loan_ids = select(Loan.id).where(Loan.group_id == group_id)
    overdue_rows = session.exec(
        select(LoanInstallment.principal_due, LoanInstallment.interest_due).where(
            LoanInstallment.loan_id.in_(loan_ids),
            LoanInstallment.status == InstallmentStatus.DUE,
            LoanInstallment.due_date < now,
        )
    ).all()
    arrears = money(
        sum((money(principal) + money(interest) for principal, interest in overdue_rows), ZERO)
    )

    settled = session.exec(
        select(LoanInstallment.due_date, LoanInstallment.paid_at).where(
            LoanInstallment.loan_id.in_(loan_ids),
            LoanInstallment.status == InstallmentStatus.PAID,
        )
    ).all()
    settled_count = len(settled)
    # A settled installment with no recorded payment date cannot be shown to
    # have been late, so it counts as on time rather than against the members.
    on_time_count = sum(1 for due_date, paid_at in settled if paid_at is None or paid_at <= due_date)

    # --- Earnings -------------------------------------------------------
    interest_earned = _sum(
        session,
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id.in_(_group_account_ids(group_id)),
            Transaction.type == TransactionType.INTEREST,
            Transaction.status == TransactionStatus.COMPLETED,
        ),
    )
    admin_fees = _sum(
        session,
        select(func.coalesce(func.sum(GroupFee.amount), 0)).where(GroupFee.group_id == group_id),
    )

    # --- Cycle movement -------------------------------------------------
    deposits = _movement(
        session, group_id=group_id, types=[TransactionType.DEPOSIT], start=cycle_start, end=now
    )
    withdrawals = _movement(
        session, group_id=group_id, types=[TransactionType.WITHDRAWAL], start=cycle_start, end=now
    )
    repayments = _movement(
        session, group_id=group_id, types=[TransactionType.LOAN_REPAYMENT], start=cycle_start, end=now
    )
    disbursed = _movement(
        session, group_id=group_id, types=[TransactionType.LOAN_DISBURSEMENT], start=cycle_start, end=now
    )
    previous_deposits = _movement(
        session, group_id=group_id, types=[TransactionType.DEPOSIT], start=previous_start, end=cycle_start
    )
    previous_withdrawals = _movement(
        session,
        group_id=group_id,
        types=[TransactionType.WITHDRAWAL],
        start=previous_start,
        end=cycle_start,
    )

    contributing_members = int(
        session.exec(
            select(func.count(func.distinct(Transaction.account_id))).where(
                Transaction.account_id.in_(_group_account_ids(group_id)),
                Transaction.type == TransactionType.DEPOSIT,
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.created_at >= cycle_start,
            )
        ).one()
        or 0
    )

    open_requests = session.exec(
        select(LoanRequest.principal).where(
            LoanRequest.group_id == group_id,
            LoanRequest.status.in_([LoanRequestStatus.REQUESTED, LoanRequestStatus.QUEUED]),
        )
    ).all()

    cap_amount = money(pool * cap_percent / Decimal(100))
    available_to_lend = money(max(ZERO, cap_amount - outstanding_principal))

    return GroupPerformance(
        group_id=group_id,
        generated_at=now,
        portfolio=PortfolioPerformance(
            outstanding_principal=outstanding_principal,
            outstanding_interest=outstanding_interest,
            active_loans=len(active_loans),
            closed_loans=closed_loans,
            at_risk_amount=at_risk,
            at_risk_loans=at_risk_count,
            par_percent=_percent(at_risk, outstanding_principal),
            par_benchmark_percent=_percent(at_risk_benchmark, outstanding_principal),
            par_benchmark_days=PAR_BENCHMARK_DAYS,
            arrears_amount=arrears,
            settled_installments=settled_count,
            on_time_installments=on_time_count,
            on_time_percent=_percent(Decimal(on_time_count), Decimal(settled_count)),
        ),
        liquidity=LiquidityPerformance(
            pool=pool,
            lent_out=outstanding_principal,
            idle=money(max(ZERO, pool - outstanding_principal)),
            cap_percent=cap_percent,
            cap_amount=cap_amount,
            available_to_lend=available_to_lend,
            utilization_percent=_percent(outstanding_principal, pool),
            cap_used_percent=_percent(outstanding_principal, cap_amount),
        ),
        earnings=EarningsPerformance(
            interest_earned=interest_earned,
            admin_fees=admin_fees,
            interest_accruing=outstanding_interest,
            return_on_pool_percent=_percent(interest_earned, pool),
        ),
        cycle=CyclePerformance(
            cycle_days=cycle_days,
            cycle_start=cycle_start,
            deposits=deposits,
            withdrawals=withdrawals,
            net_savings=money(deposits - withdrawals),
            previous_net_savings=money(previous_deposits - previous_withdrawals),
            repayments_collected=repayments,
            disbursed=disbursed,
            member_count=member_count,
            contributing_members=contributing_members,
            participation_percent=_percent(Decimal(contributing_members), Decimal(member_count)),
            open_requests=len(open_requests),
            open_request_amount=money(sum((money(value) for value in open_requests), ZERO)),
        ),
    )
