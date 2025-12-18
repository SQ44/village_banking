from sqlalchemy import func
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_active_user
from ..database import get_session
from ..models import Account, Membership, Transaction, TransactionStatus
from ..schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

def _is_platform_admin(role: str) -> bool:
    return role in {"admin", "operator"}


@router.get("/summary", response_model=DashboardStats)
def get_summary(
    group_id: int | None = None,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> DashboardStats:
    role = getattr(current_user, "role", "")
    is_admin = _is_platform_admin(role)
    resolved_group_id = group_id
    if not is_admin:
        membership = session.exec(select(Membership).where(Membership.user_id == current_user.id)).first()
        if not membership:
            raise HTTPException(status_code=404, detail="No group membership")
        resolved_group_id = membership.group_id

    account_filter = True
    tx_filter = True
    if resolved_group_id:
        account_filter = Account.group_id == resolved_group_id
        tx_filter = Transaction.account_id.in_(select(Account.id).where(Account.group_id == resolved_group_id))

    member_count = session.exec(select(func.count(Account.id)).where(account_filter)).one()
    total_balance = session.exec(select(func.coalesce(func.sum(Account.balance), 0)).where(account_filter)).one()
    pending_transactions = session.exec(select(func.count(Transaction.id)).where(tx_filter, Transaction.status == TransactionStatus.PENDING)).one()
    return DashboardStats(
        member_count=member_count,
        total_balance=total_balance,
        pending_transactions=pending_transactions,
    )
