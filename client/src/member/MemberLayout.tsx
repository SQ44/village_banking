import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  InputLabel,
  InputAdornment,
  LinearProgress,
  MenuItem,
  Select,
  Skeleton,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ReceiptLongIcon from "@mui/icons-material/ReceiptLong";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import GroupIcon from "@mui/icons-material/Group";
import ChecklistIcon from "@mui/icons-material/Checklist";

import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { Api } from "../api";
import { ScorecardDialog, type ScorecardItem } from "../components/ScorecardDialog";
import { PageHeader } from "../components/PageHeader";
import { AppShell, type NavItem } from "../layout/AppShell";
import { StatCard } from "../components/StatCard";
import { StatusChip } from "../components/StatusChip";
import { currency, formatDate, formatDateTime } from "../lib/format";
import { useColorMode } from "../colorMode";
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
  const { mode, toggle } = useColorMode();

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
      <Button
        startIcon={<CreditCardIcon />}
        variant="contained"
        disabled={busy || !membershipAccepted || !constitutionLocked || !group?.id}
        onClick={openRequest}
        aria-label="Request loan"
        sx={{ "& .MuiButton-startIcon": { mr: { xs: 0, sm: 1 } } }}
      >
        <Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>
          Request loan
        </Box>
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
      <AppShell
        title="Village Banking"
        user={currentUser}
        navItems={navItems}
        header={header}
        actions={actions}
        colorMode={mode}
        onToggleColorMode={toggle}
        onLogout={onLogout}
      >
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
                <StatCard label="Savings" value={currency(Number(summary?.savings_balance ?? 0))} icon={<DashboardIcon color="action" />} loading={busy} />
              </Grid>
              <Grid item xs={12} md={3}>
                <StatCard label="Interest earned" value={currency(Number(summary?.interest_earned ?? 0))} icon={<DashboardIcon color="action" />} loading={busy} />
              </Grid>
              <Grid item xs={12} md={3}>
                <StatCard label="Outstanding loans" value={currency(Number(summary?.loan_outstanding ?? 0))} icon={<CreditCardIcon color="action" />} loading={busy} />
              </Grid>
              <Grid item xs={12} md={3}>
                <StatCard label="My share (%)" value={`${(forecast?.my_share_percent ?? 0).toFixed(2)}%`} icon={<GroupIcon color="action" />} loading={busy} />
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
  const { group, summary, forecast, transactions, busy } = useMember();
  const [target, setTarget] = useState<number | "">("");
  const groupId = group?.id ?? null;
  const targetKey = groupId ? `vb_member_target_${groupId}` : null;

  useEffect(() => {
    if (!targetKey) return;
    const saved = localStorage.getItem(targetKey);
    const value = saved ? Number(saved) : NaN;
    setTarget(Number.isFinite(value) ? value : "");
  }, [targetKey]);

  useEffect(() => {
    if (!targetKey) return;
    if (target === "") return;
    localStorage.setItem(targetKey, String(target));
  }, [target, targetKey]);

  if (!group) return null;

  const now = new Date();
  const cycleDays = Math.max(1, Number(group.settings?.withdrawal_cycle_days ?? 30));

  const nextWithdrawalAt = summary?.next_withdrawal_at ? new Date(summary.next_withdrawal_at) : null;
  const lastWithdrawalAt = summary?.account?.last_withdrawal_at ? new Date(summary.account.last_withdrawal_at) : null;

  const cycleStart =
    lastWithdrawalAt && !Number.isNaN(lastWithdrawalAt.getTime())
      ? lastWithdrawalAt
      : nextWithdrawalAt && !Number.isNaN(nextWithdrawalAt.getTime())
        ? new Date(nextWithdrawalAt.getTime() - cycleDays * 24 * 60 * 60 * 1000)
        : null;

  const cycleEnd =
    nextWithdrawalAt && !Number.isNaN(nextWithdrawalAt.getTime())
      ? nextWithdrawalAt
      : cycleStart
        ? new Date(cycleStart.getTime() + cycleDays * 24 * 60 * 60 * 1000)
        : null;

  const daysRemaining =
    typeof summary?.days_until_withdrawal === "number"
      ? Math.max(0, Number(summary.days_until_withdrawal))
      : cycleEnd
        ? Math.max(0, Math.floor((cycleEnd.getTime() - now.getTime()) / (24 * 60 * 60 * 1000)))
        : 0;

  const txInWindow = cycleStart
    ? transactions.filter((tx) => {
        const createdAt = new Date(tx.created_at);
        return (
          tx.status === "completed" &&
          !Number.isNaN(createdAt.getTime()) &&
          createdAt.getTime() >= cycleStart.getTime() &&
          createdAt.getTime() <= now.getTime()
        );
      })
    : [];

  const flow = txInWindow.reduce(
    (acc, tx) => {
      const amount = Number(tx.amount) || 0;
      if (tx.type === "deposit" || tx.type === "loan_repayment" || tx.type === "interest") {
        acc.inflow += amount;
        if (tx.type === "deposit") {
          acc.depositCount += 1;
          acc.depositTotal += amount;
        }
      } else if (tx.type === "withdrawal" || tx.type === "fee" || tx.type === "loan_disbursement") {
        acc.outflow += amount;
      }
      return acc;
    },
    { inflow: 0, outflow: 0, depositCount: 0, depositTotal: 0 }
  );

  const daysElapsed = cycleStart
    ? Math.max(1, Math.ceil((now.getTime() - cycleStart.getTime()) / (24 * 60 * 60 * 1000)))
    : 1;
  const net = flow.inflow - flow.outflow;
  const avgNetPerDay = net / daysElapsed;

  const currentSavings = Number(summary?.savings_balance ?? 0);
  const projectedSavings = currentSavings + avgNetPerDay * daysRemaining;

  const minMonthly = Number(group.settings?.min_monthly_contribution ?? 0);
  const suggestedTarget = Math.max(
    currentSavings,
    projectedSavings,
    currentSavings + (minMonthly / 30) * daysRemaining
  );
  const effectiveTarget = target === "" ? suggestedTarget : Math.max(0, Number(target));

  const remainingToTarget = Math.max(0, effectiveTarget - currentSavings);
  const requiredPerDay = daysRemaining > 0 ? remainingToTarget / daysRemaining : remainingToTarget;
  const requiredPerWeek = requiredPerDay * 7;
  const onTrack = projectedSavings + 1e-9 >= effectiveTarget;

  const progress = effectiveTarget > 0 ? Math.min(100, (currentSavings / effectiveTarget) * 100) : 0;
  const expectedInterest = (forecast?.loans ?? []).reduce((sum, item) => sum + Number(item.my_expected_interest ?? 0), 0);

  return (
    <Box>
      <PageHeader title="Overview" subtitle="Key dates for withdrawals and interest accrual in this cycle." />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <Alert severity="info">
            Next withdrawal:{" "}
            {busy && !summary ? (
              <Skeleton width={140} sx={{ display: "inline-block" }} />
            ) : summary?.next_withdrawal_at ? (
              formatDate(summary.next_withdrawal_at)
            ) : (
              "Not scheduled"
            )}
          </Alert>
        </Grid>
        <Grid item xs={12} md={6}>
          <Alert severity="info">
            Next interest accrual:{" "}
            {busy && !summary ? (
              <Skeleton width={140} sx={{ display: "inline-block" }} />
            ) : summary?.next_interest_accrual_at ? (
              formatDate(summary.next_interest_accrual_at)
            ) : (
              "Not scheduled"
            )}
          </Alert>
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} lg={7}>
          <Card
            sx={{
              height: "100%",
              transition: "transform 160ms ease, box-shadow 160ms ease",
              "&:hover": { transform: "translateY(-1px)", boxShadow: "0 10px 24px rgba(15,23,42,0.10)" },
            }}
          >
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="flex-start" gap={2} mb={1}>
                <Box minWidth={0}>
                  <Typography variant="subtitle1" fontWeight={800}>
                    Savings projection
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Projected balance by withdrawal date based on your current pace.
                  </Typography>
                </Box>
                <Box textAlign="right" flexShrink={0}>
                  <Typography variant="body2" color="text.secondary">
                    Cycle ends
                  </Typography>
                  <Typography variant="body2" fontWeight={700}>
                    {cycleEnd ? cycleEnd.toLocaleDateString() : "—"}
                  </Typography>
                </Box>
              </Box>

              <Grid container spacing={2} sx={{ mt: 0.5 }}>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Current savings
                  </Typography>
                  <Typography variant="h6">{busy && !summary ? "—" : currency(currentSavings)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Projected by cycle end
                  </Typography>
                  <Typography variant="h6">{busy && !summary ? "—" : currency(projectedSavings)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Avg net / day (cycle)
                  </Typography>
                  <Typography variant="h6">{busy && !summary ? "—" : currency(avgNetPerDay)}</Typography>
                </Grid>
              </Grid>

              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mt: 2 }}>
                <TextField
                  label="Target by cycle end"
                  type="number"
                  fullWidth
                  value={target}
                  onChange={(e) => setTarget(e.target.value === "" ? "" : Number(e.target.value))}
                  disabled={!summary}
                  InputProps={{
                    startAdornment: <InputAdornment position="start">K</InputAdornment>,
                  }}
                  helperText={
                    target === ""
                      ? `Suggested: ${currency(suggestedTarget)} (based on pace + minimum contribution)`
                      : onTrack
                        ? "On track at current pace."
                        : `Need about ${currency(requiredPerWeek)} / week to reach target.`
                  }
                />
                <Box minWidth={{ sm: 220 }} flexShrink={0}>
                  <Typography variant="caption" color="text.secondary">
                    Progress
                  </Typography>
                  <Box display="flex" alignItems="center" gap={1} mt={0.5}>
                    <Box flex={1}>
                      <LinearProgress
                        variant="determinate"
                        value={busy && !summary ? 0 : progress}
                        sx={{ height: 10, borderRadius: 999, backgroundColor: "rgba(15,23,42,0.08)" }}
                      />
                    </Box>
                    <Typography variant="body2" fontWeight={700}>
                      {busy && !summary ? "—" : `${Math.round(progress)}%`}
                    </Typography>
                  </Box>
                  <Typography variant="body2" color={onTrack ? "success.main" : "text.secondary"} sx={{ mt: 1 }}>
                    {busy && !summary
                      ? "Calculating..."
                      : onTrack
                        ? "On track for your target."
                        : daysRemaining > 0
                          ? `Required pace: ${currency(requiredPerDay)} / day`
                          : "Target requires additional savings."}
                  </Typography>
                </Box>
              </Stack>

              <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mt: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Deposits this cycle: {flow.depositCount} • Avg deposit:{" "}
                  {flow.depositCount ? currency(flow.depositTotal / flow.depositCount) : "—"}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Days remaining: {daysRemaining}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={5}>
          <Card
            sx={{
              height: "100%",
              transition: "transform 160ms ease, box-shadow 160ms ease",
              "&:hover": { transform: "translateY(-1px)", boxShadow: "0 10px 24px rgba(15,23,42,0.10)" },
            }}
          >
            <CardContent>
              <Typography variant="subtitle1" fontWeight={800} gutterBottom>
                Interest outlook
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Expected interest from current active loans, distributed by contribution share.
              </Typography>

              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">
                    My share
                  </Typography>
                  <Typography variant="h6">{(forecast?.my_share_percent ?? 0).toFixed(2)}%</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">
                    Expected interest
                  </Typography>
                  <Typography variant="h6">{currency(expectedInterest)}</Typography>
                </Grid>
              </Grid>

              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Net contribution: {currency(Number(forecast?.my_net_contribution ?? 0))} • Group total:{" "}
                  {currency(Number(forecast?.group_total_contributions ?? 0))}
                </Typography>
              </Box>
            </CardContent>
          </Card>
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
      <PageHeader title="Transactions" subtitle="Deposits, repayments, interest distribution, and adjustments." />
      <Box height={520}>
        <DataGrid
          rows={transactions}
          columns={columns}
          density="compact"
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
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
      <PageHeader title="Requests" subtitle="Submit loan requests and see the system’s decision scorecard (no gatekeeping)." />
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
        <DataGrid
          rows={requests}
          columns={columns}
          density="compact"
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
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
      <PageHeader title="My loans" subtitle="Click a loan to make a repayment (interest first, then principal)." />
      {!membershipAccepted && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Accept group terms before repaying loans.
        </Alert>
      )}
      <Box height={520}>
        <DataGrid
          rows={myLoans}
          columns={columns}
          density="compact"
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          onRowClick={(params) => openRepay(Number(params.id))}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
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
      <PageHeader title="Group loans" subtitle="Transparency board: outstanding loans and your expected interest share." />
      <Box height={520}>
        <DataGrid
          rows={groupLoans}
          columns={columns}
          density="compact"
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
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
      <PageHeader title="Shares" subtitle="Contribution shares are used to split loan interest (after admin fee) across members." />
      <Box height={520}>
        <DataGrid
          rows={contributions}
          columns={columns}
          density="compact"
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.account_id}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
      </Box>
    </Box>
  );
}
