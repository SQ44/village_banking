from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from .models import Account, InterestAccrual


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
) -> InterestAccrual:
    days = max((period_end - period_start).days, 1)
    amount = calculate_interest(account.balance, annual_rate, days)
    account.balance += amount
    accrual = InterestAccrual(
        account_id=account.id,
        amount=amount,
        annual_rate=annual_rate,
        period_start=period_start,
        period_end=period_end,
    )
    session.add(accrual)
    session.add(account)
    session.commit()
    session.refresh(account)
    session.refresh(accrual)
    return accrual
