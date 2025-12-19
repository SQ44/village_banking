from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from sqlalchemy import func

from ..auth import get_current_active_user
from ..database import get_session
from ..group_finance import net_contributions_by_account
from ..models import (
    Account,
    Group,
    GroupSettings,
    InterestAccrual,
    Loan,
    LoanStatus,
    Membership,
    SavingsProduct,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
)
from ..schemas import (
    AccountRead,
    GroupSettingsRead,
    GroupWithSettings,
    GroupRead,
    MeContext,
    MemberForecast,
    MemberLoanForecast,
    MemberSummary,
    MembershipRead,
    TransactionRead,
)

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

    now = datetime.utcnow()
    next_withdrawal_at = None
    days_until_withdrawal = None
    next_interest_accrual_at = None
    days_until_interest_accrual = None

    if membership.group_id:
        settings = session.get(GroupSettings, membership.group_id)
        if settings and settings.withdrawal_cycle_days and settings.withdrawal_cycle_days > 0:
            if account.last_withdrawal_at:
                next_withdrawal_at = account.last_withdrawal_at + timedelta(days=int(settings.withdrawal_cycle_days))
                days_until_withdrawal = max((next_withdrawal_at - now).days, 0)
            else:
                next_withdrawal_at = now
                days_until_withdrawal = 0

    product: SavingsProduct | None = None
    if account.product_id:
        product = session.get(SavingsProduct, account.product_id)
    elif getattr(account, "product", None) is not None:
        product = account.product
    if product and product.compounding_days and product.compounding_days > 0:
        last_end = session.exec(
            select(func.max(InterestAccrual.period_end)).where(InterestAccrual.account_id == account.id)
        ).one()
        base = last_end or account.created_at
        candidate = base + timedelta(days=int(product.compounding_days))
        next_interest_accrual_at = candidate if candidate > now else now
        days_until_interest_accrual = max((next_interest_accrual_at - now).days, 0)

    return MemberSummary(
        group_id=membership.group_id,
        account=AccountRead(**account.model_dump()),
        savings_balance=float(account.balance),
        interest_earned=round(interest_total, 2),
        loan_outstanding=round(outstanding, 2),
        active_loan_count=len(active_loans),
        next_withdrawal_at=next_withdrawal_at,
        days_until_withdrawal=days_until_withdrawal,
        next_interest_accrual_at=next_interest_accrual_at,
        days_until_interest_accrual=days_until_interest_accrual,
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


@router.get("/forecast", response_model=MemberForecast)
def my_forecast(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> MemberForecast:
    membership = _get_primary_membership(session, current_user.id)
    if not membership or not membership.account_id:
        return MemberForecast(group_id=None, my_net_contribution=0, group_total_contributions=0, my_share_percent=0, loans=[])

    account = session.get(Account, membership.account_id)
    if not account or not membership.group_id:
        return MemberForecast(group_id=None, my_net_contribution=0, group_total_contributions=0, my_share_percent=0, loans=[])

    if membership.accepted_terms_at is None and current_user.role not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Accept group terms first")

    contributions = net_contributions_by_account(session, group_id=membership.group_id)
    weights = {account_id: max(float(contributed), 0.0) for account_id, contributed in contributions.items()}
    total = float(sum(weights.values()))
    my_weight = float(weights.get(int(account.id), 0.0))
    my_share_percent = round((my_weight / total) * 100.0, 2) if total > 0 else 0.0

    borrower_rows = session.exec(select(Account.id, Account.name).where(Account.group_id == membership.group_id)).all()
    borrower_names = {int(aid): name for aid, name in borrower_rows}

    active_loans = session.exec(
        select(Loan).where(Loan.group_id == membership.group_id, Loan.status == LoanStatus.ACTIVE).order_by(Loan.created_at.desc())
    ).all()

    loans: list[MemberLoanForecast] = []
    for loan in active_loans:
        outstanding_interest = float(loan.outstanding_interest)
        admin_fee_percent = float(loan.admin_fee_percent)
        distributable = round(outstanding_interest * (1.0 - (admin_fee_percent / 100.0)), 2)
        expected = round((distributable * my_weight / total), 2) if total > 0 else 0.0
        loans.append(
            MemberLoanForecast(
                loan_id=loan.id,
                borrower_name=borrower_names.get(int(loan.borrower_account_id), f"Account {loan.borrower_account_id}"),
                outstanding_interest=round(outstanding_interest, 2),
                admin_fee_percent=admin_fee_percent,
                distributable_interest=distributable,
                my_share_percent=my_share_percent,
                my_expected_interest=expected,
            )
        )

    return MemberForecast(
        group_id=membership.group_id,
        my_net_contribution=round(float(contributions.get(int(account.id), 0.0)), 2),
        group_total_contributions=round(total, 2),
        my_share_percent=my_share_percent,
        loans=loans,
    )
