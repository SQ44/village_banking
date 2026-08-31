import { useEffect, useMemo, useState } from "react";
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

import { Api } from "../api";
import { AppShell, type NavItem } from "../layout/AppShell";
import { useColorMode } from "../colorMode";
import { MemberContext, type MemberContextValue } from "./memberContext";
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
