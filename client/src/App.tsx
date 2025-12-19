import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputLabel,
  Menu,
  MenuItem,
  Select,
  Snackbar,
  Tab,
  Tabs,
  TextField,
  Typography,
  Switch,
} from "@mui/material";
import LogoutIcon from "@mui/icons-material/Logout";
import SettingsIcon from "@mui/icons-material/Settings";
import AddIcon from "@mui/icons-material/Add";
import PaymentsIcon from "@mui/icons-material/Payments";
import GroupIcon from "@mui/icons-material/Group";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";

import { Api } from "./api";
import type {
  Account,
  Group,
  GroupSettingsUpdatePayload,
  GroupWithSettings,
  Loan,
  LoanBoardItem,
  LoanCreatePayload,
  LoanRepaymentPayload,
  MemberInvitePayload,
  MemberForecast,
  MemberLoanForecast,
  MemberSummary,
  GroupContributionItem,
  Transaction,
  User,
  LoanRequest,
  LoanRequestCreatePayload,
} from "./types";

const TOKEN_STORAGE_KEY = "vb_token";

function currency(amount: number) {
  const formatter = new Intl.NumberFormat("en-ZM", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const abs = Math.abs(amount);
  const formatted = formatter.format(abs);
  return amount < 0 ? `-K ${formatted}` : `K ${formatted}`;
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(false);
  const [snack, setSnack] = useState<string | null>(null);

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    Api.setToken(null);
    setToken(null);
    setCurrentUser(null);
  };

  useEffect(() => {
    Api.setToken(token);
    if (!token) {
      setCurrentUser(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const me = await Api.getCurrentUser();
        if (!cancelled) setCurrentUser(me);
      } catch (err) {
        console.error(err);
        handleLogout();
        setSnack(err instanceof Error ? err.message : "Unable to authenticate");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (!token) {
    return <LoginScreen onSuccess={(t) => setToken(t)} />;
  }

  if (loading || !currentUser) {
    return (
      <Box display="grid" height="100%" sx={{ placeItems: "center" }}>
        <CircularProgress />
      </Box>
    );
  }

  const isMember = currentUser.role === "member";
  return (
    <>
      {isMember ? (
        <MemberWorkspace currentUser={currentUser} onLogout={handleLogout} onError={setSnack} />
      ) : (
        <AdminWorkspace currentUser={currentUser} onLogout={handleLogout} onError={setSnack} />
      )}
      <Snackbar open={!!snack} autoHideDuration={6000} onClose={() => setSnack(null)}>
        <Alert severity="error" onClose={() => setSnack(null)} sx={{ width: "100%" }}>
          {snack}
        </Alert>
      </Snackbar>
    </>
  );
}

function LoginScreen({ onSuccess }: { onSuccess: (token: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const resp = await Api.login(email, password);
      localStorage.setItem(TOKEN_STORAGE_KEY, resp.access_token);
      onSuccess(resp.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box display="grid" height="100%" sx={{ placeItems: "center", p: 2 }}>
      <Card sx={{ width: "100%", maxWidth: 420 }}>
        <CardContent>
          <Typography variant="h5" gutterBottom>
            Village Banking
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Sign in to manage your savings group, loans, and interest distribution.
          </Typography>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          <TextField
            label="Email"
            fullWidth
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            sx={{ mb: 2 }}
            autoComplete="username"
          />
          <TextField
            label="Password"
            fullWidth
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            sx={{ mb: 2 }}
            autoComplete="current-password"
          />
          <Button variant="contained" fullWidth disabled={busy} onClick={submit}>
            {busy ? "Signing in..." : "Sign in"}
          </Button>
        </CardContent>
      </Card>
    </Box>
  );
}

function TopBar({
  title,
  currentUser,
  onLogout,
  actions,
}: {
  title: string;
  currentUser: User;
  onLogout: () => void;
  actions?: React.ReactNode;
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  return (
    <AppBar position="sticky" elevation={0} color="transparent">
      <Container maxWidth="lg">
        <Box display="flex" alignItems="center" justifyContent="space-between" py={2}>
          <Box>
            <Typography variant="h5">{title}</Typography>
            <Typography variant="body2" color="text.secondary">
              {currentUser.full_name ?? currentUser.email} · {currentUser.role}
            </Typography>
          </Box>
          <Box display="flex" alignItems="center" gap={1}>
            {actions}
            <IconButton onClick={(e) => setAnchor(e.currentTarget)} aria-label="account menu">
              <SettingsIcon />
            </IconButton>
            <Menu open={!!anchor} anchorEl={anchor} onClose={() => setAnchor(null)}>
              <MenuItem
                onClick={() => {
                  setAnchor(null);
                  onLogout();
                }}
              >
                <LogoutIcon fontSize="small" style={{ marginRight: 8 }} /> Logout
              </MenuItem>
            </Menu>
          </Box>
        </Box>
      </Container>
      <Divider />
    </AppBar>
  );
}

function StatCard({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
          <Typography variant="body2" color="text.secondary">
            {label}
          </Typography>
          {icon}
        </Box>
        <Typography variant="h6">{value}</Typography>
      </CardContent>
    </Card>
  );
}

function AdminWorkspace({
  currentUser,
  onLogout,
  onError,
}: {
  currentUser: User;
  onLogout: () => void;
  onError: (msg: string) => void;
}) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<number | "">("");
  const [groupDetails, setGroupDetails] = useState<GroupWithSettings | null>(null);
  const [members, setMembers] = useState<Account[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loanRequests, setLoanRequests] = useState<LoanRequest[]>([]);
  const [tab, setTab] = useState(0);
  const [busy, setBusy] = useState(false);

  const [createGroupOpen, setCreateGroupOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");

  const [inviteOpen, setInviteOpen] = useState(false);
  const [invite, setInvite] = useState<MemberInvitePayload>({
    email: "",
    full_name: "",
    password: "",
    name: "",
    min_initial_deposit: 0,
    custom_fields: {},
  });

  const [loanOpen, setLoanOpen] = useState(false);
  const [loanDraft, setLoanDraft] = useState<LoanCreatePayload>({
    borrower_account_id: 0,
    principal: 0,
    term_months: 3,
    repayment_frequency: "monthly",
    description: "",
  });

  const refresh = async (groupId?: number) => {
    setBusy(true);
    try {
      const groupList = await Api.getGroups();
      setGroups(groupList);
      const resolved = groupId ?? (selectedGroupId === "" ? groupList[0]?.id : Number(selectedGroupId));
      if (!resolved) {
        setSelectedGroupId("");
        setGroupDetails(null);
        setMembers([]);
        setLoans([]);
        setLoanRequests([]);
        return;
      }
      setSelectedGroupId(resolved);
      const [details, accounts, groupLoans, requests] = await Promise.all([
        Api.getGroup(resolved),
        Api.getGroupAccounts(resolved),
        Api.getGroupLoans(resolved),
        Api.listLoanRequests(resolved),
      ]);
      setGroupDetails(details);
      setMembers(accounts);
      setLoans(groupLoans);
      setLoanRequests(requests);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load admin workspace");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const memberColumns: GridColDef<Account>[] = useMemo(
    () => [
      { field: "name", headerName: "Member", flex: 1, minWidth: 180 },
      { field: "email", headerName: "Email", flex: 1, minWidth: 220 },
      { field: "balance", headerName: "Savings", minWidth: 140, valueFormatter: (v) => currency(Number(v)) },
    ],
    []
  );

  const loanColumns: GridColDef<Loan>[] = useMemo(
    () => [
      { field: "id", headerName: "Loan", width: 90 },
      { field: "borrower_account_id", headerName: "Borrower ID", width: 120 },
      { field: "principal", headerName: "Principal", width: 140, valueFormatter: (v) => currency(Number(v)) },
      {
        field: "outstanding_principal",
        headerName: "Outstanding",
        width: 160,
        valueGetter: (_, row) => Number(row.outstanding_principal) + Number(row.outstanding_interest),
        valueFormatter: (v) => currency(Number(v)),
      },
      { field: "status", headerName: "Status", width: 120 },
    ],
    []
  );

  const memberNameByAccountId = useMemo(() => {
    const map = new Map<number, string>();
    for (const m of members) {
      map.set(Number(m.id), m.name);
    }
    return map;
  }, [members]);

  const constitutionLocked = Boolean(groupDetails?.settings?.constitution_locked_at);

  const requestColumns: GridColDef<LoanRequest>[] = useMemo(
    () => [
      { field: "id", headerName: "Request", width: 110 },
      {
        field: "borrower_account_id",
        headerName: "Member",
        flex: 1,
        minWidth: 180,
        valueGetter: (_, row) => memberNameByAccountId.get(Number(row.borrower_account_id)) ?? `Account ${row.borrower_account_id}`,
      },
      { field: "principal", headerName: "Principal", width: 140, valueFormatter: (v) => currency(Number(v)) },
      { field: "term_months", headerName: "Term", width: 110, valueFormatter: (v) => `${Number(v)} mo` },
      { field: "repayment_frequency", headerName: "Frequency", width: 130 },
      { field: "status", headerName: "Status", width: 120 },
      {
        field: "scorecard",
        headerName: "Scorecard",
        width: 130,
        sortable: false,
        filterable: false,
        renderCell: ({ row }) => {
          const scorecard = row.custom_fields?.scorecard;
          if (!scorecard) return null;
          return (
            <Button size="small" variant="outlined" onClick={() => window.alert(JSON.stringify(scorecard, null, 2))}>
              View
            </Button>
          );
        },
      },
      {
        field: "approved_loan_id",
        headerName: "Loan",
        width: 110,
        valueGetter: (_, row) => (row.custom_fields?.approved_loan_id ? `#${row.custom_fields.approved_loan_id}` : ""),
      },
      { field: "decision_reason", headerName: "Reason", flex: 1, minWidth: 220, valueGetter: (_, row) => row.decision_reason ?? "" },
      {
        field: "scorecard",
        headerName: "Scorecard",
        width: 130,
        sortable: false,
        filterable: false,
        renderCell: ({ row }) => {
          const scorecard = row.custom_fields?.scorecard;
          if (!scorecard) return null;
          return (
            <Button size="small" variant="outlined" onClick={() => window.alert(JSON.stringify(scorecard, null, 2))}>
              View
            </Button>
          );
        },
      },
      {
        field: "created_at",
        headerName: "Requested",
        width: 170,
        valueFormatter: (v) => (v ? new Date(String(v)).toLocaleString() : "—"),
      },
    ],
    [memberNameByAccountId]
  );

  const saveSettings = async (updates: GroupSettingsUpdatePayload) => {
    if (!selectedGroupId) return;
    try {
      const updated = await Api.updateGroupSettings(Number(selectedGroupId), updates);
      setGroupDetails((prev) => (prev ? { ...prev, settings: updated } : prev));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to save settings");
    }
  };

  const lockConstitution = async () => {
    if (!selectedGroupId) return;
    try {
      const updated = await Api.lockGroupConstitution(Number(selectedGroupId));
      setGroupDetails((prev) => (prev ? { ...prev, settings: updated } : prev));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to lock constitution");
    }
  };

  return (
    <>
      <TopBar
        title="Admin Console"
        currentUser={currentUser}
        onLogout={onLogout}
        actions={
          <Button startIcon={<AddIcon />} variant="contained" onClick={() => setCreateGroupOpen(true)}>
            New Group
          </Button>
        }
      />
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Grid container spacing={2} alignItems="center" sx={{ mb: 2 }}>
          <Grid item xs={12} md={6}>
            <FormControl fullWidth>
              <InputLabel id="group-select-label">Group</InputLabel>
              <Select
                labelId="group-select-label"
                value={selectedGroupId}
                label="Group"
                onChange={(e) => refresh(Number(e.target.value))}
              >
                {groups.map((g) => (
                  <MenuItem key={g.id} value={g.id}>
                    {g.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={6} display="flex" justifyContent="flex-end" gap={1}>
            <Button startIcon={<GroupIcon />} variant="outlined" disabled={!selectedGroupId} onClick={() => setInviteOpen(true)}>
              Add member
            </Button>
            <Button startIcon={<CreditCardIcon />} variant="outlined" disabled={!selectedGroupId} onClick={() => setLoanOpen(true)}>
              Create loan
            </Button>
          </Grid>
        </Grid>

        {!selectedGroupId ? (
          <Alert severity="info">Create a group to get started.</Alert>
        ) : (
          <>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={4}>
                <StatCard label="Members" value={`${members.length}`} icon={<GroupIcon color="action" />} />
              </Grid>
              <Grid item xs={12} md={4}>
                <StatCard
                  label="Total Savings"
                  value={currency(members.reduce((sum, m) => sum + Number(m.balance), 0))}
                  icon={<PaymentsIcon color="action" />}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <StatCard label="Active Loans" value={`${loans.filter((l) => l.status === "active").length}`} icon={<CreditCardIcon color="action" />} />
              </Grid>
              <Grid item xs={12} md={4}>
                <StatCard
                  label="Pending Requests"
                  value={`${loanRequests.filter((r) => r.status === "requested" || r.status === "queued").length}`}
                  icon={<CreditCardIcon color="action" />}
                />
              </Grid>
            </Grid>

            <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
              <Tab label="Members" />
              <Tab label="Loans" />
              <Tab label="Requests" />
              <Tab label="Settings" />
            </Tabs>

            {tab === 0 && (
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Members
                  </Typography>
                  <Box height={420}>
                    <DataGrid
                      rows={members}
                      columns={memberColumns}
                      disableRowSelectionOnClick
                      loading={busy}
                      getRowId={(row) => row.id}
                      pageSizeOptions={[10, 25, 50]}
                      initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
                    />
                  </Box>
                </CardContent>
              </Card>
            )}

            {tab === 1 && (
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Loans
                  </Typography>
                  <Box height={420}>
                    <DataGrid
                      rows={loans}
                      columns={loanColumns}
                      disableRowSelectionOnClick
                      loading={busy}
                      getRowId={(row) => row.id}
                      pageSizeOptions={[10, 25, 50]}
                      initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
                    />
                  </Box>
                </CardContent>
              </Card>
            )}

            {tab === 2 && (
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Loan requests
                  </Typography>
                  <Alert severity="info" sx={{ mb: 2 }}>
                    {constitutionLocked
                      ? "Autonomous lending is enabled. Requests are auto-approved, rejected, or queued by the constitution."
                      : "Lock the constitution in Settings to enable autonomous lending (members cannot request loans before it is locked)."}
                  </Alert>
                  <Box height={420}>
                    <DataGrid
                      rows={loanRequests}
                      columns={requestColumns}
                      disableRowSelectionOnClick
                      loading={busy}
                      getRowId={(row) => row.id}
                      pageSizeOptions={[10, 25, 50]}
                      initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
                    />
                  </Box>
                </CardContent>
              </Card>
            )}

            {tab === 3 && groupDetails && <SettingsPanel group={groupDetails} onSave={saveSettings} onLockConstitution={lockConstitution} busy={busy} />}
          </>
        )}
      </Container>

      <Dialog open={createGroupOpen} onClose={() => setCreateGroupOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create group</DialogTitle>
        <DialogContent>
          <TextField label="Group name" fullWidth value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)} sx={{ mt: 1 }} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateGroupOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!newGroupName.trim()}
            onClick={async () => {
              try {
                const created = await Api.createGroup({
                  name: newGroupName.trim(),
                  terms: "By joining, you agree to contribute as scheduled and repay loans on time.",
                });
                setCreateGroupOpen(false);
                setNewGroupName("");
                await refresh(created.id);
              } catch (err) {
                onError(err instanceof Error ? err.message : "Failed to create group");
              }
            }}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={inviteOpen} onClose={() => setInviteOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add member</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField label="Member name" fullWidth value={invite.name} onChange={(e) => setInvite((p) => ({ ...p, name: e.target.value }))} />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField label="Email" fullWidth value={invite.email} onChange={(e) => setInvite((p) => ({ ...p, email: e.target.value }))} />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField label="Full name (optional)" fullWidth value={invite.full_name ?? ""} onChange={(e) => setInvite((p) => ({ ...p, full_name: e.target.value }))} />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField label="Temporary password" fullWidth type="password" value={invite.password} onChange={(e) => setInvite((p) => ({ ...p, password: e.target.value }))} />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                label="Initial contribution"
                fullWidth
                type="number"
                value={invite.min_initial_deposit ?? 0}
                onChange={(e) => setInvite((p) => ({ ...p, min_initial_deposit: Number(e.target.value) }))}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInviteOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!selectedGroupId || !invite.name.trim() || !invite.email.trim() || !invite.password}
            onClick={async () => {
              try {
                await Api.addGroupMember(Number(selectedGroupId), invite);
                setInviteOpen(false);
                setInvite({ email: "", full_name: "", password: "", name: "", min_initial_deposit: 0, custom_fields: {} });
                await refresh(Number(selectedGroupId));
              } catch (err) {
                onError(err instanceof Error ? err.message : "Failed to add member");
              }
            }}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={loanOpen} onClose={() => setLoanOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create loan</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel id="borrower-label">Borrower</InputLabel>
                <Select
                  labelId="borrower-label"
                  label="Borrower"
                  value={loanDraft.borrower_account_id || ""}
                  onChange={(e) => setLoanDraft((p) => ({ ...p, borrower_account_id: Number(e.target.value) }))}
                >
                  {members.map((m) => (
                    <MenuItem key={m.id} value={m.id}>
                      {m.name} ({currency(Number(m.balance))})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField label="Principal" type="number" fullWidth value={loanDraft.principal} onChange={(e) => setLoanDraft((p) => ({ ...p, principal: Number(e.target.value) }))} />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField label="Term (months)" type="number" fullWidth value={loanDraft.term_months ?? 3} onChange={(e) => setLoanDraft((p) => ({ ...p, term_months: Number(e.target.value) }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField label="Description (optional)" fullWidth value={loanDraft.description ?? ""} onChange={(e) => setLoanDraft((p) => ({ ...p, description: e.target.value }))} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLoanOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!selectedGroupId || !loanDraft.borrower_account_id || loanDraft.principal <= 0}
            onClick={async () => {
              try {
                await Api.createLoan(Number(selectedGroupId), loanDraft);
                setLoanOpen(false);
                setLoanDraft({ borrower_account_id: 0, principal: 0, term_months: 3, repayment_frequency: "monthly", description: "" });
                await refresh(Number(selectedGroupId));
              } catch (err) {
                onError(err instanceof Error ? err.message : "Failed to create loan");
              }
            }}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

function SettingsPanel({
  group,
  onSave,
  onLockConstitution,
  busy,
}: {
  group: GroupWithSettings;
  onSave: (p: GroupSettingsUpdatePayload) => Promise<void> | void;
  onLockConstitution: () => Promise<void> | void;
  busy: boolean;
}) {
  const [draft, setDraft] = useState<GroupSettingsUpdatePayload>(() => ({
    min_monthly_contribution: group.settings.min_monthly_contribution,
    admin_fee_percent: group.settings.admin_fee_percent,
    loan_interest_percent: group.settings.loan_interest_percent,
    enforce_loan_limit: group.settings.enforce_loan_limit,
    loan_limit_multiplier: group.settings.loan_limit_multiplier,
    liquidity_max_outstanding_percent: group.settings.liquidity_max_outstanding_percent,
    min_term_months: group.settings.min_term_months,
    max_term_months: group.settings.max_term_months,
    max_active_loans_per_member: group.settings.max_active_loans_per_member,
    cooldown_days_after_settlement: group.settings.cooldown_days_after_settlement,
    withdrawal_cycle_days: group.settings.withdrawal_cycle_days,
    allow_advance_contribution: group.settings.allow_advance_contribution,
  }));

  useEffect(() => {
    setDraft({
      min_monthly_contribution: group.settings.min_monthly_contribution,
      admin_fee_percent: group.settings.admin_fee_percent,
      loan_interest_percent: group.settings.loan_interest_percent,
      enforce_loan_limit: group.settings.enforce_loan_limit,
      loan_limit_multiplier: group.settings.loan_limit_multiplier,
      liquidity_max_outstanding_percent: group.settings.liquidity_max_outstanding_percent,
      min_term_months: group.settings.min_term_months,
      max_term_months: group.settings.max_term_months,
      max_active_loans_per_member: group.settings.max_active_loans_per_member,
      cooldown_days_after_settlement: group.settings.cooldown_days_after_settlement,
      withdrawal_cycle_days: group.settings.withdrawal_cycle_days,
      allow_advance_contribution: group.settings.allow_advance_contribution,
    });
  }, [group]);

  const locked = Boolean(group.settings.constitution_locked_at);

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Group settings
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {locked
            ? `Constitution locked at ${new Date(String(group.settings.constitution_locked_at)).toLocaleString()}. Settings are immutable for this cycle.`
            : "Set the constitution for this cycle, then lock it to enable autonomous lending."}
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <TextField
              label="Minimum monthly contribution"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.min_monthly_contribution ?? 0}
              onChange={(e) => setDraft((p) => ({ ...p, min_monthly_contribution: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              label="Admin fee (% of loan interest)"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.admin_fee_percent ?? 0}
              onChange={(e) => setDraft((p) => ({ ...p, admin_fee_percent: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              label="Loan interest (%)"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.loan_interest_percent ?? 10}
              onChange={(e) => setDraft((p) => ({ ...p, loan_interest_percent: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              label="Loan limit multiplier"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.loan_limit_multiplier ?? 2}
              onChange={(e) => setDraft((p) => ({ ...p, loan_limit_multiplier: Number(e.target.value) }))}
              helperText={draft.enforce_loan_limit ? "Max loan = contribution x multiplier" : "Loan limit disabled"}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <FormControlLabel
              control={
                <Switch
                  checked={draft.enforce_loan_limit ?? true}
                  disabled={busy || locked}
                  onChange={(e) => setDraft((p) => ({ ...p, enforce_loan_limit: e.target.checked }))}
                />
              }
              label="Enforce loan limit"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              label="Liquidity cap (% outstanding)"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.liquidity_max_outstanding_percent ?? 80}
              onChange={(e) => setDraft((p) => ({ ...p, liquidity_max_outstanding_percent: Number(e.target.value) }))}
              helperText="Total outstanding principal must stay below this % of the pool"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              label="Min term (months)"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.min_term_months ?? 1}
              onChange={(e) => setDraft((p) => ({ ...p, min_term_months: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              label="Max term (months)"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.max_term_months ?? 12}
              onChange={(e) => setDraft((p) => ({ ...p, max_term_months: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              label="Max active loans per member"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.max_active_loans_per_member ?? 1}
              onChange={(e) => setDraft((p) => ({ ...p, max_active_loans_per_member: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              label="Cooldown after settlement (days)"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.cooldown_days_after_settlement ?? 0}
              onChange={(e) => setDraft((p) => ({ ...p, cooldown_days_after_settlement: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              label="Withdrawal cycle (days)"
              type="number"
              fullWidth
              disabled={busy || locked}
              value={draft.withdrawal_cycle_days ?? 30}
              onChange={(e) => setDraft((p) => ({ ...p, withdrawal_cycle_days: Number(e.target.value) }))}
            />
          </Grid>
        </Grid>
        <Box display="flex" justifyContent="space-between" mt={2}>
          <Button
            variant="outlined"
            color="warning"
            disabled={busy || locked}
            onClick={() => {
              if (window.confirm("Lock constitution for this cycle? This cannot be changed later.")) {
                void onLockConstitution();
              }
            }}
          >
            Lock constitution
          </Button>
          <Button variant="contained" disabled={busy || locked} onClick={() => onSave(draft)}>
            Save
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}

function MemberWorkspace({
  currentUser,
  onLogout,
  onError,
}: {
  currentUser: User;
  onLogout: () => void;
  onError: (msg: string) => void;
}) {
  const [summary, setSummary] = useState<MemberSummary | null>(null);
  const [forecast, setForecast] = useState<MemberForecast | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [groupLoans, setGroupLoans] = useState<LoanBoardItem[]>([]);
  const [contributions, setContributions] = useState<GroupContributionItem[]>([]);
  const [loanRequests, setLoanRequests] = useState<LoanRequest[]>([]);
  const [group, setGroup] = useState<GroupWithSettings | null>(null);
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

  const refresh = async () => {
    setBusy(true);
    try {
      const ctx = await Api.getMeContext();
      const accepted = !!ctx.membership?.accepted_terms_at;
      setGroup(ctx.group ?? null);
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
      } else {
        setForecast(null);
      }

      if (ctx.group?.id) {
        const myLoans = await Api.getGroupLoans(ctx.group.id);
        setLoans(myLoans);
        if (accepted) {
          try {
            setGroupLoans(await Api.getGroupLoanBoard(ctx.group.id));
          } catch {
            setGroupLoans([]);
          }
          try {
            setContributions(await Api.getGroupContributions(ctx.group.id));
          } catch {
            setContributions([]);
          }
          try {
            setLoanRequests(await Api.listLoanRequests(ctx.group.id));
          } catch {
            setLoanRequests([]);
          }
        } else {
          setGroupLoans([]);
          setContributions([]);
          setLoanRequests([]);
        }
      } else {
        setLoans([]);
        setGroupLoans([]);
        setContributions([]);
        setLoanRequests([]);
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load member portal");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: GridColDef<Transaction>[] = useMemo(
    () => [
      { field: "created_at", headerName: "Date", width: 180 },
      { field: "type", headerName: "Type", width: 160 },
      { field: "amount", headerName: "Amount", width: 140, valueFormatter: (v) => currency(Number(v)) },
      { field: "description", headerName: "Description", flex: 1, minWidth: 220 },
      { field: "status", headerName: "Status", width: 120 },
    ],
    []
  );

  const loanColumns: GridColDef<Loan>[] = useMemo(
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
      { field: "status", headerName: "Status", width: 120 },
    ],
    []
  );

  const forecastByLoanId = useMemo(() => {
    const map = new Map<number, MemberLoanForecast>();
    for (const item of forecast?.loans ?? []) {
      map.set(item.loan_id, item);
    }
    return map;
  }, [forecast]);

  const constitutionLocked = Boolean(group?.settings?.constitution_locked_at);

  const groupLoanColumns: GridColDef<LoanBoardItem>[] = useMemo(
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
      {
        field: "next_due_date",
        headerName: "Next due",
        width: 170,
        valueFormatter: (v) => (v ? new Date(String(v)).toLocaleDateString() : "—"),
      },
      {
        field: "my_expected_interest",
        headerName: "My expected interest",
        width: 180,
        valueGetter: (_, row) => forecastByLoanId.get(Number(row.id))?.my_expected_interest ?? 0,
        valueFormatter: (v) => currency(Number(v)),
      },
      { field: "status", headerName: "Status", width: 120 },
    ],
    [forecastByLoanId]
  );

  const contributionColumns: GridColDef<GroupContributionItem>[] = useMemo(
    () => [
      { field: "member_name", headerName: "Member", flex: 1, minWidth: 180 },
      { field: "net_contribution", headerName: "Net contribution", width: 170, valueFormatter: (v) => currency(Number(v)) },
      { field: "share_percent", headerName: "Share", width: 120, valueFormatter: (v) => `${Number(v).toFixed(2)}%` },
    ],
    []
  );

  const requestColumns: GridColDef<LoanRequest>[] = useMemo(
    () => [
      { field: "id", headerName: "Request", width: 110 },
      { field: "principal", headerName: "Principal", width: 140, valueFormatter: (v) => currency(Number(v)) },
      { field: "term_months", headerName: "Term", width: 110, valueFormatter: (v) => `${Number(v)} mo` },
      { field: "repayment_frequency", headerName: "Frequency", width: 130 },
      { field: "status", headerName: "Status", width: 120 },
      {
        field: "approved_loan_id",
        headerName: "Loan",
        width: 110,
        valueGetter: (_, row) => (row.custom_fields?.approved_loan_id ? `#${row.custom_fields.approved_loan_id}` : "—"),
      },
      { field: "decision_reason", headerName: "Note", flex: 1, minWidth: 200, valueGetter: (_, row) => row.decision_reason ?? "—" },
      {
        field: "created_at",
        headerName: "Requested",
        width: 170,
        valueFormatter: (v) => (v ? new Date(String(v)).toLocaleString() : "—"),
      },
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
    [busy, onError]
  );

  return (
    <>
      <TopBar title="My Wallet" currentUser={currentUser} onLogout={onLogout} />
      <Container maxWidth="lg" sx={{ py: 3 }}>
        {!membershipAccepted && group && (
          <Alert
            severity="warning"
            sx={{ mb: 2 }}
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
            <Typography variant="subtitle2" gutterBottom>
              Accept terms to continue
            </Typography>
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
              {group.terms || "No terms configured."}
            </Typography>
          </Alert>
        )}

        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} md={4}>
            <StatCard label="Savings" value={currency(Number(summary?.savings_balance ?? 0))} icon={<PaymentsIcon color="action" />} />
          </Grid>
          <Grid item xs={12} md={4}>
            <StatCard label="Interest earned" value={currency(Number(summary?.interest_earned ?? 0))} icon={<PaymentsIcon color="action" />} />
          </Grid>
          <Grid item xs={12} md={4}>
            <StatCard label="Outstanding loans" value={currency(Number(summary?.loan_outstanding ?? 0))} icon={<CreditCardIcon color="action" />} />
          </Grid>
          <Grid item xs={12} md={6}>
            <StatCard
              label="Next withdrawal"
              value={summary?.next_withdrawal_at ? new Date(summary.next_withdrawal_at).toLocaleDateString() : "—"}
              icon={<PaymentsIcon color="action" />}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <StatCard
              label="Next interest accrual"
              value={summary?.next_interest_accrual_at ? new Date(summary.next_interest_accrual_at).toLocaleDateString() : "—"}
              icon={<PaymentsIcon color="action" />}
            />
          </Grid>
        </Grid>

        {group && (
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">Group loans</Typography>
                <Typography variant="body2" color="text.secondary">
                  Your share: {(forecast?.my_share_percent ?? 0).toFixed(2)}% of distributable interest
                </Typography>
              </Box>
              <Box height={320}>
                <DataGrid
                  rows={groupLoans}
                  columns={groupLoanColumns}
                  disableRowSelectionOnClick
                  loading={busy}
                  getRowId={(row) => row.id}
                  pageSizeOptions={[5, 10]}
                  initialState={{ pagination: { paginationModel: { pageSize: 5, page: 0 } } }}
                />
              </Box>
            </CardContent>
          </Card>
        )}

        {group && (
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">Contribution shares</Typography>
                <Typography variant="body2" color="text.secondary">
                  Used to split loan interest after admin fee
                </Typography>
              </Box>
              <Box height={320}>
                <DataGrid
                  rows={contributions}
                  columns={contributionColumns}
                  disableRowSelectionOnClick
                  loading={busy}
                  getRowId={(row) => row.account_id}
                  pageSizeOptions={[5, 10]}
                  initialState={{ pagination: { paginationModel: { pageSize: 5, page: 0 } } }}
                />
              </Box>
            </CardContent>
          </Card>
        )}

        {group && (
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">Loan requests</Typography>
                <Button
                  variant="outlined"
                  disabled={busy || !membershipAccepted || !constitutionLocked}
                  onClick={() => {
                    setRequestDraft({ principal: 0, term_months: 1, repayment_frequency: "monthly", description: "" });
                    setRequestOpen(true);
                  }}
                >
                  Request loan
                </Button>
              </Box>
              {!constitutionLocked && (
                <Alert severity="info" sx={{ mb: 2 }}>
                  Loan requests open after the group locks the constitution for this cycle.
                </Alert>
              )}
              <Box height={320}>
                <DataGrid
                  rows={loanRequests}
                  columns={requestColumns}
                  disableRowSelectionOnClick
                  loading={busy}
                  getRowId={(row) => row.id}
                  pageSizeOptions={[5, 10]}
                  initialState={{ pagination: { paginationModel: { pageSize: 5, page: 0 } } }}
                />
              </Box>
            </CardContent>
          </Card>
        )}

        <Card variant="outlined" sx={{ mb: 2 }}>
          <CardContent>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">My loans</Typography>
              <Typography variant="body2" color="text.secondary">
                Tap a loan to repay
              </Typography>
            </Box>
            <Box height={260}>
              <DataGrid
                rows={loans}
                columns={loanColumns}
                disableRowSelectionOnClick
                loading={busy}
                getRowId={(row) => row.id}
                onRowClick={(params) => {
                  setRepayLoanId(Number(params.id));
                  setRepayAmount(0);
                  setRepayOpen(true);
                }}
                pageSizeOptions={[5, 10]}
                initialState={{ pagination: { paginationModel: { pageSize: 5, page: 0 } } }}
              />
            </Box>
          </CardContent>
        </Card>

        <Card variant="outlined">
          <CardContent>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">My transactions</Typography>
              <Button variant="outlined" disabled={busy} onClick={refresh}>
                Refresh
              </Button>
            </Box>
            <Box height={520}>
              <DataGrid
                rows={transactions}
                columns={columns}
                disableRowSelectionOnClick
                loading={busy}
                getRowId={(row) => row.id}
                pageSizeOptions={[10, 25, 50]}
                initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
              />
            </Box>
          </CardContent>
        </Card>
      </Container>

      <Dialog open={repayOpen} onClose={() => setRepayOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Repay loan</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1, mb: 2 }}>
            Repayments apply to interest first, then principal. Loan interest is distributed to members based on contributions.
          </Typography>
          <TextField
            label="Amount"
            type="number"
            fullWidth
            value={repayAmount}
            onChange={(e) => setRepayAmount(Number(e.target.value))}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRepayOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!membershipAccepted || !repayLoanId || repayAmount <= 0}
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
              <TextField
                label="Principal"
                type="number"
                fullWidth
                value={requestDraft.principal}
                onChange={(e) => setRequestDraft((p) => ({ ...p, principal: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                label="Term (months)"
                type="number"
                fullWidth
                value={requestDraft.term_months ?? 1}
                onChange={(e) => setRequestDraft((p) => ({ ...p, term_months: Number(e.target.value) }))}
              />
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
              <TextField
                label="Description (optional)"
                fullWidth
                value={requestDraft.description ?? ""}
                onChange={(e) => setRequestDraft((p) => ({ ...p, description: e.target.value }))}
              />
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
              } catch (err) {
                onError(err instanceof Error ? err.message : "Failed to request loan");
              }
            }}
          >
            Submit request
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
