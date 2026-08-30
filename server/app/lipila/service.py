"""Orchestration between the ledger and Lipila.

A collection is started once the transaction row exists, so the reference sent
to Lipila always has something to come back to. The provider's answer — whether
it arrives on the response, on a webhook, or on a status poll — funnels through
`apply_provider_status`, which is the only thing allowed to settle a payment.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlmodel import Session, select

from ..config import Settings
from ..ledger import InsufficientFunds, apply_status_change
from ..models import (
    Account,
    PaymentChannel,
    ProviderEvent,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from .client import LipilaClient, LipilaError
from .status import can_transition_payment_status, map_lipila_status, to_ledger_status

PROVIDER_NAME = "lipila"

# Money in versus money out. Lipila is asked to collect for the first set and to
# pay out for the second.
COLLECTION_TYPES = {TransactionType.DEPOSIT, TransactionType.LOAN_REPAYMENT}
PAYOUT_TYPES = {TransactionType.WITHDRAWAL, TransactionType.LOAN_DISBURSEMENT}

# E.164 caps a subscriber number at 15 digits. Nothing dialable is shorter than
# eight once a country code is included, so anything below that is a typo.
_MIN_E164_DIGITS = 8
_MAX_E164_DIGITS = 15


class LipilaNotConfigured(RuntimeError):
    pass


class PayoutsDisabled(RuntimeError):
    pass


def normalize_zambian_phone(value: Optional[str]) -> str:
    if not value:
        raise ValueError("phone_number_required")
    digits = "".join(char for char in value if char.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        digits = "260" + digits[1:]
    elif digits.startswith("9") and len(digits) == 9:
        digits = "260" + digits
    elif digits.startswith("260") and len(digits) == 12:
        pass
    else:
        raise ValueError("invalid_zambian_phone_number")
    if len(digits) != 12:
        raise ValueError("invalid_zambian_phone_number")
    return digits


def normalize_international_phone(value: Optional[str]) -> str:
    """Normalise a number that need not belong to a Zambian network.

    A card is not tied to a Zambian mobile wallet, so the Zambian check that
    mobile money genuinely needs would turn away a member paying in from abroad
    whose only number is British, American or South African. The number still
    has to be a plausible E.164 subscriber number, because the processor rejects
    the collection outright otherwise.

    A number with no country code is still read as Zambian: that is what a
    member standing in Lusaka types, and guessing any other country would be
    worse.
    """
    if not value:
        raise ValueError("phone_number_required")
    trimmed = value.strip()
    digits = "".join(char for char in trimmed if char.isdigit())
    if trimmed.startswith("+"):
        pass  # Already carries its own country code.
    elif digits.startswith("00"):
        digits = digits[2:]  # 00 is the international access code, not the country.
    elif digits.startswith("0") and len(digits) == 10:
        digits = "260" + digits[1:]  # Local Zambian, written with the trunk 0.
    elif digits.startswith("9") and len(digits) == 9:
        digits = "260" + digits  # Local Zambian, written without it.
    if not _MIN_E164_DIGITS <= len(digits) <= _MAX_E164_DIGITS:
        raise ValueError("invalid_phone_number")
    return digits


def normalize_phone_for_channel(channel: PaymentChannel, value: Optional[str]) -> str:
    """Mobile money must reach a Zambian wallet; a card need not."""
    if channel == PaymentChannel.CARD:
        return normalize_international_phone(value)
    return normalize_zambian_phone(value)


def network_for_phone(account_number: str) -> str:
    if account_number.startswith("26095") or account_number.startswith("26075"):
        return "zamtel"
    if account_number.startswith("26096") or account_number.startswith("26076"):
        return "mtn"
    return "airtel"


def new_reference() -> str:
    return f"VB-{secrets.token_hex(8).upper()}"


def default_narration(transaction: Transaction, account: Account) -> str:
    labels = {
        TransactionType.DEPOSIT: "Village Banking contribution",
        TransactionType.LOAN_REPAYMENT: "Village Banking loan repayment",
        TransactionType.WITHDRAWAL: "Village Banking withdrawal",
        TransactionType.LOAN_DISBURSEMENT: "Village Banking loan disbursement",
    }
    label = labels.get(transaction.type, "Village Banking transaction")
    return f"{label} for {account.name}"[:100]


def _callback_url(settings: Settings) -> str:
    return f"{settings.lipila_callback_base_url.rstrip('/')}/webhooks/lipila"


async def start_collection(
    *,
    settings: Settings,
    transaction: Transaction,
    account: Account,
    channel: PaymentChannel,
    account_number: str,
    email: Optional[str],
    currency: str,
    reference_data: str,
) -> tuple[str, dict[str, Any]]:
    """Ask Lipila to collect. Returns the mapped provider status and its payload."""
    if not settings.lipila_configured:
        raise LipilaNotConfigured("lipila_api_key is not configured")

    client = LipilaClient(settings)
    amount_major = Decimal(str(transaction.amount)).quantize(Decimal("0.01"))
    narration = transaction.description or default_narration(transaction, account)

    try:
        if channel == PaymentChannel.CARD:
            payload = await client.create_card_collection(
                reference_id=transaction.provider_reference,
                amount_major=amount_major,
                account_number=account_number,
                currency=currency,
                email=email,
                member_name=account.name,
                narration=narration,
                reference_data=reference_data,
                back_url=settings.lipila_card_return_url,
            )
        else:
            payload = await client.create_mobile_money_collection(
                reference_id=transaction.provider_reference,
                amount_major=amount_major,
                account_number=account_number,
                currency=currency,
                email=email,
                narration=narration,
                reference_data=reference_data,
                callback_url=_callback_url(settings),
            )
        return map_lipila_status(find_provider_status(payload)), payload
    except LipilaError as exc:
        return _status_from_error(exc), exc.payload or {"error": str(exc), "status_code": exc.status_code}


async def start_payout(
    *,
    settings: Settings,
    transaction: Transaction,
    account: Account,
    channel: PaymentChannel,
    account_number: str,
    currency: str,
    reference_data: str,
    bank_code: Optional[str] = None,
    account_name: Optional[str] = None,
) -> tuple[str, dict[str, Any]]:
    """Ask Lipila to pay a member out.

    Guarded by `lipila_disbursements_enabled` because the payout endpoints have
    not been exercised against Lipila — see the note on the client.
    """
    if not settings.lipila_configured:
        raise LipilaNotConfigured("lipila_api_key is not configured")
    if not settings.lipila_disbursements_enabled:
        raise PayoutsDisabled("lipila payouts are disabled")

    client = LipilaClient(settings)
    amount_major = Decimal(str(transaction.amount)).quantize(Decimal("0.01"))
    narration = transaction.description or default_narration(transaction, account)

    try:
        if channel == PaymentChannel.BANK:
            payload = await client.create_bank_payout(
                reference_id=transaction.provider_reference,
                amount_major=amount_major,
                account_number=account_number,
                bank_code=bank_code or "",
                account_name=account_name or account.name,
                currency=currency,
                narration=narration,
                reference_data=reference_data,
                callback_url=_callback_url(settings),
            )
        else:
            payload = await client.create_mobile_money_payout(
                reference_id=transaction.provider_reference,
                amount_major=amount_major,
                account_number=account_number,
                currency=currency,
                narration=narration,
                reference_data=reference_data,
                callback_url=_callback_url(settings),
            )
        return map_lipila_status(find_provider_status(payload)), payload
    except LipilaError as exc:
        return _status_from_error(exc), exc.payload or {"error": str(exc), "status_code": exc.status_code}


def _status_from_error(exc: LipilaError) -> str:
    """Read a refusal apart from an outage.

    A rejected request is settled news: it failed. An auth problem is our
    misconfiguration and must not be read as the member's payment failing. A
    timeout says nothing at all, so the payment stays pending for the poller.
    """
    if exc.status_code in {400, 404, 409, 422}:
        return "failed"
    if exc.status_code in {401, 403}:
        return "needs_review"
    return "pending"


def apply_provider_status(
    session: Session,
    transaction: Transaction,
    provider_status: str,
    payload: dict[str, Any],
    *,
    source: str,
) -> str:
    """Settle a transaction against what the provider says. The only settler.

    Refuses to act on a payload whose amount or currency disagrees with the
    ledger, and on a status the current one cannot legally move to, so a
    replayed or mismatched event cannot rewrite a settled payment.
    """
    account = session.get(Account, transaction.account_id)
    if account is None:
        return "account_missing"

    current = transaction.provider_status or "created"
    identifier = find_payload_value(payload, ("identifier", "externalId", "external_id", "transactionId"))

    transaction.last_provider_sync_at = datetime.utcnow()
    transaction.custom_fields = {**(transaction.custom_fields or {}), "lipila_response": payload}

    if not _payload_matches_ledger(transaction, payload, identifier):
        provider_status = "needs_review"
    elif not can_transition_payment_status(current, provider_status):
        # Out-of-order or duplicate news. Record it, change nothing.
        if identifier and not transaction.provider_identifier:
            transaction.provider_identifier = str(identifier)
        session.add(transaction)
        session.commit()
        session.refresh(transaction)
        return "ignored_transition"

    if identifier and not transaction.provider_identifier:
        transaction.provider_identifier = str(identifier)
    transaction.provider_status = provider_status
    transaction.custom_fields = {
        **(transaction.custom_fields or {}),
        "lipila_status_source": source,
    }

    ledger_status = to_ledger_status(provider_status)
    try:
        apply_status_change(account, transaction, ledger_status)
        # An initial contribution is owed until it actually arrives, so the
        # marker is cleared here rather than when the collection was requested.
        if ledger_status == TransactionStatus.COMPLETED and transaction.type == TransactionType.DEPOSIT:
            if (account.custom_fields or {}).get("initial_contribution_due") is not None:
                remaining = dict(account.custom_fields)
                remaining.pop("initial_contribution_due", None)
                account.custom_fields = remaining
    except InsufficientFunds:
        transaction.provider_status = "needs_review"
        transaction.status = TransactionStatus.PENDING
        session.add(transaction)
        session.add(account)
        session.commit()
        session.refresh(transaction)
        return "insufficient_funds"

    session.add(transaction)
    session.add(account)
    session.commit()
    session.refresh(transaction)
    return provider_status


def _payload_matches_ledger(
    transaction: Transaction,
    payload: dict[str, Any],
    identifier: Any,
) -> bool:
    amount_present, amount_major = find_payload_amount(payload)
    if amount_present:
        if amount_major is None:
            return False
        if Decimal(str(transaction.amount)).quantize(Decimal("0.01")) != amount_major:
            return False
    currency = find_payload_value(payload, ("currency",))
    ledger_currency = str((transaction.custom_fields or {}).get("currency") or "ZMW").upper()
    if currency and str(currency).upper() != ledger_currency:
        return False
    if transaction.provider_identifier and identifier and str(identifier) != transaction.provider_identifier:
        return False
    return True


async def refresh_transaction_status(
    session: Session,
    transaction: Transaction,
    settings: Settings,
) -> str:
    """Pull the current state from Lipila for one transaction."""
    if not transaction.provider_reference:
        raise ValueError("transaction_has_no_provider_reference")
    client = LipilaClient(settings)
    try:
        if transaction.type in PAYOUT_TYPES:
            payload = await client.check_payout_status(reference_id=transaction.provider_reference)
        else:
            payload = await client.check_collection_status(reference_id=transaction.provider_reference)
        provider_status = map_lipila_status(find_provider_status(payload))
    except LipilaError as exc:
        provider_status = _status_from_error(exc)
        payload = exc.payload or {"error": str(exc), "status_code": exc.status_code}
    return apply_provider_status(session, transaction, provider_status, payload, source="status_poll")


def process_webhook(
    session: Session,
    payload: dict[str, Any],
    webhook_id: str,
    webhook_timestamp: str,
) -> str:
    """Record and apply one verified webhook. Safe to call twice."""
    existing = session.exec(select(ProviderEvent).where(ProviderEvent.webhook_id == webhook_id)).first()
    if existing:
        return "duplicate"

    reference_id = find_reference_id(payload)
    try:
        received_at = datetime.fromtimestamp(int(webhook_timestamp), tz=timezone.utc).replace(tzinfo=None)
    except (ValueError, OverflowError, OSError):
        received_at = datetime.utcnow()

    event = ProviderEvent(
        provider=PROVIDER_NAME,
        webhook_id=webhook_id,
        webhook_timestamp=received_at,
        provider_reference=reference_id,
        payload=payload,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    if not reference_id:
        event.processing_status = "dead_letter"
        event.processed_at = datetime.utcnow()
        session.add(event)
        session.commit()
        return "needs_review"

    transaction = session.exec(
        select(Transaction).where(Transaction.provider_reference == reference_id)
    ).first()
    if transaction is None:
        event.processing_status = "dead_letter"
        event.processed_at = datetime.utcnow()
        session.add(event)
        session.commit()
        return "unknown_reference"

    provider_status = map_lipila_status(find_provider_status(payload))
    outcome = apply_provider_status(session, transaction, provider_status, payload, source="webhook")

    event.processing_status = "processed" if outcome not in {"account_missing"} else "dead_letter"
    event.processed_at = datetime.utcnow()
    session.add(event)
    session.commit()
    return outcome


# ----------------------------------------------------------------------
# Payload readers. Lipila nests some responses under `data`, and names the
# same idea more than one way, so each value is looked up by every spelling
# that has been seen.
# ----------------------------------------------------------------------


def find_payload_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    nested = payload.get("data")
    if isinstance(nested, dict):
        return find_payload_value(nested, keys)
    return None


def find_provider_status(payload: dict[str, Any]) -> str:
    value = find_payload_value(payload, ("status", "transactionStatus", "transaction_status"))
    if value is None:
        value = find_payload_value(payload, ("message",))
    return str(value or "needs_review")


def find_payload_amount(payload: dict[str, Any]) -> tuple[bool, Optional[Decimal]]:
    value = find_payload_value(payload, ("amount",))
    if value is None:
        return False, None
    try:
        return True, Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return True, None


def find_reference_id(payload: dict[str, Any]) -> Optional[str]:
    for key in ("referenceId", "reference_id", "merchantReference", "externalReference"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = payload.get("data")
    if isinstance(nested, dict):
        return find_reference_id(nested)
    return None


def find_card_redirect_url(payload: Optional[dict[str, Any]]) -> Optional[str]:
    if not payload:
        return None
    value = find_payload_value(payload, ("cardRedirectionUrl", "card_redirection_url", "redirectUrl"))
    return value if isinstance(value, str) and value else None
