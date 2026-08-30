from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session, select

from .. import audit, idempotency
from ..auth import get_current_active_user
from ..config import get_settings
from ..database import get_session
from ..autonomous_lending import process_queued_requests
from ..ledger import InsufficientFunds, apply_balance, apply_status_change
from ..lipila import service as lipila
from ..models import (
    Account,
    GroupSettings,
    Membership,
    PaymentChannel,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from ..schemas import TransactionCreate, TransactionRead, TransactionStatusUpdate

router = APIRouter(prefix="/transactions", tags=["Transactions"])

# Names the idempotency records for this endpoint, so a key used here cannot be
# replayed against a different one.
CREATE_ENDPOINT = "POST /transactions"

def _is_platform_admin(role: str) -> bool:
    return role in {"admin", "operator"}


def _get_membership(session: Session, *, group_id: int, user_id: int) -> Membership | None:
    statement = select(Membership).where(
        Membership.group_id == group_id,
        Membership.user_id == user_id,
        Membership.is_active.is_(True),
    )
    return session.exec(statement).first()


def _read(transaction: Transaction, card_redirect_url: Optional[str] = None) -> TransactionRead:
    return TransactionRead(
        **transaction.model_dump(),
        card_redirect_url=card_redirect_url,
    )


@router.get("", response_model=List[TransactionRead])
def list_transactions(
    account_id: Optional[int] = None,
    status: Optional[TransactionStatus] = None,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> List[Transaction]:
    statement = select(Transaction)
    role = getattr(current_user, "role", "")
    is_admin = _is_platform_admin(role)
    if not is_admin:
        if not account_id:
            raise HTTPException(status_code=400, detail="account_id is required")
        account = session.get(Account, account_id)
        if not account or account.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not allowed")
    if account_id:
        statement = statement.where(Transaction.account_id == account_id)
    if status:
        statement = statement.where(Transaction.status == status)
    statement = statement.order_by(Transaction.created_at.desc())
    return session.exec(statement).all()


@router.post("", response_model=TransactionRead, status_code=201)
async def create_transaction(
    payload: TransactionCreate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
    idempotency_key: Optional[str] = Header(default=None, alias=idempotency.IDEMPOTENCY_HEADER),
) -> TransactionRead:
    """Record a transaction, optionally collecting or paying it through Lipila.

    Send an `Idempotency-Key` header. A retry carrying the same key is answered
    with the first attempt's response rather than starting a second payment.
    """
    claim = idempotency.claim(
        session,
        key=idempotency_key,
        endpoint=CREATE_ENDPOINT,
        user_id=current_user.id,
        payload=payload.model_dump(mode="json"),
    )
    if claim.replay is not None:
        return TransactionRead(**claim.replay)

    try:
        result = await _create_transaction(payload, session, current_user)
    except Exception:
        # The attempt moved no money, so the key must not stay burned — the
        # caller fixes the input and retries with the same key.
        idempotency.release(session, claim)
        raise

    idempotency.store(session, claim, result, status_code=201)
    return result


async def _create_transaction(
    payload: TransactionCreate,
    session: Session,
    current_user,
) -> TransactionRead:
    account = session.get(Account, payload.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    role = getattr(current_user, "role", "")
    is_admin = _is_platform_admin(role)
    if not is_admin and account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    if not is_admin and payload.type in {TransactionType.LOAN_DISBURSEMENT, TransactionType.LOAN_REPAYMENT, TransactionType.FEE}:
        raise HTTPException(status_code=403, detail="Use the loan workflow for borrowing/repayments")

    custom_fields = dict(payload.custom_fields or {})
    currency = str(custom_fields.get("currency") or "ZMW").upper()
    custom_fields["currency"] = currency
    if currency != "ZMW":
        raise HTTPException(status_code=400, detail="Only ZMW is supported")

    settings = get_settings()

    group_settings: GroupSettings | None = None
    if account.group_id:
        membership = _get_membership(session, group_id=account.group_id, user_id=current_user.id)
        if membership is None and not is_admin:
            raise HTTPException(status_code=403, detail="Not a group member")
        if membership and membership.accepted_terms_at is None and not is_admin:
            raise HTTPException(status_code=403, detail="Accept group terms first")
        group_settings = session.get(GroupSettings, account.group_id)

    if group_settings and not is_admin and payload.type == TransactionType.DEPOSIT:
        months = int(custom_fields.get("months_covered") or 1)
        if months < 1:
            raise HTTPException(status_code=400, detail="months_covered must be >= 1")
        minimum = float(group_settings.min_monthly_contribution) * months
        if minimum > 0 and payload.amount < minimum:
            raise HTTPException(status_code=400, detail=f"Minimum contribution is {minimum:.2f} for {months} month(s)")

    if group_settings and not is_admin and payload.type == TransactionType.WITHDRAWAL and group_settings.withdrawal_cycle_days > 0:
        if account.last_withdrawal_at:
            elapsed = (datetime.utcnow() - account.last_withdrawal_at).days
            if elapsed < group_settings.withdrawal_cycle_days:
                raise HTTPException(status_code=400, detail="Withdrawal not allowed yet for this cycle")
        account.last_withdrawal_at = datetime.utcnow()

    transaction = Transaction(
        account_id=payload.account_id,
        amount=payload.amount,
        type=payload.type,
        status=payload.status,
        description=payload.description,
        custom_fields=custom_fields,
        created_at=datetime.utcnow(),
    )

    if not payload.use_lipila:
        if transaction.status == TransactionStatus.COMPLETED:
            try:
                apply_balance(account, transaction)
            except InsufficientFunds:
                raise HTTPException(status_code=400, detail="Insufficient funds")
        account.updated_at = datetime.utcnow()
        session.add(transaction)
        session.add(account)
        session.commit()
        session.refresh(transaction)
        _run_queued_lending(session, account, transaction)
        return _read(transaction)

    return await _create_lipila_transaction(
        session=session,
        settings=settings,
        account=account,
        transaction=transaction,
        payload=payload,
        custom_fields=custom_fields,
        currency=currency,
    )


async def _create_lipila_transaction(
    *,
    session: Session,
    settings,
    account: Account,
    transaction: Transaction,
    payload: TransactionCreate,
    custom_fields: dict,
    currency: str,
) -> TransactionRead:
    """Route a transaction through Lipila.

    A collection is written pending and left alone until Lipila confirms it, so
    a balance never reflects money that was merely requested. A payout is the
    other way round: the funds are debited as the payout is requested, because
    otherwise the same balance could be withdrawn again while the first payout
    is still in flight. A payout that fails hands the money back.
    """
    if not settings.lipila_configured:
        raise HTTPException(status_code=503, detail="Lipila is not configured")

    is_collection = payload.type in lipila.COLLECTION_TYPES
    is_payout = payload.type in lipila.PAYOUT_TYPES
    if not (is_collection or is_payout):
        raise HTTPException(status_code=400, detail=f"{payload.type.value} cannot be routed through Lipila")

    # Two separate presses of the same button are two requests with two keys, so
    # the idempotency key above cannot see them as one. An identical collection
    # already waiting on the member's handset is handed back instead of putting
    # a second prompt beside it.
    if is_collection:
        live = lipila.find_live_collection(
            session,
            account_id=account.id,
            amount=payload.amount,
            transaction_type=payload.type,
        )
        if live is not None:
            return _read(live)

    channel = payload.channel
    if is_payout and channel == PaymentChannel.CARD:
        raise HTTPException(status_code=400, detail="Payouts cannot be sent to a card")
    if is_payout and not settings.lipila_disbursements_enabled:
        raise HTTPException(status_code=503, detail="Lipila payouts are disabled")

    bank_code: Optional[str] = None
    account_name: Optional[str] = None

    if channel == PaymentChannel.BANK:
        account_number = (
            custom_fields.get("account_number")
            or custom_fields.get("recipient_account_number")
            or account.custom_fields.get("bank_account")
        )
        if not account_number:
            raise HTTPException(status_code=400, detail="account_number is required for a bank payout")
        bank_code = custom_fields.get("bank_code") or account.custom_fields.get("bank_code")
        if not bank_code:
            raise HTTPException(status_code=400, detail="bank_code is required for a bank payout")
        account_name = (
            custom_fields.get("recipient_name")
            or account.custom_fields.get("recipient_name")
            or account.name
        )
    else:
        raw_phone = (
            payload.phone_number
            or custom_fields.get("customer_phone")
            or account.custom_fields.get("phone")
        )
        try:
            account_number = lipila.normalize_phone_for_channel(channel, raw_phone)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    email = custom_fields.get("customer_email") or account.email

    # The row is written first so the reference handed to Lipila always has a
    # transaction to come back to, even if the webhook beats the response.
    transaction.status = TransactionStatus.PENDING
    transaction.provider = lipila.PROVIDER_NAME
    transaction.provider_reference = lipila.new_reference()
    transaction.provider_channel = channel
    transaction.provider_status = "created"

    if is_payout:
        try:
            apply_balance(account, transaction)
        except InsufficientFunds:
            raise HTTPException(status_code=400, detail="Insufficient funds")

    account.updated_at = datetime.utcnow()
    session.add(transaction)
    session.add(account)
    session.commit()
    session.refresh(transaction)

    reference_data = f"Account {account.id}" + (f" / Group {account.group_id}" if account.group_id else "")

    try:
        if is_collection:
            provider_status, provider_payload = await lipila.start_collection(
                settings=settings,
                transaction=transaction,
                account=account,
                channel=channel,
                account_number=account_number,
                email=email,
                currency=currency,
                reference_data=reference_data,
            )
        else:
            provider_status, provider_payload = await lipila.start_payout(
                settings=settings,
                transaction=transaction,
                account=account,
                channel=channel,
                account_number=account_number,
                currency=currency,
                reference_data=reference_data,
                bank_code=bank_code,
                account_name=account_name,
            )
    except (lipila.LipilaNotConfigured, lipila.PayoutsDisabled) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    lipila.apply_provider_status(
        session, transaction, provider_status, provider_payload, source="provider_response"
    )
    session.refresh(transaction)
    _run_queued_lending(session, account, transaction)
    return _read(transaction, lipila.find_card_redirect_url(provider_payload))


def _run_queued_lending(session: Session, account: Account, transaction: Transaction) -> None:
    if (
        account.group_id
        and transaction.status == TransactionStatus.COMPLETED
        and transaction.type == TransactionType.DEPOSIT
    ):
        process_queued_requests(session, group_id=int(account.group_id))


@router.post("/{transaction_id}/refresh", response_model=TransactionRead)
async def refresh_transaction(
    transaction_id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> Transaction:
    """Re-read a Lipila payment's state from the provider.

    Useful when a webhook was missed, and the only way a card payer's own tab
    learns the outcome after they come back from the hosted page.
    """
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    account = session.get(Account, transaction.account_id)
    is_admin = _is_platform_admin(getattr(current_user, "role", ""))
    if not is_admin and (not account or account.user_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    if not transaction.provider_reference:
        raise HTTPException(status_code=400, detail="Transaction was not routed through Lipila")

    await lipila.refresh_transaction_status(session, transaction, get_settings())
    session.refresh(transaction)
    if account:
        _run_queued_lending(session, account, transaction)
    return transaction


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: int,
    payload: TransactionStatusUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> Transaction:
    """Override a transaction's status by hand.

    This moves a member's balance on one person's say-so, which is the one thing
    a group joins a platform to stop happening unobserved. It therefore demands
    a reason and writes an audit entry naming the operator, in the same database
    transaction as the change itself.
    """
    if not _is_platform_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Admins only")
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    new_status = payload.status
    if transaction.status == new_status:
        return transaction

    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required to change a transaction by hand")

    account = session.get(Account, transaction.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found for transaction")

    previous_status = transaction.status
    previous_balance = float(account.balance)

    try:
        apply_status_change(account, transaction, new_status)
    except InsufficientFunds:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    audit.record(
        session,
        actor=current_user,
        action=audit.TRANSACTION_STATUS_CHANGED,
        entity_type="transaction",
        entity_id=transaction.id,
        before={"status": previous_status.value, "account_balance": previous_balance},
        after={"status": new_status.value, "account_balance": float(account.balance)},
        reason=reason,
    )

    session.add(account)
    session.add(transaction)
    # One commit, so the audit entry and the balance move land together.
    session.commit()
    session.refresh(transaction)
    _run_queued_lending(session, account, transaction)
    return transaction
