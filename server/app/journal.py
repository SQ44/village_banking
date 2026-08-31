"""Double-entry postings behind the balances.

An account balance says how much a member has. It cannot say where the money
came from, where it went, or how much of it the group actually holds — because
every balance move is one-sided. These entries are the other side.

The rule the whole module exists to keep: **debits equal credits, always**. That
is what makes "money at Lipila" and "money owed to members" two separate,
checkable numbers instead of one number standing in for both. A collection fee
is the clearest case — the member is owed the gross, the group receives the net,
and the difference has to be named or the books will not balance.

Nothing here decides whether money moved; `ledger` does that. This module only
records what `ledger` did, and refuses to record the same event twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from .models import (
    Account,
    JournalEntry,
    JournalLine,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from .money import ZERO, from_minor, money, to_minor

# --- chart of accounts -------------------------------------------------
# Assets: what the group has, and where.
LIPILA_SETTLEMENT = "lipila_settlement"
CASH_ON_HAND = "cash_on_hand"
LOANS_RECEIVABLE = "loans_receivable"
# Liability: what the group owes its members. The control account.
MEMBER_SAVINGS = "member_savings"
# Expenses.
PROVIDER_FEES = "provider_fees"
INTEREST_EXPENSE = "interest_expense"
# Income.
INTEREST_INCOME = "interest_income"
FEE_INCOME = "fee_income"

TRANSACTION_REFERENCE = "transaction"

# Money coming from a member increases what the group owes them.
CREDIT_TYPES = {TransactionType.DEPOSIT, TransactionType.LOAN_REPAYMENT, TransactionType.INTEREST}


@dataclass(frozen=True)
class StatementLine:
    """One movement on a member's statement, with the balance it left behind."""

    transaction_id: int
    created_at: object
    description: Optional[str]
    type: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


def _is_loan_interest(transaction: Transaction) -> bool:
    """Is this charge the interest half of a loan repayment?

    The loan router tags it when it splits a repayment. Both the tag and the
    loan reference are required: a bare `component` on some unrelated charge
    should not be read as lending income.
    """
    fields = transaction.custom_fields or {}
    return fields.get("component") == "interest" and fields.get("loan_id") is not None


def _where_the_money_sits(transaction: Transaction) -> str:
    """Which asset account this transaction's cash moved through.

    Cash handed over at a meeting is in somebody's tin, not at the provider.
    Reading one as the other would overstate what is actually reachable.
    """
    if (transaction.custom_fields or {}).get("settled_in") == "cash":
        return CASH_ON_HAND
    if transaction.provider:
        return LIPILA_SETTLEMENT
    return CASH_ON_HAND


def _should_post(transaction: Transaction) -> bool:
    """Only settled money is booked.

    A pending collection is a request, not a payment. A failed payout was handed
    back. Booking either would put money in the accounts that nobody has.
    """
    return transaction.status == TransactionStatus.COMPLETED


def post_transaction(
    session: Session,
    transaction: Transaction,
    account: Account,
) -> Optional[JournalEntry]:
    """Book one settled transaction. Returns None if there was nothing to book.

    Safe to call twice: the second call finds the existing entry and adds
    nothing, which is what makes a redelivered webhook harmless.
    """
    if not _should_post(transaction):
        return None

    reference_id = str(transaction.id)
    existing = session.exec(
        select(JournalEntry)
        .where(JournalEntry.reference_type == TRANSACTION_REFERENCE)
        .where(JournalEntry.reference_id == reference_id)
    ).first()
    if existing is not None:
        return existing

    gross = money(transaction.amount)
    fee = money(transaction.provider_fee or ZERO)
    asset = _where_the_money_sits(transaction)

    entry = JournalEntry(
        reference_type=TRANSACTION_REFERENCE,
        reference_id=reference_id,
        group_id=account.group_id,
        description=transaction.description or transaction.type.value,
    )
    session.add(entry)
    session.flush()  # Need the id for the lines.

    lines: list[tuple[str, Decimal, Decimal]] = []

    if transaction.type in CREDIT_TYPES:
        if transaction.type == TransactionType.INTEREST:
            # Interest paid to a saver costs the group; no cash moves.
            lines.append((INTEREST_EXPENSE, gross, ZERO))
        elif transaction.type == TransactionType.LOAN_REPAYMENT:
            # The principal half of a repayment. The borrower's own savings
            # funded the loan, so paying it back restores them — the group is no
            # better off for being handed back what it lent, and no income
            # arises here. The gain is the interest, booked separately below.
            lines.append((asset, gross - fee, ZERO))
            if fee > ZERO:
                lines.append((PROVIDER_FEES, fee, ZERO))
            lines.append((MEMBER_SAVINGS, ZERO, gross))
            return _finish(session, entry, lines, account, transaction)
        else:
            lines.append((asset, gross - fee, ZERO))
            if fee > ZERO:
                lines.append((PROVIDER_FEES, fee, ZERO))
        lines.append((MEMBER_SAVINGS, ZERO, gross))
        return _finish(session, entry, lines, account, transaction)

    # Money leaving a member's balance.
    lines.append((MEMBER_SAVINGS, gross, ZERO))
    if transaction.type == TransactionType.FEE:
        # The loan router books the interest half of a repayment as a charge
        # against savings, tagging it. Interest earned by lending is what makes
        # the pot grow and is what members meet to hear; filing it under service
        # charges would bury the one number the group cares about.
        if _is_loan_interest(transaction):
            lines.append((INTEREST_INCOME, ZERO, gross))
        else:
            lines.append((FEE_INCOME, ZERO, gross))
    elif transaction.type == TransactionType.LOAN_DISBURSEMENT:
        # The lending code draws the principal from the borrower's own savings,
        # so no money is put at risk by the group and no receivable arises —
        # economically this is a withdrawal, and booking it as one is the only
        # way the entry stays true. What is actually still owed lives on the
        # loan itself, which is where `loans_outstanding` reads it from.
        #
        # That the borrower funds their own loan conflates saving with
        # borrowing. It is recorded as it stands rather than corrected here;
        # changing it is a lending decision.
        if fee > ZERO:
            lines.append((PROVIDER_FEES, fee, ZERO))
        lines.append((asset, ZERO, gross + fee))
    else:
        # A withdrawal. The member receives the full amount; the group pays the
        # provider's charge on top.
        if fee > ZERO:
            lines.append((PROVIDER_FEES, fee, ZERO))
        lines.append((asset, ZERO, gross + fee))

    return _finish(session, entry, lines, account, transaction)


