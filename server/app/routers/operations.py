"""What needs a human, and who has touched money by hand.

The reconciliation poller, the webhook verifier and the status mapper all know
how to give up safely — they park a payment on `needs_review`, dead-letter an
event they cannot place, and hold an ambiguous answer at pending rather than
guessing. None of that was reaching anybody: the states existed in the database
and appeared nowhere in the product, so money could sit stuck indefinitely with
no one aware it had.

These endpoints are where that surfaces, plus the audit trail of hand-made
balance changes. Admin-only, and read-only apart from the on-demand
reconciliation run.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import audit
from ..auth import get_current_active_user
from ..database import get_session
from ..models import Account, ProviderEvent, Transaction, TransactionStatus, User
from ..reconciliation import check_all
from ..schemas import (
    AttentionReport,
    AuditEntryRead,
    BalanceDiscrepancyRead,
    StuckEventRead,
    StuckPaymentRead,
)

router = APIRouter(prefix="/operations", tags=["Operations"])

# A payment younger than this is still plausibly waiting on the member to
# approve it on their handset. Past it, nobody is coming, and it belongs on
# someone's screen. Matches the reconciliation poller's own grace period times
# a margin, so an item only appears here after the poller has had several goes.
STUCK_PAYMENT_AGE = timedelta(minutes=15)


def _require_admin(user: User) -> None:
    if user.role not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Admins only")


def _stuck_payments(session: Session, *, group_id: Optional[int]) -> List[StuckPaymentRead]:
    """Payments an operator has to decide about.

    Two kinds, deliberately reported together because they need the same
    response from a human:

    * `needs_review` — the provider said something we could not map onto
      "paid" or "not paid", or the payload disagreed with our ledger. The
      balance has correctly not moved, and will not until somebody says so.
    * pending past the grace period — no webhook arrived and the poller has not
      managed to resolve it either.
    """
    cutoff = datetime.utcnow() - STUCK_PAYMENT_AGE

    statement = select(Transaction).where(
        Transaction.status == TransactionStatus.PENDING,
    )
    pending = list(session.exec(statement).all())

    accounts = {
        account.id: account
        for account in session.exec(select(Account)).all()
    }

    items: List[StuckPaymentRead] = []
    for transaction in pending:
        account = accounts.get(transaction.account_id)
        if group_id is not None and (account is None or account.group_id != group_id):
            continue

        needs_review = transaction.provider_status == "needs_review"
        overdue = transaction.created_at <= cutoff
        if not (needs_review or overdue):
            continue

        items.append(
            StuckPaymentRead(
                transaction_id=int(transaction.id),
                account_id=int(transaction.account_id),
                account_name=account.name if account else "(unknown account)",
                amount=transaction.amount,
                type=transaction.type,
                provider=transaction.provider,
                provider_status=transaction.provider_status,
                provider_reference=transaction.provider_reference,
                created_at=transaction.created_at,
                last_provider_sync_at=transaction.last_provider_sync_at,
                minutes_waiting=int((datetime.utcnow() - transaction.created_at).total_seconds() // 60),
                reason="needs_review" if needs_review else "no_confirmation",
            )
        )

    # Longest-waiting first: the member who has been in the dark longest is the
    # one to call back first.
    items.sort(key=lambda item: item.minutes_waiting, reverse=True)
    return items


def _dead_letters(session: Session) -> List[StuckEventRead]:
    """Webhooks that verified but could not be placed against a transaction.

    Each one is a message from Lipila about money that this system cannot match
    to anything it knows about — the most alarming state in the whole
    integration, and previously invisible.
    """
    events = session.exec(
        select(ProviderEvent)
        .where(ProviderEvent.processing_status == "dead_letter")
        .order_by(ProviderEvent.created_at.desc())
        .limit(100)
    ).all()
    return [
        StuckEventRead(
            event_id=int(event.id),
            provider=event.provider,
            webhook_id=event.webhook_id,
            provider_reference=event.provider_reference,
            created_at=event.created_at,
            payload=event.payload or {},
        )
        for event in events
    ]


@router.get("/attention", response_model=AttentionReport)
def attention(
    group_id: Optional[int] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> AttentionReport:
    """Everything currently needing a person, in one call."""
    _require_admin(current_user)

    report = check_all(session, group_id=group_id)
    return AttentionReport(
        stuck_payments=_stuck_payments(session, group_id=group_id),
        dead_letter_events=_dead_letters(session),
        balance_discrepancies=[
            BalanceDiscrepancyRead(
                account_id=item.account_id,
                account_name=item.account_name,
                stored_balance=item.stored_balance,
                derived_balance=item.derived_balance,
                difference=item.difference,
                transaction_count=item.transaction_count,
            )
            for item in report.discrepancies
        ],
        negative_balances=[
            BalanceDiscrepancyRead(
                account_id=item.account_id,
                account_name=item.account_name,
                stored_balance=item.stored_balance,
                derived_balance=item.derived_balance,
                difference=item.difference,
                transaction_count=item.transaction_count,
            )
            for item in report.negative_balances
        ],
        accounts_checked=report.checked,
        generated_at=datetime.utcnow(),
    )


@router.get("/audit", response_model=List[AuditEntryRead])
def audit_trail(
    limit: int = 100,
    entity_type: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> List[AuditEntryRead]:
    """Every balance change made by a person rather than by a transaction."""
    _require_admin(current_user)
    limit = max(1, min(limit, 500))
    entries = audit.recent(session, limit=limit, entity_type=entity_type)
    return [AuditEntryRead.model_validate(entry, from_attributes=True) for entry in entries]
