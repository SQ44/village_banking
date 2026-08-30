from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from .models import Account, InterestAccrual, Transaction, TransactionStatus, TransactionType


def calculate_interest(balance: float, annual_rate: float, days: int) -> float:
    if annual_rate <= 0 or balance <= 0 or days <= 0:
        return 0
    daily_rate = annual_rate / 100 / 365
    return round(balance * daily_rate * days, 2)


def apply_interest(
    session: Session,
    account: Account,
    *,
    annual_rate: float,
    period_start: datetime,
    period_end: datetime,
) -> tuple[InterestAccrual, Transaction | None]:
    """Credit earned interest to an account, and record why.

    Both an `InterestAccrual` (the calculation: rate, period, amount) and a
    `Transaction` (the money movement) are written. The transaction is what
    makes the credit reconcilable — `reconciliation.check_all` rebuilds a
    balance from transactions alone, so a balance credited without one shows up
    as an unexplained number the operator has to chase.

    Both writers land in a single commit so the accrual, the entry and the new
    balance cannot disagree.

    Returns the accrual and the transaction. The transaction is None when the
    interest rounded to zero, which is not worth a ledger entry.
    """
    days = max((period_end - period_start).days, 1)
    amount = calculate_interest(account.balance, annual_rate, days)

    accrual = InterestAccrual(
        account_id=account.id,
        amount=amount,
        annual_rate=annual_rate,
        period_start=period_start,
        period_end=period_end,
    )
    session.add(accrual)
    session.flush()  # Assigns accrual.id for the transaction to point at.

    transaction: Transaction | None = None
    if amount > 0:
        account.balance += amount
        account.updated_at = datetime.utcnow()
        transaction = Transaction(
            account_id=account.id,
            amount=amount,
            type=TransactionType.INTEREST,
            status=TransactionStatus.COMPLETED,
            description=f"Interest for {period_start.date()} - {period_end.date()}",
            custom_fields={"interest_accrual_id": accrual.id},
            created_at=datetime.utcnow(),
        )
        session.add(transaction)
        session.add(account)

    session.commit()
    session.refresh(account)
    session.refresh(accrual)
    if transaction is not None:
        session.refresh(transaction)
    return accrual, transaction
