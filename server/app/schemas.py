from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field as PydanticField
from sqlmodel import SQLModel

from .models import (
    InstallmentStatus,
    LoanStatus,
    MembershipRole,
    RepaymentFrequency,
    TransactionStatus,
    TransactionType,
)


class MetadataMixin(SQLModel):
    custom_fields: Dict[str, Any] = PydanticField(default_factory=dict)


class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(SQLModel):
    sub: Optional[str] = None


class UserBase(SQLModel):
    email: str
    full_name: Optional[str] = None
    role: str = "operator"


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserLogin(SQLModel):
    email: str
    password: str


class AccountBase(MetadataMixin):
    name: str
    email: Optional[str] = None
    group_name: Optional[str] = None
    group_id: Optional[int] = None
    product_id: Optional[int] = None


class AccountCreate(AccountBase):
    initial_deposit: float = 0


class AccountUpdate(AccountBase):
    balance: Optional[float] = None


class AccountRead(AccountBase):
    id: int
    user_id: Optional[int] = None
    balance: float
    last_withdrawal_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SavingsProductBase(MetadataMixin):
    name: str
    description: Optional[str] = None
    interest_rate: float
    compounding_days: int = 30
    min_balance: float = 0


class SavingsProductCreate(SavingsProductBase):
    pass


class SavingsProductRead(SavingsProductBase):
    id: int


class TransactionBase(MetadataMixin):
    account_id: int
    amount: float
    type: TransactionType
    description: Optional[str] = None


class TransactionCreate(TransactionBase):
    status: TransactionStatus = TransactionStatus.PENDING
    use_lenco: bool = False


class TransactionRead(TransactionBase):
    id: int
    status: TransactionStatus
    created_at: datetime


class TransactionStatusUpdate(SQLModel):
    status: TransactionStatus


class InterestPreview(SQLModel):
    account_id: int
    projected_amount: float
    starts_on: datetime
    ends_on: datetime
    annual_rate: float


class InterestApplyRequest(SQLModel):
    account_id: int
    start: datetime
    end: datetime


class DashboardStats(BaseModel):
    member_count: int
    total_balance: float
    pending_transactions: int


class GroupCreate(SQLModel):
    name: str
    terms: str = ""


class GroupRead(SQLModel):
    id: int
    name: str
    terms: str
    created_at: datetime
    updated_at: datetime


class GroupSettingsUpdate(SQLModel):
    min_monthly_contribution: Optional[float] = None
    admin_fee_percent: Optional[float] = None
    loan_interest_percent: Optional[float] = None
    enforce_loan_limit: Optional[bool] = None
    loan_limit_multiplier: Optional[float] = None
    withdrawal_cycle_days: Optional[int] = None
    allow_advance_contribution: Optional[bool] = None
    custom_fields: Optional[Dict[str, Any]] = None


class GroupSettingsRead(SQLModel):
    group_id: int
    min_monthly_contribution: float
    admin_fee_percent: float
    loan_interest_percent: float
    enforce_loan_limit: bool
    loan_limit_multiplier: float
    withdrawal_cycle_days: int
    allow_advance_contribution: bool
    custom_fields: Dict[str, Any]


class GroupWithSettings(GroupRead):
    settings: GroupSettingsRead


class MemberInvite(SQLModel):
    email: str
    full_name: Optional[str] = None
    password: str
    name: str
    min_initial_deposit: float = 0
    custom_fields: Dict[str, Any] = PydanticField(default_factory=dict)


class MembershipRead(SQLModel):
    id: int
    group_id: int
    user_id: int
    account_id: Optional[int]
    role: MembershipRole
    accepted_terms_at: Optional[datetime]
    joined_at: datetime
    is_active: bool


class AcceptTermsRequest(SQLModel):
    accepted: bool = True


class LoanCreate(SQLModel):
    borrower_account_id: int
    principal: float
    term_months: int = 1
    repayment_frequency: RepaymentFrequency = RepaymentFrequency.MONTHLY
    interest_rate_percent: Optional[float] = None
    description: Optional[str] = None


class LoanRead(SQLModel):
    id: int
    group_id: int
    borrower_account_id: int
    principal: float
    interest_rate_percent: float
    admin_fee_percent: float
    term_months: int
    repayment_frequency: RepaymentFrequency
    outstanding_principal: float
    outstanding_interest: float
    status: LoanStatus
    created_at: datetime
    disbursed_at: datetime
    closed_at: Optional[datetime]
    custom_fields: Dict[str, Any]


class LoanInstallmentRead(SQLModel):
    id: int
    loan_id: int
    sequence: int
    due_date: datetime
    principal_due: float
    interest_due: float
    status: InstallmentStatus
    paid_at: Optional[datetime]


class LoanRepaymentRequest(SQLModel):
    amount: float
    interest_component: Optional[float] = None
    principal_component: Optional[float] = None
    description: Optional[str] = None


class MemberSummary(SQLModel):
    group_id: Optional[int] = None
    account: Optional[AccountRead] = None
    savings_balance: float = 0
    interest_earned: float = 0
    loan_outstanding: float = 0
    active_loan_count: int = 0


class MeContext(SQLModel):
    membership: Optional[MembershipRead] = None
    group: Optional[GroupWithSettings] = None
