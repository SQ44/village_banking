"""Translation between Lipila's provider vocabulary and the ledger's own.

Lipila reports more states than the ledger records. The rich state is kept on
the transaction (`provider_status`) so an operator can tell an expiry from a
refusal, while the ledger itself stays on pending/completed/failed.
"""

from ..models import TransactionStatus

PROVIDER_STATUSES = {
    "created",
    "pending",
    "succeeded",
    "failed",
    "expired",
    "reversed",
    "refunded",
    "needs_review",
}

_ALLOWED_TRANSITIONS = {
    "created": PROVIDER_STATUSES,
    "pending": {"pending", "succeeded", "failed", "expired", "reversed", "refunded", "needs_review"},
    "succeeded": {"succeeded", "reversed", "refunded", "needs_review"},
    "failed": {"failed", "succeeded", "reversed", "refunded", "needs_review"},
    "expired": {"expired", "succeeded", "reversed", "refunded", "needs_review"},
    "reversed": {"reversed", "refunded", "needs_review"},
    "refunded": {"refunded", "needs_review"},
    "needs_review": PROVIDER_STATUSES,
}

# A settled payment that later reverses has to give the money back, so these
# are tracked separately from an outright failure.
REVERSAL_STATUSES = {"reversed", "refunded"}


def can_transition_payment_status(current_status: str, next_status: str) -> bool:
    return next_status in _ALLOWED_TRANSITIONS.get(current_status, set())


def map_lipila_status(provider_status: str | None) -> str:
    normalized = (provider_status or "").strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in {"success", "successful", "completed", "paid", "confirmed", "approved"}:
        return "succeeded"
    if normalized in {"failed", "failure", "declined", "cancelled", "canceled", "rejected"}:
        return "failed"
    if normalized in {"expired", "timeout", "timed_out"}:
        return "expired"
    if normalized in {"reversed", "chargeback", "reversal"}:
        return "reversed"
    if normalized in {"refunded", "refund"}:
        return "refunded"
    if normalized in {"pending", "processing", "initiated", "queued", "created"}:
        return "pending"
    return "needs_review"


def to_ledger_status(provider_status: str) -> TransactionStatus:
    """Collapse a provider status onto the three states the ledger records.

    `needs_review` deliberately stays PENDING: an ambiguous provider response is
    not evidence that money moved, and it is not evidence that it did not. It
    waits for an operator rather than moving a balance either way.
    """
    if provider_status == "succeeded":
        return TransactionStatus.COMPLETED
    if provider_status in {"failed", "expired"} or provider_status in REVERSAL_STATUSES:
        return TransactionStatus.FAILED
    return TransactionStatus.PENDING
