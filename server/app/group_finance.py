from __future__ import annotations

from typing import List

from sqlalchemy import func
from sqlmodel import Session, select

from .models import Account, Transaction, TransactionStatus, TransactionType


def round_allocations(amount: float, weights: List[tuple[int, float]]) -> List[tuple[int, float]]:
    total = sum(w for _, w in weights)
    if amount <= 0 or total <= 0:
        return []
    raw = [(account_id, (amount * w) / total) for account_id, w in weights]
    rounded = [(account_id, round(val, 2)) for account_id, val in raw]
    remainder = round(amount - sum(v for _, v in rounded), 2)
    if remainder != 0 and rounded:
        largest = max(range(len(weights)), key=lambda i: weights[i][1])
        account_id, current = rounded[largest]
        rounded[largest] = (account_id, round(current + remainder, 2))
    return [(aid, val) for aid, val in rounded if val > 0]


def net_contributions_by_account(session: Session, *, group_id: int) -> dict[int, float]:
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

    totals: dict[int, float] = {int(aid): 0.0 for aid in account_ids}
    for aid, total in deposits:
        totals[int(aid)] += float(total or 0)
    for aid, total in withdrawals:
        totals[int(aid)] -= float(total or 0)
    return totals

