export type TransactionType =
  | "deposit"
  | "withdrawal"
  | "loan_disbursement"
  | "loan_repayment"
  | "interest"
  | "fee";

export type TransactionStatus = "pending" | "completed" | "failed";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: number;
  email: string;
  full_name?: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavingsProduct {
  id: number;
  name: string;
  description?: string;
  interest_rate: number;
  compounding_days: number;
  min_balance: number;
  custom_fields: Record<string, any>;
}

export interface Account {
  id: number;
  name: string;
  email?: string;
  group_name?: string;
  group_id?: number;
  user_id?: number;
  product_id?: number;
  balance: number;
  last_withdrawal_at?: string | null;
  custom_fields: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface AccountPayload {
  name: string;
  email?: string;
  group_name?: string;
  group_id?: number;
  product_id?: number;
  initial_deposit?: number;
  custom_fields?: Record<string, any>;
}

export type PaymentChannel = "mobile_money" | "card" | "bank";

/** lipila = prompt the member's handset; cash = admin attests it was handed
 *  over; defer = record it as owed and collect later. */
export type ContributionMethod = "lipila" | "cash" | "defer";

export interface Transaction {
  id: number;
  account_id: number;
  amount: number;
  type: TransactionType;
  status: TransactionStatus;
  description?: string;
  custom_fields: Record<string, any>;
  created_at: string;
  provider?: string | null;
  provider_reference?: string | null;
  provider_channel?: PaymentChannel | null;
  /** Lipila's own status: pending, succeeded, failed, expired, needs_review… */
  provider_status?: string | null;
  /** Only on a card collection — send the payer here to authorise. */
  card_redirect_url?: string | null;
}

export interface TransactionPayload {
  account_id: number;
  amount: number;
  type: TransactionType;
  description?: string;
  status?: TransactionStatus;
  custom_fields?: Record<string, any>;
  use_lipila?: boolean;
  channel?: PaymentChannel;
  phone_number?: string;
}

export interface DashboardStats {
  member_count: number;
  total_balance: number;
  pending_transactions: number;
}

export type MembershipRole = "admin" | "member";

export interface Group {
  id: number;
  name: string;
  terms: string;
  created_at: string;
  updated_at: string;
}

export interface GroupSettings {
  group_id: number;
  min_monthly_contribution: number;
  admin_fee_percent: number;
  loan_interest_percent: number;
  enforce_loan_limit: boolean;
  loan_limit_multiplier: number;
  liquidity_max_outstanding_percent: number;
  min_term_months: number;
  max_term_months: number;
  max_active_loans_per_member: number;
  cooldown_days_after_settlement: number;
  constitution_locked_at?: string | null;
  withdrawal_cycle_days: number;
  allow_advance_contribution: boolean;
  custom_fields: Record<string, any>;
}

export interface GroupWithSettings extends Group {
  settings: GroupSettings;
}

export interface GroupCreatePayload {
  name: string;
  terms?: string;
}

export interface GroupSettingsUpdatePayload {
  min_monthly_contribution?: number;
  admin_fee_percent?: number;
  loan_interest_percent?: number;
  enforce_loan_limit?: boolean;
  loan_limit_multiplier?: number;
  liquidity_max_outstanding_percent?: number;
  min_term_months?: number;
  max_term_months?: number;
  max_active_loans_per_member?: number;
  cooldown_days_after_settlement?: number;
  withdrawal_cycle_days?: number;
  allow_advance_contribution?: boolean;
  custom_fields?: Record<string, any>;
}

export interface Membership {
  id: number;
  group_id: number;
  user_id: number;
  account_id?: number | null;
  role: MembershipRole;
  accepted_terms_at?: string | null;
  joined_at: string;
  is_active: boolean;
}

export interface MemberInvitePayload {
  email: string;
  full_name?: string;
  password: string;
  name: string;
  /** Mobile money number, kept on the account for later collections. */
  phone_number?: string;
  min_initial_deposit?: number;
  /** How the initial contribution is settled. */
  initial_contribution_method?: ContributionMethod;
  /** Why cash is being banked on the member's word. Required for "cash". */
  cash_reason?: string;
  custom_fields?: Record<string, any>;
}

export interface MemberPayment {
  transaction_id: number;
  amount: number;
  status: TransactionStatus;
  provider_status?: string | null;
  provider_reference?: string | null;
  card_redirect_url?: string | null;
  /** True when this prompt was already waiting on the member's handset — the
   *  server returned the live one instead of sending a second. */
  already_pending?: boolean;
}

export interface MemberInviteResponse {
  membership: Membership;
  /** Set when a collection was started — the member approves on their handset. */
  payment?: MemberPayment | null;
  /** Set when a contribution is owed but has not been requested yet. */
  initial_contribution_due?: number | null;
}

export interface MemberContributionPayload {
  amount?: number;
  phone_number?: string;
  channel?: PaymentChannel;
  method?: ContributionMethod;
  cash_reason?: string;
}

export type RepaymentFrequency = "weekly" | "monthly";
export type LoanStatus = "active" | "closed";
export type LoanRequestStatus = "requested" | "queued" | "approved" | "rejected" | "canceled";

export interface Loan {
  id: number;
  group_id: number;
  borrower_account_id: number;
  principal: number;
  interest_rate_percent: number;
  admin_fee_percent: number;
  term_months: number;
  repayment_frequency: RepaymentFrequency;
  outstanding_principal: number;
  outstanding_interest: number;
  status: LoanStatus;
  created_at: string;
  disbursed_at: string;
  closed_at?: string | null;
  custom_fields: Record<string, any>;
}

export interface LoanCreatePayload {
  borrower_account_id: number;
  principal: number;
  term_months?: number;
  repayment_frequency?: RepaymentFrequency;
  interest_rate_percent?: number;
  description?: string;
}

export type InstallmentStatus = "due" | "paid";

export interface LoanInstallment {
  id: number;
  loan_id: number;
  sequence: number;
  due_date: string;
  principal_due: number;
  interest_due: number;
  status: InstallmentStatus;
  paid_at?: string | null;
}

export interface LoanRepaymentPayload {
  amount: number;
  interest_component?: number;
  principal_component?: number;
  description?: string;
}

export interface MemberSummary {
  group_id?: number | null;
  account?: Account | null;
  savings_balance: number;
  interest_earned: number;
  loan_outstanding: number;
  active_loan_count: number;
  next_withdrawal_at?: string | null;
  days_until_withdrawal?: number | null;
  next_interest_accrual_at?: string | null;
  days_until_interest_accrual?: number | null;
}

export interface LoanBoardItem {
  id: number;
  group_id: number;
  borrower_account_id: number;
  borrower_name: string;
  principal: number;
  interest_rate_percent: number;
  admin_fee_percent: number;
  outstanding_principal: number;
  outstanding_interest: number;
  status: LoanStatus;
  disbursed_at: string;
  next_due_date?: string | null;
}

export interface MemberLoanForecast {
  loan_id: number;
  borrower_name: string;
  outstanding_interest: number;
  admin_fee_percent: number;
  distributable_interest: number;
  my_share_percent: number;
  my_expected_interest: number;
}

export interface MemberForecast {
  group_id?: number | null;
  my_net_contribution: number;
  group_total_contributions: number;
  my_share_percent: number;
  loans: MemberLoanForecast[];
}

export interface GroupContributionItem {
  account_id: number;
  member_name: string;
  net_contribution: number;
  share_percent: number;
}

export interface LoanRequestCreatePayload {
  principal: number;
  term_months?: number;
  repayment_frequency?: RepaymentFrequency;
  description?: string;
}

export interface LoanRequest {
  id: number;
  group_id: number;
  borrower_account_id: number;
  requester_user_id: number;
  principal: number;
  term_months: number;
  repayment_frequency: RepaymentFrequency;
  interest_rate_percent?: number | null;
  status: LoanRequestStatus;
  description?: string | null;
  decision_reason?: string | null;
  decided_by_user_id?: number | null;
  decided_at?: string | null;
  created_at: string;
  custom_fields: Record<string, any>;
}

export interface LoanRequestDecisionPayload {
  decision: "approve" | "reject";
  decision_reason?: string;
  interest_rate_percent?: number;
}

export interface InterestPreview {
  account_id: number;
  projected_amount: number;
  starts_on: string;
  ends_on: string;
  annual_rate: number;
}

export interface InterestRequest {
  account_id: number;
  start: string;
  end: string;
}

/** A payment that will not resolve itself: either the provider said something
 *  we could not trust (`needs_review`), or nothing came back at all. */
export interface StuckPayment {
  transaction_id: number;
  account_id: number;
  account_name: string;
  amount: number;
  type: TransactionType;
  provider?: string | null;
  provider_status?: string | null;
  provider_reference?: string | null;
  created_at: string;
  last_provider_sync_at?: string | null;
  minutes_waiting: number;
  reason: "needs_review" | "no_confirmation";
}

/** A verified webhook that could not be matched to any transaction — the
 *  provider talking about money this system cannot place. */
export interface StuckEvent {
  event_id: number;
  provider: string;
  webhook_id: string;
  provider_reference?: string | null;
  created_at: string;
  payload: Record<string, any>;
}

/** An account whose stored balance its ledger entries do not add up to. */
export interface BalanceDiscrepancy {
  account_id: number;
  account_name: string;
  stored_balance: number;
  derived_balance: number;
  /** Positive when the balance claims more money than the entries do. */
  difference: number;
  transaction_count: number;
}

export interface AttentionReport {
  stuck_payments: StuckPayment[];
  dead_letter_events: StuckEvent[];
  balance_discrepancies: BalanceDiscrepancy[];
  negative_balances: BalanceDiscrepancy[];
  accounts_checked: number;
  generated_at: string;
}

/** One hand-made balance change, and who made it. */
export interface AuditEntry {
  id: number;
  actor_user_id?: number | null;
  actor_email?: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  reason?: string | null;
  before: Record<string, any>;
  after: Record<string, any>;
  created_at: string;
}
