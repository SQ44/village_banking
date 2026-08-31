from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_active_user
from ..database import get_session
from ..interest import apply_interest, calculate_interest
from ..models import Account, InterestAccrual, Membership, Transaction, TransactionStatus, TransactionType
from ..schemas import InterestApplyRequest, InterestPreview, TransactionRead
from ..roles import is_platform_admin

router = APIRouter(prefix="/interest", tags=["Interest"])

def _is_platform_admin(role: str) -> bool:
    return is_platform_admin(role)


def _is_member_in_group(session: Session, *, group_id: int, user_id: int) -> bool:
    return (
        session.exec(select(Membership).where(Membership.group_id == group_id, Membership.user_id == user_id))
        .first()
        is not None
    )


@router.post("/preview", response_model=InterestPreview)
def preview_interest(
    request: InterestApplyRequest,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> InterestPreview:
    account = session.get(Account, request.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if not _is_platform_admin(getattr(current_user, "role", "")) and account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    if account.group_id and not _is_platform_admin(getattr(current_user, "role", "")):
        if not _is_member_in_group(session, group_id=account.group_id, user_id=current_user.id):
            raise HTTPException(status_code=403, detail="Not a group member")
    if not account.product:
        rate = 5.0
    else:
        rate = account.product.interest_rate
    days = max((request.end - request.start).days, 1)
    projected = calculate_interest(account.balance, rate, days)
    return InterestPreview(
        account_id=account.id,
        projected_amount=projected,
        starts_on=request.start,
        ends_on=request.end,
        annual_rate=rate,
    )


@router.post("/apply", response_model=TransactionRead)
def apply_interest_route(
    request: InterestApplyRequest,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> Transaction:
    if not _is_platform_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Admins only")
    account = session.get(Account, request.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    # Admin-only tool; members can view interest but shouldn't mint it.
    if not account.product:
        rate = 5.0
    else:
        rate = account.product.interest_rate

    # `apply_interest` writes the ledger entry itself, in the same commit as the
    # accrual and the balance change. This route used to add a second one after
    # the fact, which left a window where the balance had moved and nothing
    # explained it.
    accrual, transaction = apply_interest(
        session,
        account,
        annual_rate=rate,
        period_start=request.start,
        period_end=request.end,
    )

    if transaction is None:
        # Nothing was earned over this period, so there is no movement to
        # report. Answer with a zero entry rather than inventing a ledger row.
        return Transaction(
            id=0,
            account_id=account.id,
            amount=0.0,
            type=TransactionType.INTEREST,
            status=TransactionStatus.COMPLETED,
            description=f"No interest for {request.start.date()} - {request.end.date()}",
            custom_fields={"interest_accrual_id": accrual.id},
            created_at=datetime.utcnow(),
        )
    return transaction
