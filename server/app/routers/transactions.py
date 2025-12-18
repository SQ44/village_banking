from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_active_user
from ..database import get_session
from ..lenco_service import LencoPayClient
from ..models import Account, GroupSettings, Membership, Transaction, TransactionStatus, TransactionType
from ..schemas import TransactionCreate, TransactionRead, TransactionStatusUpdate

router = APIRouter(prefix="/transactions", tags=["Transactions"])

def _is_platform_admin(role: str) -> bool:
    return role in {"admin", "operator"}


def _get_membership(session: Session, *, group_id: int, user_id: int) -> Membership | None:
    statement = select(Membership).where(
        Membership.group_id == group_id,
        Membership.user_id == user_id,
        Membership.is_active.is_(True),
    )
    return session.exec(statement).first()


def _apply_balance(account: Account, transaction: Transaction) -> None:
    if transaction.status != TransactionStatus.COMPLETED:
        return
    if transaction.type in {
        TransactionType.DEPOSIT,
        TransactionType.LOAN_REPAYMENT,
        TransactionType.INTEREST,
    }:
        account.balance += transaction.amount
    elif transaction.type == TransactionType.WITHDRAWAL:
        if account.balance < transaction.amount:
            raise HTTPException(status_code=400, detail="Insufficient funds")
        account.balance -= transaction.amount
    elif transaction.type == TransactionType.FEE:
        account.balance -= transaction.amount
    elif transaction.type == TransactionType.LOAN_DISBURSEMENT:
        account.balance -= transaction.amount


@router.get("/", response_model=List[TransactionRead])
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


@router.post("/", response_model=TransactionRead, status_code=201)
async def create_transaction(
    payload: TransactionCreate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> Transaction:
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
    currency = str(custom_fields.get("currency") or "ZMW")

    settings: GroupSettings | None = None
    if account.group_id:
        membership = _get_membership(session, group_id=account.group_id, user_id=current_user.id)
        if membership is None and not is_admin:
            raise HTTPException(status_code=403, detail="Not a group member")
        if membership and membership.accepted_terms_at is None and not is_admin:
            raise HTTPException(status_code=403, detail="Accept group terms first")
        settings = session.get(GroupSettings, account.group_id)

    if settings and not is_admin and payload.type == TransactionType.DEPOSIT:
        months = int(custom_fields.get("months_covered") or 1)
        if months < 1:
            raise HTTPException(status_code=400, detail="months_covered must be >= 1")
        minimum = float(settings.min_monthly_contribution) * months
        if minimum > 0 and payload.amount < minimum:
            raise HTTPException(status_code=400, detail=f"Minimum contribution is {minimum:.2f} for {months} month(s)")

    if settings and not is_admin and payload.type == TransactionType.WITHDRAWAL and settings.withdrawal_cycle_days > 0:
        if account.last_withdrawal_at:
            elapsed = (datetime.utcnow() - account.last_withdrawal_at).days
            if elapsed < settings.withdrawal_cycle_days:
                raise HTTPException(status_code=400, detail="Withdrawal not allowed yet for this cycle")
        account.last_withdrawal_at = datetime.utcnow()

    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    recipient_account_number: Optional[str] = None
    recipient_bank_code: Optional[str] = None
    recipient_name: Optional[str] = None

    client: Optional[LencoPayClient] = None
    if payload.use_lenco:
        client = LencoPayClient()
        using_lenco_pay = bool(client.lenco_pay_base)
        if payload.type in {TransactionType.DEPOSIT, TransactionType.LOAN_REPAYMENT}:
            customer_phone = custom_fields.get("customer_phone") or account.custom_fields.get("phone")
            customer_email = custom_fields.get("customer_email") or account.email
            if using_lenco_pay and not (customer_email or customer_phone):
                raise HTTPException(
                    status_code=400,
                    detail="customer_email or customer_phone is required for Lenco Pay collections",
                )
        else:
            recipient_account_number = (
                custom_fields.get("account_number")
                or custom_fields.get("recipient_account_number")
                or account.custom_fields.get("bank_account")
            )
            if not recipient_account_number:
                raise HTTPException(
                    status_code=400,
                    detail="account_number custom field is required for Lenco Pay transfers",
                )
            if using_lenco_pay:
                recipient_bank_code = (
                    custom_fields.get("bank_code")
                    or custom_fields.get("recipient_bank_code")
                    or account.custom_fields.get("bank_code")
                )
                if not recipient_bank_code:
                    raise HTTPException(
                        status_code=400,
                        detail="bank_code custom field is required for Lenco Pay transfers",
                    )
                recipient_name = (
                    custom_fields.get("recipient_name")
                    or account.custom_fields.get("recipient_name")
                    or account.name
                )

    transaction = Transaction(
        account_id=payload.account_id,
        amount=payload.amount,
        type=payload.type,
        status=payload.status,
        description=payload.description,
        custom_fields=custom_fields,
        created_at=datetime.utcnow(),
    )

    _apply_balance(account, transaction)
    account.updated_at = datetime.utcnow()
    session.add(transaction)
    session.add(account)
    session.commit()
    session.refresh(transaction)

    if payload.use_lenco:
        assert client is not None
        reference = f"txn-{transaction.id}"
        description = payload.description or f"{payload.type.value} for {account.name}"
        if payload.type in {TransactionType.DEPOSIT, TransactionType.LOAN_REPAYMENT}:
            response = await client.collect_payment(
                amount=payload.amount,
                reference=reference,
                customer_email=customer_email,
                customer_phone=customer_phone,
                customer_name=account.name,
                currency=currency,
                description=description,
                callback_url=custom_fields.get("callback_url"),
            )
        else:
            assert recipient_account_number is not None
            response = await client.create_transfer(
                amount=payload.amount,
                reference=reference,
                recipient_account_number=recipient_account_number,
                recipient_bank_code=recipient_bank_code or "",
                recipient_name=recipient_name or "",
                currency=currency,
                description=description,
            )
        transaction.custom_fields["lenco_response"] = response
        session.add(transaction)
        session.commit()
        session.refresh(transaction)
    return transaction


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: int,
    payload: TransactionStatusUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> Transaction:
    if not _is_platform_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Admins only")
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    new_status = payload.status
    if transaction.status == new_status:
        return transaction

    account = session.get(Account, transaction.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found for transaction")

    previous_status = transaction.status
    transaction.status = new_status

    if previous_status != TransactionStatus.COMPLETED and new_status == TransactionStatus.COMPLETED:
        _apply_balance(account, transaction)
    elif previous_status == TransactionStatus.COMPLETED and new_status != TransactionStatus.COMPLETED:
        # Roll back balance impact if a completed transaction is reverted.
        if transaction.type in {
            TransactionType.DEPOSIT,
            TransactionType.LOAN_REPAYMENT,
            TransactionType.INTEREST,
        }:
            account.balance -= transaction.amount
        else:
            account.balance += transaction.amount

    account.updated_at = datetime.utcnow()
    session.add(account)
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction
