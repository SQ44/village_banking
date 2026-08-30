import type {
  Account,
  AccountPayload,
  DashboardStats,
  Group,
  GroupCreatePayload,
  GroupSettings,
  GroupSettingsUpdatePayload,
  GroupWithSettings,
  GroupContributionItem,
  InterestPreview,
  InterestRequest,
  Loan,
  LoanCreatePayload,
  LoanInstallment,
  LoanRepaymentPayload,
  LoanRequest,
  LoanRequestCreatePayload,
  LoanRequestDecisionPayload,
  LoanBoardItem,
  MemberContributionPayload,
  MemberInvitePayload,
  MemberInviteResponse,
  MemberPayment,
  MemberForecast,
  MemberSummary,
  Membership,
  SavingsProduct,
  TokenResponse,
  Transaction,
  TransactionPayload,
  User,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
let authToken: string | null = null;

const isFormBody = (body: BodyInit | null | undefined): boolean => {
  if (!body) return false;
  const hasFormData = typeof FormData !== "undefined" && body instanceof FormData;
  const hasSearchParams = typeof URLSearchParams !== "undefined" && body instanceof URLSearchParams;
  return hasFormData || hasSearchParams;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  if (!headers.has("Content-Type") && options.body && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  if (!headers.has("Content-Type") && options.body && isFormBody(options.body)) {
    // Allow fetch to infer the proper multipart/form encoding
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as any;
      const message = payload?.detail ?? payload?.message ?? JSON.stringify(payload);
      throw new Error(message || "Request failed");
    }
    const message = await response.text();
    throw new Error(message || "Request failed");
  }
  return (await response.json()) as T;
}

export const Api = {
  setToken: (token: string | null) => {
    authToken = token;
  },
  login: (email: string, password: string) => {
    const payload = new URLSearchParams();
    payload.set("username", email);
    payload.set("password", password);
    return request<TokenResponse>("/auth/login", {
      method: "POST",
      body: payload,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
  },
  getCurrentUser: () => request<User>("/auth/me"),
  getAccounts: () => request<Account[]>("/accounts"),
  createAccount: (payload: AccountPayload) =>
    request<Account>("/accounts", { method: "POST", body: JSON.stringify(payload) }),
  getTransactions: (accountId?: number) => {
    const query = accountId ? `?account_id=${accountId}` : "";
    return request<Transaction[]>(`/transactions${query}`);
  },
  createTransaction: (payload: TransactionPayload) =>
    request<Transaction>("/transactions", { method: "POST", body: JSON.stringify(payload) }),
  /** Re-read a Lipila payment from the provider — used after a card return, or
   *  while a member is approving a mobile money prompt on their handset. */
  refreshTransaction: (transactionId: number) =>
    request<Transaction>(`/transactions/${transactionId}/refresh`, { method: "POST" }),
  getProducts: () => request<SavingsProduct[]>("/products"),
  createProduct: (payload: Omit<SavingsProduct, "id">) =>
    request<SavingsProduct>("/products", { method: "POST", body: JSON.stringify(payload) }),
  getDashboard: () => request<DashboardStats>("/dashboard/summary"),
  getDashboardForGroup: (groupId: number) => request<DashboardStats>(`/dashboard/summary?group_id=${groupId}`),
  previewInterest: (payload: InterestRequest) =>
    request<InterestPreview>("/interest/preview", { method: "POST", body: JSON.stringify(payload) }),
  applyInterest: (payload: InterestRequest) =>
    request<Transaction>("/interest/apply", { method: "POST", body: JSON.stringify(payload) }),

  getGroups: () => request<Group[]>("/groups"),
  createGroup: (payload: GroupCreatePayload) => request<GroupWithSettings>("/groups", { method: "POST", body: JSON.stringify(payload) }),
  getGroup: (groupId: number) => request<GroupWithSettings>(`/groups/${groupId}`),
  updateGroupSettings: (groupId: number, payload: GroupSettingsUpdatePayload) =>
    request<GroupSettings>(`/groups/${groupId}/settings`, { method: "PATCH", body: JSON.stringify(payload) }),
  lockGroupConstitution: (groupId: number) =>
    request<GroupSettings>(`/groups/${groupId}/constitution/lock`, { method: "POST" }),
  getGroupMembers: (groupId: number) => request<Membership[]>(`/groups/${groupId}/members`),
  addGroupMember: (groupId: number, payload: MemberInvitePayload) =>
    request<MemberInviteResponse>(`/groups/${groupId}/members`, { method: "POST", body: JSON.stringify(payload) }),
  /** Collect from a member who deferred their contribution at sign-up. */
  collectMemberContribution: (groupId: number, accountId: number, payload: MemberContributionPayload) =>
    request<MemberPayment>(`/groups/${groupId}/members/${accountId}/collect`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  acceptGroupTerms: (groupId: number) =>
    request<Membership>(`/groups/${groupId}/accept-terms`, { method: "POST", body: JSON.stringify({ accepted: true }) }),
  getGroupAccounts: (groupId: number) => request<Account[]>(`/groups/${groupId}/accounts`),
  getGroupContributions: (groupId: number) => request<GroupContributionItem[]>(`/groups/${groupId}/contributions`),

  getMeSummary: () => request<MemberSummary>("/me/summary"),
  getMeContext: () => request<{ membership?: Membership; group?: GroupWithSettings }>("/me/context"),
  getMeTransactions: () => request<Transaction[]>("/me/transactions"),
  getMeForecast: () => request<MemberForecast>("/me/forecast"),

  getGroupLoans: (groupId: number) => request<Loan[]>(`/loans/group/${groupId}`),
  getGroupLoanBoard: (groupId: number) => request<LoanBoardItem[]>(`/loans/group/${groupId}/board`),
  createLoan: (groupId: number, payload: LoanCreatePayload) =>
    request<Loan>(`/loans/group/${groupId}`, { method: "POST", body: JSON.stringify(payload) }),
  requestLoan: (groupId: number, payload: LoanRequestCreatePayload) =>
    request<LoanRequest>(`/loans/group/${groupId}/requests`, { method: "POST", body: JSON.stringify(payload) }),
  listLoanRequests: (groupId: number) => request<LoanRequest[]>(`/loans/group/${groupId}/requests`),
  decideLoanRequest: (requestId: number, payload: LoanRequestDecisionPayload) =>
    request<LoanRequest>(`/loans/requests/${requestId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  cancelLoanRequest: (requestId: number) =>
    request<LoanRequest>(`/loans/requests/${requestId}/cancel`, { method: "POST" }),
  getLoanSchedule: (loanId: number) => request<LoanInstallment[]>(`/loans/${loanId}/schedule`),
  repayLoan: (loanId: number, payload: LoanRepaymentPayload) =>
    request<Loan>(`/loans/${loanId}/repay`, { method: "POST", body: JSON.stringify(payload) }),
};
