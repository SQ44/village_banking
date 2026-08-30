"""Balance movement for a transaction, in one place.

Both the API and the Lipila webhook settle transactions, and they must agree on
what a status change does to an account. The rules live here so neither can
drift from the other.
"""

from datetime import datetime

from .models import Account, Transaction, TransactionStatus, TransactionType

# Types that add to a member's balance when they complete; everything else
# takes away from it.
CREDIT_TYPES = {
    TransactionType.DEPOSIT,
    TransactionType.LOAN_REPAYMENT,
    TransactionType.INTEREST,
}

# Money moving out to a member. These are debited when the payout is requested
# rather than when it settles, so the same balance cannot be withdrawn twice
# while the first payout is still in flight.
OUTBOUND_TYPES = {
    TransactionType.WITHDRAWAL,
    TransactionType.LOAN_DISBURSEMENT,
}


class InsufficientFunds(RuntimeError):
    """The account cannot cover the debit being attempted."""


def is_credit(transaction: Transaction) -> bool:
    return transaction.type in CREDIT_TYPES


def apply_balance(account: Account, transaction: Transaction) -> None:
    """Move the balance in the direction this transaction implies."""
    if is_credit(transaction):
        account.balance += transaction.amount
    else:
        if account.balance < transaction.amount:
            raise InsufficientFunds("Insufficient funds")
        account.balance -= transaction.amount
    account.updated_at = datetime.utcnow()


def reverse_balance(account: Account, transaction: Transaction) -> None:
    """Undo a movement that was applied earlier.

    This can drive a balance below zero, and deliberately does. A deposit that
    settles, gets spent, and is then charged back by the provider leaves the
    member genuinely overdrawn — the money left the group. Clamping at zero
    would invent the difference and hide the debt, so the true number is kept
    instead.

    Nothing further can be spent from it: `apply_balance` refuses any debit an
    account cannot cover, so a negative balance blocks withdrawals and
    disbursements until it is settled. `reconciliation.check_all` reports the
    account so an operator sees it rather than discovering it later.
    """
    if is_credit(transaction):
        account.balance -= transaction.amount
    else:
        account.balance += transaction.amount
    account.updated_at = datetime.utcnow()


def apply_status_change(
    account: Account,
    transaction: Transaction,
    new_status: TransactionStatus,
) -> None:
    """Adjust the balance for a transaction moving to `new_status`.

    The caller has already decided the move is legal; this only settles money.
    A transaction whose funds were reserved up front (an outbound payout) has
    already moved the balance, so completing it must not move it a second time.
    """
    previous_status = transaction.status
    if previous_status == new_status:
        return

    reserved_up_front = transaction.type in OUTBOUND_TYPES and transaction.provider_reference is not None

    if previous_status != TransactionStatus.COMPLETED and new_status == TransactionStatus.COMPLETED:
        if not reserved_up_front:
            apply_balance(account, transaction)
    elif previous_status == TransactionStatus.COMPLETED and new_status != TransactionStatus.COMPLETED:
        reverse_balance(account, transaction)
    elif previous_status == TransactionStatus.PENDING and new_status == TransactionStatus.FAILED:
        # A reserved payout that never went through has to give the money back.
        if reserved_up_front:
            reverse_balance(account, transaction)

    transaction.status = new_status
    account.updated_at = datetime.utcnow()
