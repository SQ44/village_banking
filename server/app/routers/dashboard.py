from sqlalchemy import func
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_active_user
from ..database import get_session
from ..models import Account, Membership, Transaction, TransactionStatus
from ..performance import build_group_performance
from ..roles import is_platform_admin
from ..schemas import DashboardStats, GroupPerformance

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _is_platform_admin(role: str) -> bool:
    return is_platform_admin(role)


def _resolve_group(session: Session, *, group_id: int | None, current_user) -> int | None:
    """Which group this user may read, given the one they asked for.

    A system administrator reads any group by naming it. Everyone else — group
    administrators included — is answered only about a group they belong to, so
    naming somebody else's group id is a 403 rather than a peek at their books.
    Asking for nothing falls back to the caller's own group.
    """
    if is_platform_admin(current_user):
        return group_id

    memberships = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.is_active.is_(True),
        )
    ).all()
    if not memberships:
        raise HTTPException(status_code=404, detail="No group membership")

    allowed = {int(m.group_id) for m in memberships}
    if group_id is None:
        return int(memberships[0].group_id)
    if int(group_id) not in allowed:
        raise HTTPException(status_code=403, detail="Not a member of this group")
    return int(group_id)


@router.get("/summary", response_model=DashboardStats)
def get_summary(
    group_id: int | None = None,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> DashboardStats:
    resolved_group_id = _resolve_group(session, group_id=group_id, current_user=current_user)

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


@router.get("/performance", response_model=GroupPerformance)
def get_performance(
    group_id: int | None = None,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> GroupPerformance:
    """How one group is doing: portfolio quality, liquidity, earnings, movement.

    Computed here rather than in the browser because two of the four need data
    the client cannot reach in one request — arrears live in per-loan
    installment schedules, and cycle movement needs the group's whole
    transaction history.
    """
    resolved_group_id = _resolve_group(session, group_id=group_id, current_user=current_user)
    if resolved_group_id is None:
        raise HTTPException(status_code=400, detail="group_id is required")
    return build_group_performance(session, group_id=resolved_group_id)
