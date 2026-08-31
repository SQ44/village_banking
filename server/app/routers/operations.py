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

from .. import audit, journal
from ..auth import get_current_active_user
from ..database import get_session
from ..models import Account, JournalEntry, JournalLine, Loan, LoanStatus, ProviderEvent, Transaction, TransactionStatus, User
from ..reconciliation import check_all
from ..schemas import (
    AttentionReport,
    AuditEntryRead,
    BalanceDiscrepancyRead,
    JournalEntryRead,
    JournalLineRead,
    StuckEventRead,
    StuckPaymentRead,
    TrialBalanceReport,
    TrialBalanceRow,
)
from ..money import ZERO, from_minor, money

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
        books_balanced=journal.books_are_balanced(session),
        control_total_matches=journal.control_total_matches(session, group_id=group_id),
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


@router.get("/trial-balance", response_model=TrialBalanceReport)
def trial_balance(
    group_id: Optional[int] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> TrialBalanceReport:
    """Where the money is, in one screen.

    `member_savings` is what the group owes; `lipila_settlement` and
    `cash_on_hand` are what it actually holds. Those being different numbers is
    the point — the gap is fees, and it was invisible until the books had two
    sides.
    """
    _require_admin(current_user)

    balances = journal.trial_balance(session, group_id=group_id)

    loan_filter = select(Loan).where(Loan.status == LoanStatus.ACTIVE)
    if group_id is not None:
        loan_filter = loan_filter.where(Loan.group_id == group_id)
    outstanding = sum(
        (money(loan.outstanding_principal) for loan in session.exec(loan_filter).all()),
        ZERO,
    )

    return TrialBalanceReport(
        loans_outstanding=outstanding,
        accounts=[
            TrialBalanceRow(account_code=code, balance=balance)
            for code, balance in sorted(balances.items())
        ],
        balanced=journal.books_are_balanced(session),
        control_total_matches=journal.control_total_matches(session, group_id=group_id),
        generated_at=datetime.utcnow(),
    )


@router.get("/journal", response_model=List[JournalEntryRead])
def journal_entries(
    group_id: Optional[int] = None,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> List[JournalEntryRead]:
    """Recent entries, each with both sides, newest first."""
    _require_admin(current_user)
    limit = max(1, min(limit, 500))

    statement = select(JournalEntry)
    if group_id is not None:
        statement = statement.where(JournalEntry.group_id == group_id)
    entries = session.exec(
        statement.order_by(JournalEntry.created_at.desc(), JournalEntry.id.desc()).limit(limit)
    ).all()

    out: List[JournalEntryRead] = []
    for entry in entries:
        lines = session.exec(
            select(JournalLine).where(JournalLine.journal_entry_id == entry.id).order_by(JournalLine.id)
        ).all()
        out.append(
            JournalEntryRead(
                id=entry.id,
                reference_type=entry.reference_type,
                reference_id=entry.reference_id,
                group_id=entry.group_id,
                description=entry.description,
                created_at=entry.created_at,
                lines=[
                    JournalLineRead(
                        account_code=line.account_code,
                        debit=from_minor(line.debit_minor),
                        credit=from_minor(line.credit_minor),
                        account_id=line.account_id,
                    )
                    for line in lines
                ],
            )
        )
    return out
