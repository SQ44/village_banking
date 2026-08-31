import { createContext, useContext } from "react";

import type {
  Account,
  DashboardStats,
  Group,
  GroupContributionItem,
  GroupPerformance,
  GroupSettingsUpdatePayload,
  GroupWithSettings,
  Loan,
  LoanRequest,
  Membership,
} from "../types";

export type AdminContextValue = {
  busy: boolean;
  groups: Group[];
  selectedGroupId: number | "";
  group: GroupWithSettings | null;
  members: Account[];
  memberships: Membership[];
  contributions: GroupContributionItem[];
  dashboard: DashboardStats | null;
  performance: GroupPerformance | null;
  loans: Loan[];
  requests: LoanRequest[];
  constitutionLocked: boolean;
  refresh: (groupId?: number) => Promise<void>;
  openInvite: () => void;
  openManualLoan: () => void;
  openCreateGroup: () => void;
  saveSettings: (payload: GroupSettingsUpdatePayload) => Promise<void>;
  lockConstitution: () => Promise<void>;
};

export const AdminContext = createContext<AdminContextValue | null>(null);

export function useAdmin() {
  const ctx = useContext(AdminContext);
  if (!ctx) throw new Error("useAdmin must be used inside AdminLayout");
  return ctx;
}

