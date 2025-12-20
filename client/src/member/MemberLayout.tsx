import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ReceiptLongIcon from "@mui/icons-material/ReceiptLong";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import GroupIcon from "@mui/icons-material/Group";
import ChecklistIcon from "@mui/icons-material/Checklist";

import { DataGrid, type GridColDef } from "@mui/x-data-grid";

import { Api } from "../api";
import { ScorecardDialog, type ScorecardItem } from "../components/ScorecardDialog";
import { AppShell, type NavItem } from "../layout/AppShell";
import { StatCard } from "../components/StatCard";
import { StatusChip } from "../components/StatusChip";
import { currency, formatDate, formatDateTime } from "../lib/format";
import type {
  GroupContributionItem,
  GroupWithSettings,
  Loan,
  LoanBoardItem,
  LoanRepaymentPayload,
  LoanRequest,
  LoanRequestCreatePayload,
  MemberForecast,
  MemberSummary,
  Membership,
  Transaction,
  User,
} from "../types";

type MemberContextValue = {
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

const MemberContext = createContext<MemberContextValue | null>(null);

export function useMember() {
  const ctx = useContext(MemberContext);
  if (!ctx) throw new Error("useMember must be used inside MemberLayout");
  return ctx;
}

export function MemberLayout({
  currentUser,
  onLogout,
  onError,
}: {
  currentUser: User;
  onLogout: () => void;
  onError: (msg: string) => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();

  const [summary, setSummary] = useState<MemberSummary | null>(null);
  const [forecast, setForecast] = useState<MemberForecast | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [myLoans, setMyLoans] = useState<Loan[]>([]);
  const [groupLoans, setGroupLoans] = useState<LoanBoardItem[]>([]);
  const [contributions, setContributions] = useState<GroupContributionItem[]>([]);
  const [requests, setRequests] = useState<LoanRequest[]>([]);
  const [group, setGroup] = useState<GroupWithSettings | null>(null);
  const [membership, setMembership] = useState<Membership | null>(null);
  const [membershipAccepted, setMembershipAccepted] = useState(true);
  const [busy, setBusy] = useState(false);

  const [repayOpen, setRepayOpen] = useState(false);
  const [repayLoanId, setRepayLoanId] = useState<number | null>(null);
  const [repayAmount, setRepayAmount] = useState(0);

  const [requestOpen, setRequestOpen] = useState(false);
  const [requestDraft, setRequestDraft] = useState<LoanRequestCreatePayload>({
    principal: 0,
    term_months: 1,
    repayment_frequency: "monthly",
    description: "",
  });

  const constitutionLocked = Boolean(group?.settings?.constitution_locked_at);

  const refresh = async () => {
    setBusy(true);
    try {
      const ctx = await Api.getMeContext();
      setGroup(ctx.group ?? null);
      setMembership(ctx.membership ?? null);
      const accepted = !!ctx.membership?.accepted_terms_at;
      setMembershipAccepted(accepted);

      const [sum, tx] = await Promise.all([Api.getMeSummary(), Api.getMeTransactions()]);
      setSummary(sum);
      setTransactions(tx);

      if (accepted && ctx.group?.id) {
        try {
          setForecast(await Api.getMeForecast());
        } catch {
          setForecast(null);
        }

        const [loans, board, shares, reqs] = await Promise.all([
          Api.getGroupLoans(ctx.group.id),
          Api.getGroupLoanBoard(ctx.group.id).catch(() => []),
          Api.getGroupContributions(ctx.group.id).catch(() => []),
          Api.listLoanRequests(ctx.group.id).catch(() => []),
        ]);
        setMyLoans(loans);
        setGroupLoans(board);
        setContributions(shares);
        setRequests(reqs);
      } else {
        setForecast(null);
        setMyLoans([]);
        setGroupLoans([]);
        setContributions([]);
        setRequests([]);
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load member portal");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (location.pathname === "/member" || location.pathname === "/member/") {
      navigate("/member/overview", { replace: true });
    }
  }, [location.pathname, navigate]);

  const openRequest = () => {
    setRequestDraft({ principal: 0, term_months: 1, repayment_frequency: "monthly", description: "" });
    setRequestOpen(true);
  };

  const openRepay = (loanId: number) => {
    setRepayLoanId(loanId);
    setRepayAmount(0);
    setRepayOpen(true);
  };

  const header = (
    <Box display="flex" flexDirection="column" minWidth={0}>
      <Typography variant="h6" noWrap>
        {group?.name ?? "My Wallet"}
      </Typography>
      <Typography variant="body2" color="text.secondary" noWrap>
        {constitutionLocked ? "Autonomous lending enabled" : "Waiting for constitution lock"}
      </Typography>
    </Box>
  );

  const actions = (
    <>
      <Button variant="contained" disabled={busy || !membershipAccepted || !constitutionLocked || !group?.id} onClick={openRequest}>
        Request loan
      </Button>
    </>
  );

  const navItems: NavItem[] = useMemo(
    () => [
      { to: "/member/overview", label: "Overview", icon: <DashboardIcon /> },
      { to: "/member/transactions", label: "Transactions", icon: <ReceiptLongIcon />, badge: transactions.length },
      { to: "/member/requests", label: "Requests", icon: <ChecklistIcon />, badge: requests.filter((r) => r.status === "requested" || r.status === "queued").length },
      { to: "/member/my-loans", label: "My loans", icon: <CreditCardIcon />, badge: myLoans.filter((l) => l.status === "active").length },
      { to: "/member/group-loans", label: "Group loans", icon: <GroupIcon />, badge: groupLoans.length },
      { to: "/member/shares", label: "Shares", icon: <GroupIcon />, badge: contributions.length },
    ],
    [contributions.length, groupLoans.length, myLoans, requests, transactions.length]
  );

  const ctx: MemberContextValue = {
    onError,
    busy,
    group,
    membership,
    membershipAccepted,
    constitutionLocked,
    summary,
    forecast,
    transactions,
    myLoans,
    groupLoans,
    contributions,
    requests,
    refresh,
    openRequest,
    openRepay,
  };

  return (
    <MemberContext.Provider value={ctx}>
      <AppShell title="Village Banking" user={currentUser} navItems={navItems} header={header} actions={actions} onLogout={onLogout}>
        {!group ? (
          <Alert severity="info">You are not assigned to a group yet.</Alert>
        ) : (
          <>
            {!membershipAccepted && (
              <Alert
                severity="warning"
                sx={{ mb: 2, whiteSpace: "pre-wrap" }}
                action={
                  <Button
                    color="inherit"
                    onClick={async () => {
                      try {
                        await Api.acceptGroupTerms(group.id);
                        await refresh();
                      } catch (err) {
                        onError(err instanceof Error ? err.message : "Failed to accept terms");
                      }
                    }}
                  >
                    Accept terms
                  </Button>
                }
              >
                {group.terms || "No terms configured."}
              </Alert>
            )}

            {!constitutionLocked && (
              <Alert severity="info" sx={{ mb: 2 }}>
                Loan requests open after the group locks the constitution for this cycle.
              </Alert>
            )}

            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={3}>
                <StatCard label="Savings" value={currency(Number(summary?.savings_balance ?? 0))} icon={<DashboardIcon color="action" />} />
              </Grid>
              <Grid item xs={12} md={3}>
                <StatCard label="Interest earned" value={currency(Number(summary?.interest_earned ?? 0))} icon={<DashboardIcon color="action" />} />
              </Grid>
              <Grid item xs={12} md={3}>
                <StatCard label="Outstanding loans" value={currency(Number(summary?.loan_outstanding ?? 0))} icon={<CreditCardIcon color="action" />} />
              </Grid>
              <Grid item xs={12} md={3}>
                <StatCard label="My share (%)" value={`${(forecast?.my_share_percent ?? 0).toFixed(2)}%`} icon={<GroupIcon color="action" />} />
              </Grid>
            </Grid>

            <Outlet />
          </>
        )}

        <Dialog open={repayOpen} onClose={() => setRepayOpen(false)} fullWidth maxWidth="sm">
          <DialogTitle>Repay loan</DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1, mb: 2 }}>
              Repayments are applied to interest first, then principal. Loan interest is distributed to members based on contributions.
            </Typography>
            <TextField label="Amount" type="number" fullWidth value={repayAmount} onChange={(e) => setRepayAmount(Number(e.target.value))} />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setRepayOpen(false)}>Cancel</Button>
            <Button
              variant="contained"
              disabled={!membershipAccepted || !repayLoanId || repayAmount <= 0 || busy}
              onClick={async () => {
                try {
                  const payload: LoanRepaymentPayload = { amount: repayAmount };
                  await Api.repayLoan(repayLoanId!, payload);
                  setRepayOpen(false);
                  await refresh();
                } catch (err) {
                  onError(err instanceof Error ? err.message : "Failed to repay loan");
                }
              }}
            >
              Repay
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog open={requestOpen} onClose={() => setRequestOpen(false)} fullWidth maxWidth="sm">
          <DialogTitle>Request loan</DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1, mb: 2 }}>
              Your request is auto-approved, rejected, or queued based on the group constitution.
            </Typography>
            {!constitutionLocked && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                Constitution is not locked yet for this cycle. Loan requests are disabled.
              </Alert>
            )}
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <TextField label="Principal" type="number" fullWidth value={requestDraft.principal} onChange={(e) => setRequestDraft((p) => ({ ...p, principal: Number(e.target.value) }))} />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField label="Term (months)" type="number" fullWidth value={requestDraft.term_months ?? 1} onChange={(e) => setRequestDraft((p) => ({ ...p, term_months: Number(e.target.value) }))} />
              </Grid>
              <Grid item xs={12} md={6}>
                <FormControl fullWidth>
                  <InputLabel id="repay-frequency-label">Repayment frequency</InputLabel>
                  <Select
                    labelId="repay-frequency-label"
                    label="Repayment frequency"
                    value={requestDraft.repayment_frequency ?? "monthly"}
                    onChange={(e) => setRequestDraft((p) => ({ ...p, repayment_frequency: e.target.value as any }))}
                  >
                    <MenuItem value="weekly">Weekly</MenuItem>
                    <MenuItem value="monthly">Monthly</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12}>
                <TextField label="Description (optional)" fullWidth value={requestDraft.description ?? ""} onChange={(e) => setRequestDraft((p) => ({ ...p, description: e.target.value }))} />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setRequestOpen(false)}>Cancel</Button>
            <Button
              variant="contained"
              disabled={!membershipAccepted || busy || !group?.id || !constitutionLocked || (requestDraft.principal ?? 0) <= 0}
              onClick={async () => {
                try {
                  await Api.requestLoan(group!.id, requestDraft);
                  setRequestOpen(false);
                  await refresh();
                  navigate("/member/requests");
                } catch (err) {
                  onError(err instanceof Error ? err.message : "Failed to request loan");
                }
              }}
            >
              Submit request
            </Button>
          </DialogActions>
        </Dialog>
      </AppShell>
    </MemberContext.Provider>
  );
}

export function MemberOverviewPage() {
  const { group, summary } = useMember();
  if (!group || !summary) return null;
  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Overview
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Alert severity="info">
            Next withdrawal: {summary.next_withdrawal_at ? formatDate(summary.next_withdrawal_at) : "—"}
          </Alert>
        </Grid>
        <Grid item xs={12} md={6}>
          <Alert severity="info">
            Next interest accrual: {summary.next_interest_accrual_at ? formatDate(summary.next_interest_accrual_at) : "—"}
          </Alert>
        </Grid>
      </Grid>
    </Box>
  );
}

export function MemberTransactionsPage() {
  const { busy, transactions } = useMember();
  const columns: GridColDef<Transaction>[] = useMemo(
    () => [
      { field: "created_at", headerName: "Date", width: 180, valueFormatter: (v) => formatDateTime(String(v)) },
      { field: "type", headerName: "Type", width: 160 },
      { field: "amount", headerName: "Amount", width: 140, valueFormatter: (v) => currency(Number(v)) },
      { field: "description", headerName: "Description", flex: 1, minWidth: 220 },
      { field: "status", headerName: "Status", width: 120 },
    ],
    []
  );
  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Transactions
      </Typography>
      <Box height={520}>
        <DataGrid rows={transactions} columns={columns} disableRowSelectionOnClick loading={busy} getRowId={(row) => row.id} pageSizeOptions={[10, 25, 50]} initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }} />
      </Box>
    </Box>
  );
}

export function MemberRequestsPage() {
  const { busy, requests, refresh, constitutionLocked, membershipAccepted, onError } = useMember();
  const [scorecardOpen, setScorecardOpen] = useState(false);
  const [scorecard, setScorecard] = useState<ScorecardItem[] | null>(null);
  const columns: GridColDef<LoanRequest>[] = useMemo(
    () => [
      { field: "id", headerName: "Request", width: 110 },
      { field: "principal", headerName: "Principal", width: 140, valueFormatter: (v) => currency(Number(v)) },
      { field: "term_months", headerName: "Term", width: 100, valueFormatter: (v) => `${Number(v)} mo` },
      { field: "repayment_frequency", headerName: "Frequency", width: 120 },
      { field: "status", headerName: "Status", width: 120, renderCell: ({ value }) => <StatusChip value={String(value)} /> },
      {
        field: "approved_loan_id",
        headerName: "Loan",
        width: 100,
        valueGetter: (_, row) => (row.custom_fields?.approved_loan_id ? `#${row.custom_fields.approved_loan_id}` : ""),
      },
      {
        field: "scorecard",
        headerName: "Scorecard",
        width: 120,
        sortable: false,
        filterable: false,
        renderCell: ({ row }) => {
          const items = row.custom_fields?.scorecard as ScorecardItem[] | undefined;
          if (!items?.length) return null;
          return (
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                setScorecard(items);
                setScorecardOpen(true);
              }}
            >
              View
            </Button>
          );
        },
      },
      { field: "decision_reason", headerName: "Reason", flex: 1, minWidth: 220, valueGetter: (_, row) => row.decision_reason ?? "" },
      { field: "created_at", headerName: "Created", width: 170, valueFormatter: (v) => formatDateTime(String(v)) },
      {
        field: "actions",
        headerName: "",
        width: 140,
        sortable: false,
        filterable: false,
        renderCell: ({ row }) => {
          if (row.status !== "requested" && row.status !== "queued") return null;
          return (
            <Button
              size="small"
              variant="outlined"
              color="error"
              disabled={busy}
              onClick={async () => {
                try {
                  await Api.cancelLoanRequest(row.id);
                  await refresh();
                } catch (err) {
                  onError(err instanceof Error ? err.message : "Failed to cancel request");
                }
              }}
            >
              Cancel
            </Button>
          );
        },
      },
    ],
    [busy, onError, refresh]
  );

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Requests
      </Typography>
      {!constitutionLocked && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Loan requests open after the group locks the constitution for this cycle.
        </Alert>
      )}
      {!membershipAccepted && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Accept group terms before requesting loans.
        </Alert>
      )}
      <Box height={520}>
        <DataGrid rows={requests} columns={columns} disableRowSelectionOnClick loading={busy} getRowId={(row) => row.id} pageSizeOptions={[10, 25, 50]} initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }} />
      </Box>
      <ScorecardDialog open={scorecardOpen} onClose={() => setScorecardOpen(false)} scorecard={scorecard} />
    </Box>
  );
}