def _finish(
    session: Session,
    entry: JournalEntry,
    lines: list[tuple[str, Decimal, Decimal]],
    account: Account,
    transaction: Transaction,
) -> JournalEntry:
    for code, debit, credit in lines:
        session.add(
            JournalLine(
                journal_entry_id=entry.id,
                account_code=code,
                debit_minor=to_minor(debit),
                credit_minor=to_minor(credit),
                account_id=account.id if code == MEMBER_SAVINGS else None,
            )
        )
    session.flush()
    if not entry_is_balanced(session, entry):
        # A refusal, not a warning. Half an entry is worse than none.
        raise ValueError(f"unbalanced journal entry for transaction {transaction.id}")
    return entry


# ----------------------------------------------------------------------
# Reading the books
# ----------------------------------------------------------------------


def entry_is_balanced(session: Session, entry: JournalEntry) -> bool:
    lines = session.exec(select(JournalLine).where(JournalLine.journal_entry_id == entry.id)).all()
    return sum(line.debit_minor for line in lines) == sum(line.credit_minor for line in lines)


def books_are_balanced(session: Session) -> bool:
    """Every entry, not just the total — a pair of opposite errors still sums to zero."""
    return all(entry_is_balanced(session, entry) for entry in session.exec(select(JournalEntry)).all())


def trial_balance(session: Session, *, group_id: Optional[int] = None) -> dict[str, Decimal]:
    """Net movement per account code, as a positive figure in its natural direction.

    Assets and expenses are debit-normal, so they read debit minus credit.
    Liabilities and income are credit-normal and read the other way, which is
    what makes `member_savings` comparable to the sum of member balances.
    """
    statement = select(JournalLine, JournalEntry).join(
        JournalEntry, JournalLine.journal_entry_id == JournalEntry.id
    )
    if group_id is not None:
        statement = statement.where(JournalEntry.group_id == group_id)

    credit_normal = {MEMBER_SAVINGS, INTEREST_INCOME, FEE_INCOME}
    totals: dict[str, int] = {}
    for line, _entry in session.exec(statement).all():
        signed = (
            line.credit_minor - line.debit_minor
            if line.account_code in credit_normal
            else line.debit_minor - line.credit_minor
        )
        totals[line.account_code] = totals.get(line.account_code, 0) + signed
    return {code: from_minor(value) for code, value in totals.items()}


def control_total_matches(session: Session, *, group_id: Optional[int] = None) -> bool:
    """Does what the books say members are owed equal what their accounts say?

    This is the check that catches a balance edited behind the journal's back —
    the silent hand on the pot that a one-sided ledger cannot see.
    """
    booked = trial_balance(session, group_id=group_id).get(MEMBER_SAVINGS, ZERO)

    statement = select(Account)
    if group_id is not None:
        statement = statement.where(Account.group_id == group_id)
    stored = sum((money(a.balance) for a in session.exec(statement).all()), ZERO)
    return booked == stored


def statement(session: Session, *, account_id: int) -> list[StatementLine]:
    """One member's movements in order, each with the balance it left behind."""
    rows = session.exec(
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(JournalLine.account_id == account_id)
        .where(JournalLine.account_code == MEMBER_SAVINGS)
        .order_by(JournalEntry.created_at, JournalEntry.id)
    ).all()

    lines: list[StatementLine] = []
    running = ZERO
    for line, entry in rows:
        credit = from_minor(line.credit_minor)
        debit = from_minor(line.debit_minor)
        running = running + credit - debit
        lines.append(
            StatementLine(
                transaction_id=int(entry.reference_id) if entry.reference_id.isdigit() else 0,
                created_at=entry.created_at,
                description=entry.description,
                type=entry.description or "",
                debit=debit,
                credit=credit,
                running_balance=running,
            )
        )
    return lines


def backfill(session: Session) -> int:
    """Book every settled transaction that has no entry yet.

    Two jobs. It brings an existing database's history into the journal so the
    control total is meaningful from the first run, and it is a safety net: if a
    posting is ever missed at the point of settlement, this finds it rather than
    leaving the books quietly short.
    """
    posted = 0
    booked = {
        entry.reference_id
        for entry in session.exec(
            select(JournalEntry).where(JournalEntry.reference_type == TRANSACTION_REFERENCE)
        ).all()
    }
    transactions = session.exec(
        select(Transaction)
        .where(Transaction.status == TransactionStatus.COMPLETED)
        .order_by(Transaction.created_at, Transaction.id)
    ).all()
    for transaction in transactions:
        if str(transaction.id) in booked:
            continue
        account = session.get(Account, transaction.account_id)
        if account is None:
            continue
        if post_transaction(session, transaction, account) is not None:
            posted += 1
    session.commit()
    return posted
