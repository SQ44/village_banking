from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from sqlalchemy import func

from ..auth import get_current_active_user
from ..database import get_session
from ..models import (
    Account,
    Group,
    GroupFee,
    GroupSettings,
    InstallmentStatus,
    Loan,
    LoanInstallment,
    LoanStatus,
    Membership,
    MembershipRole,
    RepaymentFrequency,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
)
from ..schemas import LoanCreate, LoanInstallmentRead, LoanRead, LoanRepaymentRequest

router = APIRouter(prefix="/loans", tags=["Loans"])


def _is_platform_admin(user: User) -> bool:
    return user.role in {"admin", "operator"}


def _get_membership(session: Session, *, group_id: int, user_id: int) -> Optional[Membership]:
    statement = select(Membership).where(
        Membership.group_id == group_id,
        Membership.user_id == user_id,
        Membership.is_active.is_(True),
    )
    return session.exec(statement).first()


def _require_group_access(session: Session, *, group_id: int, user: User) -> Membership:
    membership = _get_membership(session, group_id=group_id, user_id=user.id)
    if _is_platform_admin(user) and membership:
        return membership
    if not membership:
        raise HTTPException(status_code=403, detail="Not a group member")
    return membership


def _require_terms(membership: Membership) -> None:
    if membership.accepted_terms_at is None:
        raise HTTPException(status_code=403, detail="Accept group terms first")


def _calc_periods(term_months: int, frequency: RepaymentFrequency) -> int:
    if term_months < 1:
        return 1
    return term_months if frequency == RepaymentFrequency.MONTHLY else term_months * 4


def _schedule_due_date(start: datetime, *, frequency: RepaymentFrequency, step: int) -> datetime:
    if frequency == RepaymentFrequency.WEEKLY:
        return start + timedelta(days=7 * step)
    # Approximate monthly as 30 days to stay timezone/stdlib-only.
    return start + timedelta(days=30 * step)


def _round_allocations(amount: float, weights: List[tuple[int, float]]) -> List[tuple[int, float]]:
    total = sum(w for _, w in weights)
    if amount <= 0 or total <= 0:
        return []
    raw = [(account_id, (amount * w) / total) for account_id, w in weights]
    rounded = [(account_id, round(val, 2)) for account_id, val in raw]
    remainder = round(amount - sum(v for _, v in rounded), 2)
    if remainder != 0 and rounded:
        # Add remainder to the largest weight holder to keep totals exact.
        largest = max(range(len(weights)), key=lambda i: weights[i][1])
        account_id, current = rounded[largest]
        rounded[largest] = (account_id, round(current + remainder, 2))
    return [(aid, val) for aid, val in rounded if val > 0]


def _net_contributions_by_account(session: Session, *, group_id: int) -> dict[int, float]:
    """Compute contributions as deposits minus withdrawals for each account in the group."""
    account_ids = session.exec(select(Account.id).where(Account.group_id == group_id)).all()
    if not account_ids:
        return {}

    deposits = session.exec(
        select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.account_id.in_(account_ids),
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.type == TransactionType.DEPOSIT,
        )
        .group_by(Transaction.account_id)
    ).all()
    withdrawals = session.exec(
        select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.account_id.in_(account_ids),
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.type == TransactionType.WITHDRAWAL,
        )
        .group_by(Transaction.account_id)
    ).all()

    totals: dict[int, float] = {aid: 0.0 for aid in account_ids}
    for aid, total in deposits:
        totals[int(aid)] += float(total or 0)
    for aid, total in withdrawals:
        totals[int(aid)] -= float(total or 0)
    return totals


@router.get("/group/{group_id}", response_model=List[LoanRead])
def list_group_loans(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> List[Loan]:
    membership = _require_group_access(session, group_id=group_id, user=current_user)
    if _is_platform_admin(current_user) or membership.role == MembershipRole.ADMIN:
        statement = select(Loan).where(Loan.group_id == group_id).order_by(Loan.created_at.desc())
        return session.exec(statement).all()

    if not membership.account_id:
        return []
    statement = (
        select(Loan)
        .where(Loan.group_id == group_id, Loan.borrower_account_id == membership.account_id)
        .order_by(Loan.created_at.desc())
    )
    return session.exec(statement).all()


@router.post("/group/{group_id}", response_model=LoanRead, status_code=201)
def create_loan(
    group_id: int,
    payload: LoanCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> Loan:
    membership = _require_group_access(session, group_id=group_id, user=current_user)
    if not (_is_platform_admin(current_user) or membership.role == MembershipRole.ADMIN):
        raise HTTPException(status_code=403, detail="Group admins only")

    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    settings = session.get(GroupSettings, group_id) or GroupSettings(group_id=group_id)
    borrower = session.get(Account, payload.borrower_account_id)
    if not borrower or borrower.group_id != group_id:
        raise HTTPException(status_code=404, detail="Borrower not found in group")

    rate = float(payload.interest_rate_percent if payload.interest_rate_percent is not None else settings.loan_interest_percent)
    admin_fee_percent = float(settings.admin_fee_percent)
    principal = float(payload.principal)
    if principal <= 0:
        raise HTTPException(status_code=400, detail="Principal must be positive")

    if settings.enforce_loan_limit:
        contributions = _net_contributions_by_account(session, group_id=group_id)
        contribution = max(float(contributions.get(borrower.id, 0.0)), 0.0)
        max_loan = contribution * float(settings.loan_limit_multiplier)
        if principal > max_loan and max_loan > 0:
            raise HTTPException(status_code=400, detail=f"Loan exceeds limit (max {max_loan:.2f})")

    periods = _calc_periods(payload.term_months, payload.repayment_frequency)
    total_interest = round(principal * (rate / 100.0), 2)
    principal_each = round(principal / periods, 2)
    interest_each = round(total_interest / periods, 2)
    # Fix rounding drift on last installment.
    principal_last = round(principal - principal_each * (periods - 1), 2)
    interest_last = round(total_interest - interest_each * (periods - 1), 2)

    loan = Loan(
        group_id=group_id,
        borrower_account_id=borrower.id,
        principal=principal,
        interest_rate_percent=rate,
        admin_fee_percent=admin_fee_percent,
        term_months=payload.term_months,
        repayment_frequency=payload.repayment_frequency,
        outstanding_principal=principal,
        outstanding_interest=total_interest,
        status=LoanStatus.ACTIVE,
        custom_fields={"description": payload.description} if payload.description else {},
        created_at=datetime.utcnow(),
        disbursed_at=datetime.utcnow(),
    )
    session.add(loan)
    session.commit()
    session.refresh(loan)

    for idx in range(1, periods + 1):
        installment = LoanInstallment(
            loan_id=loan.id,
            sequence=idx,
            due_date=_schedule_due_date(loan.disbursed_at, frequency=payload.repayment_frequency, step=idx),
            principal_due=principal_last if idx == periods else principal_each,
            interest_due=interest_last if idx == periods else interest_each,
            status=InstallmentStatus.DUE,
        )
        session.add(installment)
    session.commit()

    # Disbursement is recorded as a transaction for audit.
    tx = Transaction(
        account_id=borrower.id,
        amount=principal,
        type=TransactionType.LOAN_DISBURSEMENT,
        status=TransactionStatus.COMPLETED,
        description=payload.description or f"Loan disbursement (loan {loan.id})",
        custom_fields={"loan_id": loan.id, "group_id": group_id},
        created_at=datetime.utcnow(),
    )
    borrower.balance -= principal
    borrower.updated_at = datetime.utcnow()
    session.add(tx)
    session.add(borrower)
    session.commit()
    session.refresh(loan)
    return loan


@router.get("/{loan_id}/schedule", response_model=List[LoanInstallmentRead])
def get_schedule(
    loan_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> List[LoanInstallment]:
    loan = session.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    membership = _require_group_access(session, group_id=loan.group_id, user=current_user)
    if not (_is_platform_admin(current_user) or membership.role == MembershipRole.ADMIN):
        if membership.account_id != loan.borrower_account_id:
            raise HTTPException(status_code=403, detail="Not allowed")
    statement = select(LoanInstallment).where(LoanInstallment.loan_id == loan_id).order_by(LoanInstallment.sequence.asc())
    return session.exec(statement).all()


@router.post("/{loan_id}/repay", response_model=LoanRead)
def repay_loan(
    loan_id: int,
    payload: LoanRepaymentRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> Loan:
    loan = session.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    membership = _require_group_access(session, group_id=loan.group_id, user=current_user)
    _require_terms(membership)

    allowed = _is_platform_admin(current_user) or membership.role == MembershipRole.ADMIN or membership.account_id == loan.borrower_account_id
    if not allowed:
        raise HTTPException(status_code=403, detail="Not allowed")

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    amount = float(payload.amount)
    if payload.interest_component is not None or payload.principal_component is not None:
        interest_paid = float(payload.interest_component or 0)
        principal_paid = float(payload.principal_component or 0)
        if round(interest_paid + principal_paid, 2) != round(amount, 2):
            raise HTTPException(status_code=400, detail="principal_component + interest_component must equal amount")
    else:
        interest_paid = min(float(loan.outstanding_interest), amount)
        principal_paid = min(float(loan.outstanding_principal), amount - interest_paid)

    borrower = session.get(Account, loan.borrower_account_id)
    if not borrower:
        raise HTTPException(status_code=404, detail="Borrower account not found")

    description = payload.description or f"Loan repayment (loan {loan.id})"
    now = datetime.utcnow()

    if principal_paid > 0:
        tx_principal = Transaction(
            account_id=borrower.id,
            amount=principal_paid,
            type=TransactionType.LOAN_REPAYMENT,
            status=TransactionStatus.COMPLETED,
            description=description,
            custom_fields={"loan_id": loan.id, "group_id": loan.group_id, "component": "principal"},
            created_at=now,
        )
        borrower.balance += principal_paid
        session.add(tx_principal)

    if interest_paid > 0:
        tx_interest = Transaction(
            account_id=borrower.id,
            amount=interest_paid,
            type=TransactionType.FEE,
            status=TransactionStatus.COMPLETED,
            description=f"{description} (interest)",
            custom_fields={"loan_id": loan.id, "group_id": loan.group_id, "component": "interest"},
            created_at=now,
        )
        borrower.balance -= interest_paid
        session.add(tx_interest)

    loan.outstanding_interest = round(float(loan.outstanding_interest) - interest_paid, 2)
    loan.outstanding_principal = round(float(loan.outstanding_principal) - principal_paid, 2)
    if loan.outstanding_interest <= 0 and loan.outstanding_principal <= 0:
        loan.status = LoanStatus.CLOSED
        loan.closed_at = now
        loan.outstanding_interest = 0
        loan.outstanding_principal = 0

    borrower.updated_at = now
    session.add(borrower)
    session.add(loan)
    session.commit()

    # Apply installment payments (best-effort, sequential).
    remaining = round(interest_paid + principal_paid, 2)
    installments = session.exec(
        select(LoanInstallment)
        .where(LoanInstallment.loan_id == loan.id, LoanInstallment.status == InstallmentStatus.DUE)
        .order_by(LoanInstallment.sequence.asc())
    ).all()
    for inst in installments:
        if remaining <= 0:
            break
        inst_total = round(float(inst.principal_due) + float(inst.interest_due), 2)
        if remaining + 1e-9 >= inst_total:
            inst.status = InstallmentStatus.PAID
            inst.paid_at = now
            remaining = round(remaining - inst_total, 2)
            session.add(inst)
    session.commit()

    # Distribute paid interest to group members proportional to their contributions.
    if interest_paid > 0:
        admin_fee = round(interest_paid * (float(loan.admin_fee_percent) / 100.0), 2)
        distributable = round(interest_paid - admin_fee, 2)

        if admin_fee > 0:
            session.add(GroupFee(group_id=loan.group_id, amount=admin_fee, created_at=now))

        if distributable > 0:
            contributions = _net_contributions_by_account(session, group_id=loan.group_id)
            weights = [(account_id, max(amount_contributed, 0.0)) for account_id, amount_contributed in contributions.items()]
            allocations = _round_allocations(distributable, weights)
            for account_id, amount_alloc in allocations:
                tx = Transaction(
                    account_id=account_id,
                    amount=amount_alloc,
                    type=TransactionType.INTEREST,
                    status=TransactionStatus.COMPLETED,
                    description=f"Loan interest distribution (loan {loan.id})",
                    custom_fields={
                        "source": "loan_interest",
                        "loan_id": loan.id,
                        "borrower_account_id": borrower.id,
                        "admin_fee_amount": admin_fee,
                    },
                    created_at=now,
                )
                acct = session.get(Account, account_id)
                if acct:
                    acct.balance += amount_alloc
                    acct.updated_at = now
                    session.add(acct)
                session.add(tx)
        session.commit()

    session.refresh(loan)
    return loan