export function MemberMyLoansPage() {
  const { busy, myLoans, openRepay, membershipAccepted } = useMember();
  const columns: GridColDef<Loan>[] = useMemo(
    () => [
      { field: "id", headerName: "Loan", width: 90 },
      { field: "principal", headerName: "Principal", width: 140, valueFormatter: (v) => currency(Number(v)) },
      {
        field: "outstanding_principal",
        headerName: "Outstanding",
        width: 160,
        valueGetter: (_, row) => Number(row.outstanding_principal) + Number(row.outstanding_interest),
        valueFormatter: (v) => currency(Number(v)),
      },
      { field: "status", headerName: "Status", width: 120, renderCell: ({ value }) => <StatusChip value={String(value)} /> },
    ],
    []
  );
  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        My loans
      </Typography>
      {!membershipAccepted && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Accept group terms before repaying loans.
        </Alert>
      )}
      <Box height={520}>
        <DataGrid
          rows={myLoans}
          columns={columns}
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          onRowClick={(params) => openRepay(Number(params.id))}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
        />
      </Box>
    </Box>
  );
}

export function MemberGroupLoansPage() {
  const { busy, groupLoans, forecast } = useMember();
  const forecastByLoanId = useMemo(() => {
    const map = new Map<number, number>();
    for (const item of forecast?.loans ?? []) map.set(Number(item.loan_id), Number(item.my_expected_interest ?? 0));
    return map;
  }, [forecast]);
  const columns: GridColDef<LoanBoardItem>[] = useMemo(
    () => [
      { field: "borrower_name", headerName: "Borrower", flex: 1, minWidth: 180 },
      { field: "principal", headerName: "Principal", width: 140, valueFormatter: (v) => currency(Number(v)) },
      {
        field: "outstanding",
        headerName: "Outstanding",
        width: 160,
        valueGetter: (_, row) => Number(row.outstanding_principal) + Number(row.outstanding_interest),
        valueFormatter: (v) => currency(Number(v)),
      },
      { field: "next_due_date", headerName: "Next due", width: 160, valueGetter: (_, row) => row.next_due_date ?? "", valueFormatter: (v) => formatDate(String(v)) },
      {
        field: "my_expected_interest",
        headerName: "My expected interest",
        width: 180,
        valueGetter: (_, row) => forecastByLoanId.get(Number(row.id)) ?? 0,
        valueFormatter: (v) => currency(Number(v)),
      },
      { field: "status", headerName: "Status", width: 120, renderCell: ({ value }) => <StatusChip value={String(value)} /> },
    ],
    [forecastByLoanId]
  );
  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Group loans
      </Typography>
      <Box height={520}>
        <DataGrid rows={groupLoans} columns={columns} disableRowSelectionOnClick loading={busy} getRowId={(row) => row.id} pageSizeOptions={[10, 25, 50]} initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }} />
      </Box>
    </Box>
  );
}

export function MemberSharesPage() {
  const { busy, contributions } = useMember();
  const columns: GridColDef<GroupContributionItem>[] = useMemo(
    () => [
      { field: "member_name", headerName: "Member", flex: 1, minWidth: 180 },
      { field: "net_contribution", headerName: "Net contribution", width: 170, valueFormatter: (v) => currency(Number(v)) },
      { field: "share_percent", headerName: "Share", width: 120, valueFormatter: (v) => `${Number(v).toFixed(2)}%` },
    ],
    []
  );
  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Shares
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Contribution shares are used to split loan interest after the admin fee.
      </Typography>
      <Box height={520}>
        <DataGrid rows={contributions} columns={columns} disableRowSelectionOnClick loading={busy} getRowId={(row) => row.account_id} pageSizeOptions={[10, 25, 50]} initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }} />
      </Box>
    </Box>
  );
}
