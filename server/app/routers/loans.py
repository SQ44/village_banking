from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session, select
from sqlalchemy import func

from .. import idempotency, journal
from ..autonomous_lending import auto_decide_and_apply, process_queued_requests
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
    LoanRequest,
    LoanRequestStatus,
    Membership,
    MembershipRole,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
)
from ..group_finance import net_contributions_by_account, round_allocations
from ..money import ZERO, money, percent_of, rate as as_rate
from ..loan_service import create_loan_internal
from ..schemas import (
    LoanBoardItem,
    LoanCreate,
    LoanInstallmentRead,
    LoanRead,
    LoanRepaymentRequest,
    LoanRequestCreate,
    LoanRequestDecision,
    LoanRequestRead,
)

router = APIRouter(prefix="/loans", tags=["Loans"])

# Scope name for the idempotency records this router writes.
REPAY_ENDPOINT = "POST /loans/{loan_id}/repay"


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


@router.get("/group/{group_id}/board", response_model=List[LoanBoardItem])
def group_loan_board(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> List[LoanBoardItem]:
    membership = _require_group_access(session, group_id=group_id, user=current_user)
    if not _is_platform_admin(current_user):
        _require_terms(membership)

    loans = session.exec(select(Loan).where(Loan.group_id == group_id).order_by(Loan.created_at.desc())).all()
    if not loans:
        return []

    borrowers = session.exec(select(Account.id, Account.name).where(Account.group_id == group_id)).all()
    borrower_names = {int(account_id): name for account_id, name in borrowers}

    next_due = session.exec(
        select(LoanInstallment.loan_id, func.min(LoanInstallment.due_date))
        .where(LoanInstallment.loan_id.in_([loan.id for loan in loans]), LoanInstallment.status == InstallmentStatus.DUE)
        .group_by(LoanInstallment.loan_id)
    ).all()
    next_due_map = {int(loan_id): due for loan_id, due in next_due}

    items: List[LoanBoardItem] = []
    for loan in loans:
        items.append(
            LoanBoardItem(
                id=loan.id,
                group_id=loan.group_id,
                borrower_account_id=loan.borrower_account_id,
                borrower_name=borrower_names.get(int(loan.borrower_account_id), f"Account {loan.borrower_account_id}"),
                principal=loan.principal,
                interest_rate_percent=loan.interest_rate_percent,
                admin_fee_percent=loan.admin_fee_percent,
                outstanding_principal=loan.outstanding_principal,
                outstanding_interest=loan.outstanding_interest,
                status=loan.status,
                disbursed_at=loan.disbursed_at,
                next_due_date=next_due_map.get(int(loan.id)),
            )
        )
    return items


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
    return create_loan_internal(
        session=session,
        group_id=group_id,
        borrower_account_id=payload.borrower_account_id,
        principal=money(payload.principal),
        term_months=int(payload.term_months),
        repayment_frequency=payload.repayment_frequency,
        interest_rate_percent=payload.interest_rate_percent,
        description=payload.description,
    )


@router.post("/group/{group_id}/requests", response_model=LoanRequestRead, status_code=201)
def request_loan(
    group_id: int,
    payload: LoanRequestCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> LoanRequest:
    membership = _get_membership(session, group_id=group_id, user_id=current_user.id)
    if not membership or not membership.is_active:
        raise HTTPException(status_code=403, detail="Not a group member")
    _require_terms(membership)
    if not membership.account_id:
        raise HTTPException(status_code=400, detail="No linked member account")

    principal = money(payload.principal)
    if principal <= ZERO:
        raise HTTPException(status_code=400, detail="Principal must be positive")
    if int(payload.term_months or 1) < 1:
        raise HTTPException(status_code=400, detail="term_months must be >= 1")

    settings = session.get(GroupSettings, group_id) or GroupSettings(group_id=group_id)
    if settings.constitution_locked_at is None:
        raise HTTPException(status_code=400, detail="Constitution is not locked yet for this cycle")

    existing = session.exec(
        select(LoanRequest).where(
            LoanRequest.group_id == group_id,
            LoanRequest.borrower_account_id == int(membership.account_id),
            LoanRequest.status.in_([LoanRequestStatus.REQUESTED, LoanRequestStatus.QUEUED]),
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="You already have a pending loan request")

    req = LoanRequest(
        group_id=group_id,
        borrower_account_id=int(membership.account_id),
        requester_user_id=int(current_user.id),
        principal=principal,
        term_months=int(payload.term_months or 1),
        repayment_frequency=payload.repayment_frequency,
        status=LoanRequestStatus.REQUESTED,
        description=payload.description,
        created_at=datetime.utcnow(),
    )
    session.add(req)
    session.commit()
    session.refresh(req)
    req = auto_decide_and_apply(session=session, request=req, settings=settings)
    return req


@router.get("/group/{group_id}/requests", response_model=List[LoanRequestRead])
def list_loan_requests(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> List[LoanRequest]:
    membership = _get_membership(session, group_id=group_id, user_id=current_user.id)
    is_admin = _is_platform_admin(current_user) or (membership is not None and membership.role == MembershipRole.ADMIN)

    if not is_admin:
        if not membership:
            raise HTTPException(status_code=403, detail="Not a group member")
        _require_terms(membership)
        statement = (
            select(LoanRequest)
            .where(LoanRequest.group_id == group_id, LoanRequest.requester_user_id == current_user.id)
            .order_by(LoanRequest.created_at.desc())
        )
        return session.exec(statement).all()

    statement = select(LoanRequest).where(LoanRequest.group_id == group_id).order_by(LoanRequest.created_at.desc())
    return session.exec(statement).all()


@router.post("/requests/{request_id}/cancel", response_model=LoanRequestRead)
def cancel_loan_request(
    request_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> LoanRequest:
    req = session.get(LoanRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Loan request not found")
    if req.requester_user_id != current_user.id and not _is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="Not allowed")
    if req.status not in {LoanRequestStatus.REQUESTED, LoanRequestStatus.QUEUED}:
        raise HTTPException(status_code=400, detail="Only pending loan requests can be canceled")
    req.status = LoanRequestStatus.CANCELED
    req.decided_at = datetime.utcnow()
    req.decided_by_user_id = int(current_user.id)
    session.add(req)
    session.commit()
    session.refresh(req)
    return req


@router.patch("/requests/{request_id}", response_model=LoanRequestRead)
def decide_loan_request(
    request_id: int,
    payload: LoanRequestDecision,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> LoanRequest:
    raise HTTPException(status_code=400, detail="Manual loan request approvals are disabled (autonomous lending)")


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
    idempotency_key: Optional[str] = Header(default=None, alias=idempotency.IDEMPOTENCY_HEADER),
) -> Loan:
    """Record a repayment against a loan.

    Send an `Idempotency-Key`: a retry after a lost reply would otherwise book
    the repayment a second time, crediting the borrower and distributing the
    interest twice over.
    """
    claim = idempotency.claim(
        session,
        key=idempotency_key,
        endpoint=REPAY_ENDPOINT,
        user_id=current_user.id,
        payload={"loan_id": loan_id, **payload.model_dump(mode="json")},
    )
    if claim.replay is not None:
        return LoanRead(**claim.replay)

    try:
        loan = _repay_loan(loan_id, payload, session, current_user)
        result = LoanRead.model_validate(loan, from_attributes=True)
    except Exception:
        idempotency.release(session, claim)
        raise

    idempotency.store(session, claim, result)
    return loan


def _repay_loan(
    loan_id: int,
    payload: LoanRepaymentRequest,
    session: Session,
    current_user: User,
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

    amount = money(payload.amount)
    if payload.interest_component is not None or payload.principal_component is not None:
        interest_paid = money(payload.interest_component or 0)
        principal_paid = money(payload.principal_component or 0)
        # Exact equality: both sides are quantized to the ngwee, so a split that
        # does not add up is a real disagreement rather than a rounding artefact.
        if interest_paid + principal_paid != amount:
            raise HTTPException(status_code=400, detail="principal_component + interest_component must equal amount")
    else:
        # Interest first, then principal — the ordinary allocation order, and
        # the one the group's constitution assumes when it quotes a rate.
        interest_paid = min(money(loan.outstanding_interest), amount)
        principal_paid = min(money(loan.outstanding_principal), amount - interest_paid)

    borrower = session.get(Account, loan.borrower_account_id)
    if not borrower:
        raise HTTPException(status_code=404, detail="Borrower account not found")

    description = payload.description or f"Loan repayment (loan {loan.id})"
    now = datetime.utcnow()

    # Either half can be zero — a repayment covering only interest writes no
    # principal row, and vice versa.
    tx_principal: Optional[Transaction] = None
    tx_interest: Optional[Transaction] = None

    if principal_paid > ZERO:
        tx_principal = Transaction(
            account_id=borrower.id,
            amount=principal_paid,
            type=TransactionType.LOAN_REPAYMENT,
            status=TransactionStatus.COMPLETED,
            description=description,
            custom_fields={"loan_id": loan.id, "group_id": loan.group_id, "component": "principal"},
            created_at=now,
        )
        borrower.balance = money(borrower.balance) + principal_paid
        session.add(tx_principal)

    if interest_paid > ZERO:
        tx_interest = Transaction(
            account_id=borrower.id,
            amount=interest_paid,
            type=TransactionType.FEE,
            status=TransactionStatus.COMPLETED,
            description=f"{description} (interest)",
            custom_fields={"loan_id": loan.id, "group_id": loan.group_id, "component": "interest"},
            created_at=now,
        )
        borrower.balance = money(borrower.balance) - interest_paid
        session.add(tx_interest)

    loan.outstanding_interest = money(loan.outstanding_interest) - interest_paid
    loan.outstanding_principal = money(loan.outstanding_principal) - principal_paid
    # Exact zero closes the loan. With floats this had to tolerate a residue;
    # now a loan is settled when it is settled, to the ngwee.
    if loan.outstanding_interest <= ZERO and loan.outstanding_principal <= ZERO:
        loan.status = LoanStatus.CLOSED
        loan.closed_at = now
        loan.outstanding_interest = ZERO
        loan.outstanding_principal = ZERO

    borrower.updated_at = now
    session.add(borrower)
    session.add(loan)
    # Flushed, not committed. A repayment is one event: the borrower's balance,
    # the loan's outstanding amounts, the installments it settles and the
    # interest it distributes to the other members all have to land together. A
    # commit here would let a crash further down leave the loan reduced with the
    # members' share of the interest never paid.
    session.flush()

    # Book both halves. Inside the same event, so the books cannot record the
    # principal without the interest that came with it.
    for booked in (tx_principal, tx_interest):
        if booked is not None:
            journal.post_transaction(session, booked, borrower)
    session.flush()

    # Apply installment payments (best-effort, sequential).
    remaining = interest_paid + principal_paid
    installments = session.exec(
        select(LoanInstallment)
        .where(LoanInstallment.loan_id == loan.id, LoanInstallment.status == InstallmentStatus.DUE)
        .order_by(LoanInstallment.sequence.asc())
    ).all()
    for inst in installments:
        if remaining <= ZERO:
            break
        inst_total = money(inst.principal_due) + money(inst.interest_due)
        # No epsilon needed: exact amounts compare exactly.
        if remaining >= inst_total:
            inst.status = InstallmentStatus.PAID
            inst.paid_at = now
            remaining = remaining - inst_total
            session.add(inst)
    session.flush()

    # Distribute paid interest to group members proportional to their contributions.
    if interest_paid > ZERO:
        admin_fee = percent_of(interest_paid, as_rate(loan.admin_fee_percent))
        distributable = interest_paid - admin_fee

        if admin_fee > ZERO:
            session.add(GroupFee(group_id=loan.group_id, amount=admin_fee, created_at=now))

        if distributable > ZERO:
            contributions = net_contributions_by_account(session, group_id=loan.group_id)
            weights = [(account_id, max(amount_contributed, ZERO)) for account_id, amount_contributed in contributions.items()]
            allocations = round_allocations(distributable, weights)
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
                        # Stringified: a JSON column has no Decimal, and a
                        # float here would reintroduce the imprecision.
                        "admin_fee_amount": str(admin_fee),
                    },
                    created_at=now,
                )
                acct = session.get(Account, account_id)
                if acct:
                    acct.balance = money(acct.balance) + amount_alloc
                    acct.updated_at = now
                    session.add(acct)
                session.add(tx)

    # The single commit for the whole repayment. Everything above either lands
    # here together or is rolled back together.
    session.commit()

    session.refresh(loan)
    # Deliberately after the commit: releasing queued loans is a consequence of
    # the repayment, not part of it, and must not be able to roll it back.
    process_queued_requests(session, group_id=loan.group_id)
    return loan
