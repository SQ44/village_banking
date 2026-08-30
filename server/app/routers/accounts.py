from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import audit
from ..database import get_session
from ..models import Account, Transaction, TransactionStatus, TransactionType
from ..schemas import AccountCreate, AccountRead, AccountUpdate
from ..auth import get_current_active_user

router = APIRouter(prefix="/accounts", tags=["Accounts"])

def _is_platform_admin(role: str) -> bool:
    return role in {"admin", "operator"}


@router.get("", response_model=List[AccountRead])
def list_accounts(
    search: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> List[Account]:
    statement = select(Account)
    if not _is_platform_admin(getattr(current_user, "role", "")):
        statement = statement.where(Account.user_id == current_user.id)
    if search:
        statement = statement.where(Account.name.contains(search))
    accounts = session.exec(statement).all()
    return accounts


@router.post("", response_model=AccountRead, status_code=201)
def create_account(
    payload: AccountCreate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> Account:
    if not _is_platform_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Admins only")
    account = Account(
        name=payload.name,
        email=payload.email,
        group_name=payload.group_name,
        group_id=payload.group_id,
        product_id=payload.product_id,
        custom_fields=payload.custom_fields,
        balance=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    if payload.initial_deposit > 0:
        transaction = Transaction(
            account_id=account.id,
            amount=payload.initial_deposit,
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.COMPLETED,
            description="Initial deposit",
        )
        account.balance += payload.initial_deposit
        session.add(transaction)
        session.add(account)
        session.commit()
        session.refresh(account)
    return account


@router.get("/{account_id}", response_model=AccountRead)
def get_account(
    account_id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> Account:
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if not _is_platform_admin(getattr(current_user, "role", "")) and account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    return account


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> Account:
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if not _is_platform_admin(getattr(current_user, "role", "")) and account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    updates = payload.model_dump(exclude_unset=True)
    if not _is_platform_admin(getattr(current_user, "role", "")):
        updates.pop("balance", None)
        updates.pop("product_id", None)
        updates.pop("group_id", None)
        updates.pop("group_name", None)

    # Setting a balance here writes a number no transaction explains, which is
    # both a silent hand on the pot and a guaranteed reconciliation mismatch. It
    # stays available for correcting a genuinely broken account, but it has to
    # say why, and it leaves a record naming the operator.
    previous_balance = float(account.balance)
    new_balance = updates.get("balance")
    balance_changing = new_balance is not None and float(new_balance) != previous_balance
    if balance_changing and not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="A reason is required to set a balance by hand")

    for field, value in updates.items():
        if field == "reason":
            continue  # Audit metadata, not a column.
        if field == "custom_fields" and value is not None:
            account.custom_fields.update(value)
        elif hasattr(account, field) and value is not None:
            setattr(account, field, value)
    account.updated_at = datetime.utcnow()

    if balance_changing:
        audit.record(
            session,
            actor=current_user,
            action=audit.ACCOUNT_BALANCE_CHANGED,
            entity_type="account",
            entity_id=account.id,
            before={"balance": previous_balance},
            after={"balance": float(account.balance)},
            reason=payload.reason.strip(),
        )

    session.add(account)
    # One commit, so the audit entry cannot be lost while the change survives.
    session.commit()
    session.refresh(account)
    return account
