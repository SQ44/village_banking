from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, JSON, Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from .money import (
    MONEY_PRECISION,
    MONEY_SCALE,
    RATE_PRECISION,
    RATE_SCALE,
    ZERO,
)


def money_column(**kwargs: Any) -> Any:
    """A currency column: NUMERIC(12, 2), never a float.

    Declared once here so every amount in the schema has the same precision and
    the same storage type. On PostgreSQL this is a native fixed-point column; on
    SQLite the driver hands back an exactly-2dp `Decimal`, which is what lets
    `reconciliation` compare a balance to its entries with `==` instead of a
    tolerance.
    """
    return Field(sa_column=Column(Numeric(MONEY_PRECISION, MONEY_SCALE), **kwargs))


def rate_column(**kwargs: Any) -> Any:
    """A percentage column: NUMERIC(9, 4). Rates carry more places than money."""
    return Field(sa_column=Column(Numeric(RATE_PRECISION, RATE_SCALE), **kwargs))


class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    LOAN_DISBURSEMENT = "loan_disbursement"
    LOAN_REPAYMENT = "loan_repayment"
    INTEREST = "interest"
    FEE = "fee"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    email: str = Field(
        sa_column=Column(
            "email",
            String(255),
            unique=True,
            index=True,
            nullable=False
        )
    )

    full_name: Optional[str] = None
    hashed_password: str
    role: str = Field(default="admin")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SavingsProduct(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    interest_rate: Decimal = rate_column(nullable=False)
    compounding_days: int = Field(default=30)
    min_balance: Decimal = money_column(nullable=False, default=0)
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    accounts: List["Account"] = Relationship(back_populates="product")


class Group(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    terms: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    settings: Optional["GroupSettings"] = Relationship(back_populates="group")
    memberships: List["Membership"] = Relationship(back_populates="group")
    accounts: List["Account"] = Relationship(back_populates="group")


class GroupSettings(SQLModel, table=True):
    group_id: int = Field(foreign_key="group.id", primary_key=True)

    min_monthly_contribution: Decimal = money_column(nullable=False, default=0)
    # Percent of loan interest kept as an administration fee.
    admin_fee_percent: Decimal = rate_column(nullable=False, default=0)
    loan_interest_percent: Decimal = rate_column(nullable=False, default=10)

    enforce_loan_limit: bool = Field(default=True)
    # Max loan = contribution * multiplier.
    loan_limit_multiplier: Decimal = rate_column(nullable=False, default=2)

    # Total outstanding principal must stay at or below this percent of the pool.
    liquidity_max_outstanding_percent: Decimal = rate_column(nullable=False, default=80)
    min_term_months: int = Field(default=1)
    max_term_months: int = Field(default=12)
    max_active_loans_per_member: int = Field(default=1)
    cooldown_days_after_settlement: int = Field(default=0, description="Days after closing a loan before borrowing again")
    constitution_locked_at: Optional[datetime] = None

    withdrawal_cycle_days: int = Field(default=30)
    allow_advance_contribution: bool = Field(default=True)
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    group: "Group" = Relationship(back_populates="settings")


class MembershipRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"


class Membership(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    account_id: Optional[int] = Field(default=None, foreign_key="account.id", index=True)
    role: MembershipRole = Field(default=MembershipRole.MEMBER)
    accepted_terms_at: Optional[datetime] = None
    is_active: bool = Field(default=True)
    joined_at: datetime = Field(default_factory=datetime.utcnow)

    group: "Group" = Relationship(back_populates="memberships")
    user: "User" = Relationship()
    account: Optional["Account"] = Relationship()



class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: Optional[str] = Field(default=None, index=True)
    group_name: Optional[str] = Field(default=None, index=True)
    group_id: Optional[int] = Field(default=None, foreign_key="group.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    balance: Decimal = money_column(nullable=False, default=0)
    last_withdrawal_at: Optional[datetime] = None

    product_id: Optional[int] = Field(default=None, foreign_key="savingsproduct.id")
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    product: Optional["SavingsProduct"] = Relationship(back_populates="accounts")
    transactions: List["Transaction"] = Relationship(back_populates="account")
    group: Optional["Group"] = Relationship(back_populates="accounts")
    user: Optional["User"] = Relationship()



class PaymentChannel(str, Enum):
    MOBILE_MONEY = "mobile_money"
    CARD = "card"
    BANK = "bank"


class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    amount: Decimal = money_column(nullable=False)
    type: TransactionType
    status: TransactionStatus = Field(default=TransactionStatus.PENDING)
    description: Optional[str] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Payment provider linkage. `provider_reference` is what Lipila echoes back
    # on a webhook, so it is how an inbound event finds its transaction.
    provider: Optional[str] = Field(default=None, index=True)
    provider_reference: Optional[str] = Field(default=None, index=True, unique=True)
    provider_channel: Optional[PaymentChannel] = Field(default=None)
    # Lipila's own vocabulary, kept alongside the coarser ledger status.
    provider_status: Optional[str] = Field(default=None)
    provider_identifier: Optional[str] = Field(default=None)
    last_provider_sync_at: Optional[datetime] = Field(default=None)

    account: "Account" = Relationship(back_populates="transactions")


class ProviderEvent(SQLModel, table=True):
    """One received webhook, recorded so a redelivery cannot be applied twice."""

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(default="lipila", index=True)
    webhook_id: str = Field(index=True, unique=True)
    webhook_timestamp: Optional[datetime] = Field(default=None)
    provider_reference: Optional[str] = Field(default=None, index=True)
    processing_status: str = Field(default="received")
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = Field(default=None)


class IdempotencyRecord(SQLModel, table=True):
    """One money-moving request, remembered so a retry cannot repeat the work.

    `ProviderEvent` protects the inbound direction — Lipila telling us the same
    thing twice. This protects the other direction: our own client asking for
    the same thing twice. A phone on a weak network cannot tell a lost reply
    from a lost request, so it retries; without this the retry would start a
    second collection and put a second prompt on the member's handset against
    the same money.

    The first attempt claims the key and stores what it answered. A retry
    carrying that key is handed the stored answer back instead of doing the work
    again.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    # The key is scoped to the endpoint and the caller, so two users cannot
    # collide on the same key and one endpoint's key cannot replay on another.
    scope: str = Field(
        sa_column=Column("scope", String(400), unique=True, index=True, nullable=False)
    )
    endpoint: str
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    # Hash of the request body. The same key arriving with a different body is a
    # client bug, not a retry, and is refused rather than answered wrongly.
    request_fingerprint: str

    # "in_progress" while the original attempt is still running, "completed"
    # once its response is stored.
    state: str = Field(default="in_progress", index=True)
    response_status: Optional[int] = Field(default=None)
    response_body: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    completed_at: Optional[datetime] = Field(default=None)


class AuditLog(SQLModel, table=True):
    """A record of a human moving money by hand.

    Every automatic balance movement is explained by a transaction. These are
    the movements that are not: an operator overriding a payment's status, or
    editing a balance directly. The whole reason a group runs on this platform
    instead of one person's notebook is so that no single person can move the
    pot unobserved, which makes this table part of the product rather than
    plumbing — it is served back to admins at `GET /operations/audit`.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    actor_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    # Copied rather than joined: the user row can be renamed or deactivated
    # later, and an audit entry has to keep saying who it was at the time.
    actor_email: Optional[str] = Field(default=None)

    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)

    # Why the operator says they did it. Required by the endpoints that write
    # here, because "who" without "why" does not settle an argument.
    reason: Optional[str] = None

    before: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    after: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class LoanStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class RepaymentFrequency(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class LoanRequestStatus(str, Enum):
    REQUESTED = "requested"
    QUEUED = "queued"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"


class LoanRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    borrower_account_id: int = Field(foreign_key="account.id", index=True)
    requester_user_id: int = Field(foreign_key="user.id", index=True)

    principal: Decimal = money_column(nullable=False)
    term_months: int = Field(default=1)
    repayment_frequency: RepaymentFrequency = Field(default=RepaymentFrequency.MONTHLY)
    interest_rate_percent: Optional[Decimal] = rate_column(nullable=True, default=None)

    status: LoanRequestStatus = Field(default=LoanRequestStatus.REQUESTED, index=True)
    description: Optional[str] = None
    decision_reason: Optional[str] = None
    decided_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    decided_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Loan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    borrower_account_id: int = Field(foreign_key="account.id", index=True)

    principal: Decimal = money_column(nullable=False)
    interest_rate_percent: Decimal = rate_column(nullable=False)
    admin_fee_percent: Decimal = rate_column(nullable=False, default=0)

    term_months: int = Field(default=1)
    repayment_frequency: RepaymentFrequency = Field(default=RepaymentFrequency.MONTHLY)

    outstanding_principal: Decimal = money_column(nullable=False)
    outstanding_interest: Decimal = money_column(nullable=False, default=0)
    status: LoanStatus = Field(default=LoanStatus.ACTIVE)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    disbursed_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    installments: List["LoanInstallment"] = Relationship(back_populates="loan")


class InstallmentStatus(str, Enum):
    DUE = "due"
    PAID = "paid"


class LoanInstallment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    loan_id: int = Field(foreign_key="loan.id", index=True)
    sequence: int = Field(index=True)
    due_date: datetime
    principal_due: Decimal = money_column(nullable=False)
    interest_due: Decimal = money_column(nullable=False)
    status: InstallmentStatus = Field(default=InstallmentStatus.DUE)
    paid_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    loan: "Loan" = Relationship(back_populates="installments")


class GroupFee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    amount: Decimal = money_column(nullable=False)
    description: str = Field(default="Administration fee")
    created_at: datetime = Field(default_factory=datetime.utcnow)



class InterestAccrual(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    amount: Decimal = money_column(nullable=False)
    applied_on: datetime = Field(default_factory=datetime.utcnow)
    period_start: datetime
    period_end: datetime
    annual_rate: Decimal = rate_column(nullable=False)
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    account: "Account" = Relationship()
