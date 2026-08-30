"""Make a money-moving request safe to send twice.

A member on a weak network taps "Pay" and the reply never arrives. Their phone
cannot tell a lost response from a lost request, so it sends the same thing
again. Without something here, the second send starts a second collection: two
prompts on the handset, two debits against the same K300.

The client sends an `Idempotency-Key` header — one value per user intent, kept
across retries of that intent. The first request to arrive with a given key
claims it and records what it answered; any later request carrying the same key
is handed that stored answer instead of doing the work again.

Usage in an endpoint::

    claim = idempotency.claim(session, key=..., endpoint=..., user_id=..., payload=...)
    if claim.replay is not None:
        return TransactionRead(**claim.replay)          # a retry — answer as before
    try:
        ...                                             # do the real work
    except Exception:
        idempotency.release(session, claim)             # let a genuine retry through
        raise
    idempotency.store(session, claim, response)
    return response

Sending no key is allowed and simply skips the protection, so an older client
keeps working. Every money-moving call in this app's own client sends one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .models import IdempotencyRecord

IDEMPOTENCY_HEADER = "Idempotency-Key"

# Long enough to be unguessable, short enough to index. A UUID fits comfortably.
MAX_KEY_LENGTH = 200


@dataclass
class Claim:
    """The outcome of trying to claim a key for this request.

    Exactly one of the two is meaningful: `replay` holds the earlier response
    when this request is a repeat, and `record` holds the row to write the
    response into when it is the first attempt. Both are None when the caller
    sent no key, which means "proceed without protection".
    """

    record: Optional[IdempotencyRecord] = None
    replay: Optional[dict[str, Any]] = None


def fingerprint(payload: Any) -> str:
    """A stable hash of a request body.

    Sorted keys so that a client reordering its JSON is still recognised as the
    same request, and `default=str` so a date or Decimal in the payload hashes
    rather than raising.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scope(endpoint: str, user_id: Optional[int], key: str) -> str:
    return f"{endpoint}|{user_id if user_id is not None else '-'}|{key}"


def claim(
    session: Session,
    *,
    key: Optional[str],
    endpoint: str,
    user_id: Optional[int],
    payload: Any,
) -> Claim:
    """Claim `key` for this request, or recognise the request as a repeat.

    Raises 409 when an identical request is still in flight — the honest answer
    to "I am already doing that", and better than either duplicating the work or
    pretending it is finished.

    Raises 422 when the key has been used for a *different* body. That is a
    client bug, and answering it with the first request's response would be
    worse than refusing.
    """
    if not key:
        return Claim()

    key = key.strip()
    if not key or len(key) > MAX_KEY_LENGTH:
        raise HTTPException(status_code=400, detail="invalid_idempotency_key")

    scope = _scope(endpoint, user_id, key)
    digest = fingerprint(payload)

    existing = session.exec(
        select(IdempotencyRecord).where(IdempotencyRecord.scope == scope)
    ).first()

    if existing is None:
        record = IdempotencyRecord(
            scope=scope,
            endpoint=endpoint,
            user_id=user_id,
            request_fingerprint=digest,
            state="in_progress",
        )
        session.add(record)
        try:
            # Commit now rather than at the end: the row is the claim, and it
            # has to be visible to a concurrent retry before the slow part
            # (calling Lipila) begins.
            session.commit()
        except IntegrityError:
            # Two retries raced and the other won the unique index. Whatever it
            # is doing, this request must not do it as well.
            session.rollback()
            raise HTTPException(status_code=409, detail="request_already_in_progress")
        session.refresh(record)
        return Claim(record=record)

    if existing.request_fingerprint != digest:
        raise HTTPException(status_code=422, detail="idempotency_key_reused_with_different_body")

    if existing.state != "completed":
        raise HTTPException(status_code=409, detail="request_already_in_progress")

    return Claim(replay=dict(existing.response_body or {}))


def store(session: Session, claim_result: Claim, response: Any, *, status_code: int = 200) -> None:
    """Remember what this request answered, so a retry can be answered the same."""
    record = claim_result.record
    if record is None:
        return

    if hasattr(response, "model_dump"):
        # mode="json" so datetimes and enums land as the strings the retry will
        # be handed back, not as Python objects the JSON column cannot store.
        body = response.model_dump(mode="json")
    elif isinstance(response, dict):
        body = response
    else:
        body = {"result": response}

    record.state = "completed"
    record.response_status = status_code
    record.response_body = body
    record.completed_at = datetime.utcnow()
    session.add(record)
    session.commit()


def release(session: Session, claim_result: Claim) -> None:
    """Give the key back after a failed attempt.

    A request that raised did not move money, so the key should not be burned:
    the member fixes the typo, the client retries with the same key, and it has
    to be allowed through. Left claimed, they would get 409 forever.
    """
    record = claim_result.record
    if record is None:
        return
    try:
        session.delete(record)
        session.commit()
    except Exception:  # pragma: no cover - releasing must never mask the real error
        session.rollback()
