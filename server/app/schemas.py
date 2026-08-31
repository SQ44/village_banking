from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Dict, Optional, Literal

from pydantic import BaseModel, BeforeValidator, Field as PydanticField, PlainSerializer
from sqlmodel import SQLModel

from .money import money, rate

# Money crossing the API boundary.
#
# `BeforeValidator` is where a float stops. Whatever a client sends — 300,
# "300.00", or the 300.30000000000007 that JavaScript produces when it adds
# 300.1 and 200.2 — becomes an exact 2dp Decimal, rounded half up, before any
# endpoint sees it. Nothing downstream has to remember to do that.
#
# On the way out amounts are serialised as JSON numbers rather than strings, so
# the existing TypeScript client keeps working. That is safe because the wire is
# display-only: every value crossing it has already been quantized to the
# ngwee, and anything echoed back is quantized again on the way in. The
# exactness that matters is in the ledger, not the transport.
Money = Annotated[
    Decimal,
    BeforeValidator(money),
    PlainSerializer(float, return_type=float, when_used="json"),
]
Rate = Annotated[
    Decimal,
    BeforeValidator(rate),
    PlainSerializer(float, return_type=float, when_used="json"),
]

from .models import (
    InstallmentStatus,
    LoanStatus,
    LoanRequestStatus,
    MembershipRole,
    PaymentChannel,
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
    initial_deposit: Money = 0


class AccountUpdate(AccountBase):
    balance: Optional[Money] = None
    # Required when `balance` is set by hand — see `update_account`.
    reason: Optional[str] = None


class AccountRead(AccountBase):
    id: int
    user_id: Optional[int] = None
    balance: Money
    last_withdrawal_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SavingsProductBase(MetadataMixin):
    name: str
    description: Optional[str] = None
    interest_rate: Rate
    compounding_days: int = 30
    min_balance: Money = 0


class SavingsProductCreate(SavingsProductBase):
    pass


class SavingsProductRead(SavingsProductBase):
    id: int


class TransactionBase(MetadataMixin):
    account_id: int
    amount: Money
    type: TransactionType
    description: Optional[str] = None


class TransactionCreate(TransactionBase):
    status: TransactionStatus = TransactionStatus.PENDING
    # Route this transaction through Lipila. A collection is then held pending
    # until Lipila confirms it, whatever `status` asked for.
    use_lipila: bool = False
    channel: PaymentChannel = PaymentChannel.MOBILE_MONEY
    phone_number: Optional[str] = None


class TransactionRead(TransactionBase):
    id: int
    status: TransactionStatus
    created_at: datetime
    provider: Optional[str] = None
    provider_reference: Optional[str] = None
    provider_channel: Optional[PaymentChannel] = None
    provider_status: Optional[str] = None
    # Present only for a card collection: where to send the payer to authorise.
    card_redirect_url: Optional[str] = None


class TransactionStatusUpdate(SQLModel):
    status: TransactionStatus
    # Required by the endpoint. A hand-made balance change with no stated reason
    # is exactly what the audit log exists to prevent, so "who" is not enough.
    reason: Optional[str] = None


class InterestPreview(SQLModel):
    account_id: int
    projected_amount: Money
    starts_on: datetime
    ends_on: datetime
    annual_rate: Rate


class InterestApplyRequest(SQLModel):
    account_id: int
    start: datetime
    end: datetime


class DashboardStats(BaseModel):
    member_count: int
    total_balance: Money
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
    min_monthly_contribution: Optional[Money] = None
    admin_fee_percent: Optional[Rate] = None
    loan_interest_percent: Optional[Rate] = None
    enforce_loan_limit: Optional[bool] = None
    loan_limit_multiplier: Optional[Rate] = None
    liquidity_max_outstanding_percent: Optional[Rate] = None
    min_term_months: Optional[int] = None
    max_term_months: Optional[int] = None
    max_active_loans_per_member: Optional[int] = None
    cooldown_days_after_settlement: Optional[int] = None
    withdrawal_cycle_days: Optional[int] = None
    allow_advance_contribution: Optional[bool] = None
    custom_fields: Optional[Dict[str, Any]] = None


class GroupSettingsRead(SQLModel):
    group_id: int
    min_monthly_contribution: Money
    admin_fee_percent: Rate
    loan_interest_percent: Rate
    enforce_loan_limit: bool
    loan_limit_multiplier: Rate
    liquidity_max_outstanding_percent: Rate
    min_term_months: int
    max_term_months: int
    max_active_loans_per_member: int
    cooldown_days_after_settlement: int
    constitution_locked_at: Optional[datetime] = None
    withdrawal_cycle_days: int
    allow_advance_contribution: bool
    custom_fields: Dict[str, Any]


class GroupWithSettings(GroupRead):
    settings: GroupSettingsRead


class ContributionMethod(str, Enum):
    """How an initial contribution is settled."""

    # Ask Lipila for it; the member approves on their handset.
    LIPILA = "lipila"
    # Handed over in person. An admin attests to it, so it is banked at once and
    # written to the audit log with who said so and why.
    CASH = "cash"
    # Not settled yet. Recorded as owed and collected whenever they are ready.
    DEFER = "defer"


class MemberInvite(SQLModel):
    email: str
    full_name: Optional[str] = None
    password: str
    name: str
    # The member's mobile money number. Kept on the account so any later
    # collection can default to it instead of asking again.
    phone_number: Optional[str] = None
    min_initial_deposit: Money = 0
    # How to settle the initial contribution. Defaults to recording it as owed.
    initial_contribution_method: ContributionMethod = ContributionMethod.DEFER
    # Why the cash is being banked on the member's word. Required for CASH,
    # because a balance that moves without a payment behind it needs a reason
    # on the record.
    cash_reason: Optional[str] = None
    custom_fields: Dict[str, Any] = PydanticField(default_factory=dict)


class MemberPayment(SQLModel):
    """The collection started for a member, if one was."""

    transaction_id: int
    amount: Money
    status: TransactionStatus
    provider_status: Optional[str] = None
    provider_reference: Optional[str] = None
    card_redirect_url: Optional[str] = None
    # True when this is a prompt that was already waiting on the member's
    # handset rather than a new one. The caller tells the operator so, instead
    # of implying a second prompt was sent.
    already_pending: bool = False


class MemberInviteResponse(SQLModel):
    membership: "MembershipRead"
    # Present when a collection was started. The member approves it on their
    # handset; the balance moves only once Lipila confirms.
    payment: Optional[MemberPayment] = None
    # Set when an initial contribution is owed but not yet requested.
    initial_contribution_due: Optional[Money] = None


class MemberContributionRequest(SQLModel):
    """Collect a contribution from a member who is ready to pay."""

    amount: Optional[Money] = None
    phone_number: Optional[str] = None
    channel: PaymentChannel = PaymentChannel.MOBILE_MONEY
    method: ContributionMethod = ContributionMethod.LIPILA
    cash_reason: Optional[str] = None


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
    principal: Money
    term_months: int = 1
    repayment_frequency: RepaymentFrequency = RepaymentFrequency.MONTHLY
    interest_rate_percent: Optional[Rate] = None
    description: Optional[str] = None


class LoanRead(SQLModel):
    id: int
    group_id: int
    borrower_account_id: int
    principal: Money
    interest_rate_percent: Rate
    admin_fee_percent: Rate
    term_months: int
    repayment_frequency: RepaymentFrequency
    outstanding_principal: Money
    outstanding_interest: Money
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
    principal_due: Money
    interest_due: Money
    status: InstallmentStatus
    paid_at: Optional[datetime]


class LoanRepaymentRequest(SQLModel):
    amount: Money
    interest_component: Optional[Money] = None
    principal_component: Optional[Money] = None
    description: Optional[str] = None


class MemberSummary(SQLModel):
    group_id: Optional[int] = None
    account: Optional[AccountRead] = None
    savings_balance: Money = 0
    interest_earned: Money = 0
    loan_outstanding: Money = 0
    active_loan_count: int = 0
    next_withdrawal_at: Optional[datetime] = None
    days_until_withdrawal: Optional[int] = None
    next_interest_accrual_at: Optional[datetime] = None
    days_until_interest_accrual: Optional[int] = None


class LoanBoardItem(SQLModel):
    id: int
    group_id: int
    borrower_account_id: int
    borrower_name: str
    principal: Money
    interest_rate_percent: Rate
    admin_fee_percent: Rate
    outstanding_principal: Money
    outstanding_interest: Money
    status: LoanStatus
    disbursed_at: datetime
    next_due_date: Optional[datetime] = None


class MemberLoanForecast(SQLModel):
    loan_id: int
    borrower_name: str
    outstanding_interest: Money
    admin_fee_percent: Rate
    distributable_interest: Money
    my_share_percent: Rate
    my_expected_interest: Money


class MemberForecast(SQLModel):
    group_id: Optional[int] = None
    my_net_contribution: Money
    group_total_contributions: Money
    my_share_percent: Rate
    loans: list[MemberLoanForecast] = []


class MeContext(SQLModel):
    membership: Optional[MembershipRead] = None
    group: Optional[GroupWithSettings] = None


class GroupContributionItem(SQLModel):
    account_id: int
    member_name: str
    net_contribution: Money
    share_percent: Rate


class LoanRequestCreate(SQLModel):
    principal: Money
    term_months: int = 1
    repayment_frequency: RepaymentFrequency = RepaymentFrequency.MONTHLY
    description: Optional[str] = None


class LoanRequestRead(SQLModel):
    id: int
    group_id: int
    borrower_account_id: int
    requester_user_id: int
    principal: Money
    term_months: int
    repayment_frequency: RepaymentFrequency
    interest_rate_percent: Optional[Rate] = None
    status: LoanRequestStatus
    description: Optional[str] = None
    decision_reason: Optional[str] = None
    decided_by_user_id: Optional[int] = None
    decided_at: Optional[datetime] = None
    created_at: datetime
    custom_fields: Dict[str, Any]


class LoanRequestDecision(SQLModel):
    decision: Literal["approve", "reject"]
    decision_reason: Optional[str] = None
    interest_rate_percent: Optional[Rate] = None


# ----------------------------------------------------------------------
# Operations: what needs a person, and who has moved money by hand.
# ----------------------------------------------------------------------


class StuckPaymentRead(SQLModel):
    """A payment that will not resolve itself."""

    transaction_id: int
    account_id: int
    account_name: str
    amount: Money
    type: TransactionType
    provider: Optional[str] = None
    provider_status: Optional[str] = None
    provider_reference: Optional[str] = None
    created_at: datetime
    last_provider_sync_at: Optional[datetime] = None
    minutes_waiting: int
    # "needs_review" (the provider's answer could not be trusted) or
    # "no_confirmation" (nothing came back at all).
    reason: str


class StuckEventRead(SQLModel):
    """A verified webhook that could not be matched to a transaction."""

    event_id: int
    provider: str
    webhook_id: str
    provider_reference: Optional[str] = None
    created_at: datetime
    payload: Dict[str, Any] = PydanticField(default_factory=dict)


class BalanceDiscrepancyRead(SQLModel):
    """An account whose stored balance the ledger entries do not explain."""

    account_id: int
    account_name: str
    stored_balance: Money
    derived_balance: Money
    # Positive when the stored balance claims more money than the entries do.
    difference: Money
    transaction_count: int


class AttentionReport(SQLModel):
    stuck_payments: list[StuckPaymentRead] = []
    dead_letter_events: list[StuckEventRead] = []
    balance_discrepancies: list[BalanceDiscrepancyRead] = []
    negative_balances: list[BalanceDiscrepancyRead] = []
    accounts_checked: int = 0
    # Every journal entry's debits equal its credits.
    books_balanced: bool = True
    # What the books say members are owed equals what their accounts say. False
    # means a balance moved without an entry behind it.
    control_total_matches: bool = True
    generated_at: datetime


class AuditEntryRead(SQLModel):
    id: int
    actor_user_id: Optional[int] = None
    actor_email: Optional[str] = None
    action: str
    entity_type: str
    entity_id: str
    reason: Optional[str] = None
    before: Dict[str, Any] = PydanticField(default_factory=dict)
    after: Dict[str, Any] = PydanticField(default_factory=dict)
    created_at: datetime


class TrialBalanceRow(SQLModel):
    account_code: str
    balance: Decimal


class TrialBalanceReport(SQLModel):
    """Where the group's money is, and whether the books agree with themselves."""

    accounts: list[TrialBalanceRow] = []
    # Every entry's debits equal its credits.
    balanced: bool = True
    # What the books say members are owed equals what their accounts say.
    control_total_matches: bool = True
    # Principal still with borrowers. Read from the loans rather than the
    # journal: under the current lending model a borrower draws on their own
    # savings, so no receivable is booked and the loans are the only truth.
    loans_outstanding: Decimal = Decimal("0.00")
    generated_at: datetime


class JournalLineRead(SQLModel):
    account_code: str
    debit: Decimal
    credit: Decimal
    account_id: Optional[int] = None


class JournalEntryRead(SQLModel):
    id: int
    reference_type: str
    reference_id: str
    group_id: Optional[int] = None
    description: Optional[str] = None
    created_at: datetime
    lines: list[JournalLineRead] = []


class StatementLineRead(SQLModel):
    """One movement on a member's statement."""

    transaction_id: int
    created_at: datetime
    description: Optional[str] = None
    debit: Decimal
    credit: Decimal
    running_balance: Decimal
