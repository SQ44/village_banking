"""Recording the money movements that no transaction explains.

Almost every balance change in this app is the consequence of a transaction,
and the transaction is its own explanation. Two paths are not: an operator
overriding a payment's status, and an operator editing a balance directly.
Those are exactly the actions a village banking group adopts software to stop
happening unobserved, so each one writes a row here naming who did it and why.

`record` deliberately does not commit. The entry is added to the caller's
session so it lands in the same database transaction as the change it
describes — either both are written or neither is, and there is no window in
which the balance moved without the note saying who moved it.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlmodel import Session, select

from .models import AuditLog, User

# Actions recorded so far. Kept as constants so the operations endpoint and the
# tests refer to the same strings the writers use.
TRANSACTION_STATUS_CHANGED = "transaction.status_changed"
ACCOUNT_BALANCE_CHANGED = "account.balance_changed"


def record(
    session: Session,
    *,
    actor: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Any,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> AuditLog:
    """Add an audit entry to the caller's session. The caller commits."""
    entry = AuditLog(
        actor_user_id=getattr(actor, "id", None),
        actor_email=getattr(actor, "email", None),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        reason=reason,
        before=before or {},
        after=after or {},
    )
    session.add(entry)
    return entry


def recent(session: Session, *, limit: int = 100, entity_type: Optional[str] = None) -> list[AuditLog]:
    """Newest entries first — what an admin sees on the audit page."""
    statement = select(AuditLog)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    statement = statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
    return list(session.exec(statement).all())
