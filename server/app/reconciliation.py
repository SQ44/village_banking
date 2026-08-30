"""Proving a stored balance against the entries that should explain it.

`Account.balance` is this app's primary record: it is mutated in place as
transactions settle, and every read of a member's savings comes from it. That
is fast and simple, and it has one weakness — nothing forces it to agree with
the transactions behind it. A path that moves the balance without writing an
entry, or writes an entry without moving the balance, leaves a number nobody
can derive and an argument nobody can settle. In a village banking group, where
the whole point is that members can check the pot, that is the failure that
matters.

So the balance stays primary and this recomputes it from the entries on a
schedule. Cheap, and it turns a silent divergence into a named discrepancy on
the operator's attention page.

The rules below mirror `ledger.apply_status_change` exactly, and import its
constants rather than restating them, so the two cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session, select

from .ledger import CREDIT_TYPES, OUTBOUND_TYPES
from .models import Account, Transaction, TransactionStatus

# Half a ngwee. Below this a difference is float representation noise, not a
# real disagreement — see the note in the project README about money currently
# being stored as float.
TOLERANCE = 0.005


@dataclass
class Discrepancy:
    account_id: int
    account_name: str
    stored_balance: float
    derived_balance: float
    transaction_count: int

    @property
    def difference(self) -> float:
        """Positive when the stored balance claims more money than the entries do."""
        return round(self.stored_balance - self.derived_balance, 2)


@dataclass
class ReconciliationReport:
    checked: int = 0
    discrepancies: list[Discrepancy] = field(default_factory=list)
    negative_balances: list[Discrepancy] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.discrepancies and not self.negative_balances


def transaction_effect(transaction: Transaction) -> float:
    """What this one transaction should have done to its account's balance.

    Mirrors `ledger.apply_status_change`:

    * An outbound payout routed through a provider is debited when it is
      *requested*, not when it settles, so that the same balance cannot be
      withdrawn twice while one payout is in flight. It therefore counts while
      pending, still counts once completed, and counts for nothing if it failed
      (the money was handed back).
    * Everything else moves the balance only on completion.
    """
    reserved_up_front = transaction.type in OUTBOUND_TYPES and transaction.provider_reference is not None
    amount = float(transaction.amount)

    if reserved_up_front:
        if transaction.status == TransactionStatus.FAILED:
            return 0.0
        return -amount

    if transaction.status != TransactionStatus.COMPLETED:
        return 0.0
    return amount if transaction.type in CREDIT_TYPES else -amount


def derived_balance(transactions: list[Transaction]) -> float:
    return round(sum(transaction_effect(tx) for tx in transactions), 2)


def check_account(session: Session, account: Account) -> Optional[Discrepancy]:
    """Recompute one account. Returns None when the entries explain the balance."""
    transactions = list(
        session.exec(select(Transaction).where(Transaction.account_id == account.id)).all()
    )
    derived = derived_balance(transactions)
    stored = round(float(account.balance), 2)

    if abs(stored - derived) <= TOLERANCE:
        return None

    return Discrepancy(
        account_id=int(account.id),
        account_name=account.name,
        stored_balance=stored,
        derived_balance=derived,
        transaction_count=len(transactions),
    )


def check_all(session: Session, *, group_id: Optional[int] = None) -> ReconciliationReport:
    """Recompute every account (or every account in one group).

    A negative balance is reported alongside a mismatch but kept separate: it is
    not a bookkeeping error, it is a real state the ledger can reach when a
    settled deposit is later reversed after the member has already spent it. The
    money genuinely left, so the number is right — it just needs a human.
    """
    statement = select(Account)
    if group_id is not None:
        statement = statement.where(Account.group_id == group_id)
    accounts = list(session.exec(statement).all())

    report = ReconciliationReport(checked=len(accounts))
    for account in accounts:
        discrepancy = check_account(session, account)
        if discrepancy is not None:
            report.discrepancies.append(discrepancy)
        if float(account.balance) < -TOLERANCE:
            report.negative_balances.append(
                Discrepancy(
                    account_id=int(account.id),
                    account_name=account.name,
                    stored_balance=round(float(account.balance), 2),
                    derived_balance=discrepancy.derived_balance
                    if discrepancy
                    else round(float(account.balance), 2),
                    transaction_count=discrepancy.transaction_count if discrepancy else 0,
                )
            )
    return report
