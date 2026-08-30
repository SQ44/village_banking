from __future__ import annotations

from decimal import Decimal
from typing import List

from sqlalchemy import func
from sqlmodel import Session, select

from .models import Account, Transaction, TransactionStatus, TransactionType
from .money import ZERO, allocate, money


def round_allocations(amount: Decimal, weights: List[tuple[int, Decimal]]) -> List[tuple[int, Decimal]]:
    """Split a sum between members, preserving it exactly.

    Delegates to `money.allocate`, which uses the largest-remainder method: the
    parts always add back to the whole, and the same inputs always produce the
    same split.

    The previous version rounded each share independently and then patched the
    difference onto whoever had the largest contribution — which preserved the
    total, but handed the odd ngwee to the richest member every single time.
    Largest remainder gives it to whoever the rounding shortchanged most, which
    is both the standard rule and the one that can be defended in a meeting.
    """
    return allocate(money(amount), [(account_id, Decimal(weight)) for account_id, weight in weights])


def net_contributions_by_account(session: Session, *, group_id: int) -> dict[int, Decimal]:
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

    totals: dict[int, Decimal] = {int(aid): ZERO for aid in account_ids}
    for aid, total in deposits:
        totals[int(aid)] += money(total or 0)
    for aid, total in withdrawals:
        totals[int(aid)] -= money(total or 0)
    return totals

