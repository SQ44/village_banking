from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_active_user
from ..database import get_session
from ..models import Account, Group, GroupSettings, Loan, LoanStatus, Membership, Transaction, TransactionStatus, TransactionType, User
from ..schemas import AccountRead, GroupSettingsRead, GroupWithSettings, GroupRead, MeContext, MemberSummary, MembershipRead, TransactionRead

router = APIRouter(prefix="/me", tags=["Me"])


def _get_primary_membership(session: Session, user_id: int) -> Membership | None:
    statement = select(Membership).where(Membership.user_id == user_id, Membership.is_active.is_(True)).order_by(
        Membership.joined_at.desc()
    )
    return session.exec(statement).first()


@router.get("/context", response_model=MeContext)
def my_context(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> MeContext:
    membership = _get_primary_membership(session, current_user.id)
    if not membership:
        return MeContext()
    group = session.get(Group, membership.group_id)
    settings = session.get(GroupSettings, membership.group_id)
    group_with_settings = None
    if group and settings:
        group_with_settings = GroupWithSettings(
            **GroupRead(**group.model_dump()).model_dump(),
            settings=GroupSettingsRead(**settings.model_dump()),
        )
    return MeContext(
        membership=MembershipRead(**membership.model_dump()),
        group=group_with_settings,
    )


@router.get("/summary", response_model=MemberSummary)
def my_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> MemberSummary:
    membership = _get_primary_membership(session, current_user.id)
    if not membership or not membership.account_id:
        return MemberSummary()
    account = session.get(Account, membership.account_id)
    if not account:
        return MemberSummary()

    interest_earned = session.exec(
        select(Transaction).where(
            Transaction.account_id == account.id,
            Transaction.type == TransactionType.INTEREST,
            Transaction.status == TransactionStatus.COMPLETED,
        )
    ).all()
    interest_total = sum(float(tx.amount) for tx in interest_earned)

    active_loans = session.exec(
        select(Loan).where(Loan.borrower_account_id == account.id, Loan.status == LoanStatus.ACTIVE)
    ).all()
    outstanding = sum(float(loan.outstanding_principal) + float(loan.outstanding_interest) for loan in active_loans)

    return MemberSummary(
        group_id=membership.group_id,
        account=AccountRead(**account.model_dump()),
        savings_balance=float(account.balance),
        interest_earned=round(interest_total, 2),
        loan_outstanding=round(outstanding, 2),
        active_loan_count=len(active_loans),
    )


@router.get("/transactions", response_model=list[TransactionRead])
def my_transactions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> list[Transaction]:
    membership = _get_primary_membership(session, current_user.id)
    if not membership or not membership.account_id:
        raise HTTPException(status_code=404, detail="No linked member account")
    statement = (
        select(Transaction)
        .where(Transaction.account_id == membership.account_id)
        .order_by(Transaction.created_at.desc())
    )
    return session.exec(statement).all()
