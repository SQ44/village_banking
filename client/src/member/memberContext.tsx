import { createContext, useContext } from "react";

import type {
  GroupContributionItem,
  GroupWithSettings,
  Loan,
  LoanBoardItem,
  LoanRequest,
  MemberForecast,
  MemberSummary,
  Membership,
  Transaction,
} from "../types";

export type MemberContextValue = {
  onError: (msg: string) => void;
  busy: boolean;
  group: GroupWithSettings | null;
  membership: Membership | null;
  membershipAccepted: boolean;
  constitutionLocked: boolean;
  summary: MemberSummary | null;
  forecast: MemberForecast | null;
  transactions: Transaction[];
  myLoans: Loan[];
  groupLoans: LoanBoardItem[];
  contributions: GroupContributionItem[];
  requests: LoanRequest[];
  refresh: () => Promise<void>;
  openRequest: () => void;
  openRepay: (loanId: number) => void;
};

export const MemberContext = createContext<MemberContextValue | null>(null);

export function useMember() {
  const ctx = useContext(MemberContext);
  if (!ctx) throw new Error("useMember must be used inside MemberLayout");
  return ctx;
}
