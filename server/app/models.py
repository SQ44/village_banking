from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, JSON, String
from sqlmodel import Field, Relationship, SQLModel


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
    interest_rate: float = Field(description="Annual interest rate as a percentage")
    compounding_days: int = Field(default=30)
    min_balance: float = Field(default=0)
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

    min_monthly_contribution: float = Field(default=0)
    admin_fee_percent: float = Field(default=0, description="Percent of loan interest kept as admin fee")
    loan_interest_percent: float = Field(default=10, description="Default loan interest percent")

    enforce_loan_limit: bool = Field(default=True)
    loan_limit_multiplier: float = Field(default=2, description="Max loan = contribution * multiplier")

    liquidity_max_outstanding_percent: float = Field(
        default=80, description="Total outstanding principal must be <= percent of pool"
    )
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
    balance: float = Field(default=0)
    last_withdrawal_at: Optional[datetime] = None

    product_id: Optional[int] = Field(default=None, foreign_key="savingsproduct.id")
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    product: Optional["SavingsProduct"] = Relationship(back_populates="accounts")
    transactions: List["Transaction"] = Relationship(back_populates="account")
    group: Optional["Group"] = Relationship(back_populates="accounts")
    user: Optional["User"] = Relationship()



class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    amount: float
    type: TransactionType
    status: TransactionStatus = Field(default=TransactionStatus.PENDING)
    description: Optional[str] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    account: "Account" = Relationship(back_populates="transactions")


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

    principal: float
    term_months: int = Field(default=1)
    repayment_frequency: RepaymentFrequency = Field(default=RepaymentFrequency.MONTHLY)
    interest_rate_percent: Optional[float] = None

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

    principal: float
    interest_rate_percent: float
    admin_fee_percent: float = Field(default=0)

    term_months: int = Field(default=1)
    repayment_frequency: RepaymentFrequency = Field(default=RepaymentFrequency.MONTHLY)

    outstanding_principal: float
    outstanding_interest: float = Field(default=0)
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
    principal_due: float
    interest_due: float
    status: InstallmentStatus = Field(default=InstallmentStatus.DUE)
    paid_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    loan: "Loan" = Relationship(back_populates="installments")


class GroupFee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    amount: float
    description: str = Field(default="Administration fee")
    created_at: datetime = Field(default_factory=datetime.utcnow)



class InterestAccrual(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    amount: float
    applied_on: datetime = Field(default_factory=datetime.utcnow)
    period_start: datetime
    period_end: datetime
    annual_rate: float
    custom_fields: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    account: "Account" = Relationship()
