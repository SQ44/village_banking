import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Switch,
  TextField,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import GroupIcon from "@mui/icons-material/Group";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import ChecklistIcon from "@mui/icons-material/Checklist";
import GavelIcon from "@mui/icons-material/Gavel";
import AddIcon from "@mui/icons-material/Add";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";

import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { Api } from "../api";
import { ScorecardDialog, type ScorecardItem } from "../components/ScorecardDialog";
import { PageHeader } from "../components/PageHeader";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { AppShell, type NavItem } from "../layout/AppShell";
import { StatCard } from "../components/StatCard";
import { StatusChip } from "../components/StatusChip";
import { currency, formatDateTime } from "../lib/format";
import { useColorMode } from "../colorMode";
import type {
  Account,
  Group,
  GroupSettingsUpdatePayload,
  GroupWithSettings,
  Loan,
  LoanCreatePayload,
  LoanRequest,
  MemberInvitePayload,
  User,
} from "../types";

type AdminContextValue = {
  busy: boolean;
  groups: Group[];
  selectedGroupId: number | "";
  group: GroupWithSettings | null;
  members: Account[];
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

const AdminContext = createContext<AdminContextValue | null>(null);

export function useAdmin() {
  const ctx = useContext(AdminContext);
  if (!ctx) throw new Error("useAdmin must be used inside AdminLayout");
  return ctx;
}

const GROUP_STORAGE_KEY = "vb_selected_group";

export function AdminLayout({
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

  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<number | "">(() => {
    const saved = localStorage.getItem(GROUP_STORAGE_KEY);
    const num = saved ? Number(saved) : NaN;
    return Number.isFinite(num) ? num : "";
  });
  const [group, setGroup] = useState<GroupWithSettings | null>(null);
  const [members, setMembers] = useState<Account[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [requests, setRequests] = useState<LoanRequest[]>([]);
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

  const constitutionLocked = Boolean(group?.settings?.constitution_locked_at);
  const totalSavings = members.reduce((sum, member) => sum + Number(member.balance), 0);
  const activeLoansCount = loans.filter((loan) => loan.status === "active").length;
  const pendingRequestsCount = requests.filter((req) => req.status === "requested" || req.status === "queued").length;

  const refresh = async (groupId?: number) => {
    setBusy(true);
    try {
      const groupList = await Api.getGroups();
      setGroups(groupList);

      const resolved = groupId ?? (selectedGroupId === "" ? groupList[0]?.id : Number(selectedGroupId));
      if (!resolved) {
        setSelectedGroupId("");
        setGroup(null);
        setMembers([]);
        setLoans([]);
        setRequests([]);
        return;
      }

      setSelectedGroupId(resolved);
      localStorage.setItem(GROUP_STORAGE_KEY, String(resolved));

      const [details, accounts, groupLoans, loanRequests] = await Promise.all([
        Api.getGroup(resolved),
        Api.getGroupAccounts(resolved),
        Api.getGroupLoans(resolved),
        Api.listLoanRequests(resolved),
      ]);
      setGroup(details);
      setMembers(accounts);
      setLoans(groupLoans);
      setRequests(loanRequests);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load admin console");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openCreateGroup = () => setCreateGroupOpen(true);
  const openInvite = () => setInviteOpen(true);
  const openManualLoan = () => setLoanOpen(true);

  const saveSettings = async (payload: GroupSettingsUpdatePayload) => {
    if (!selectedGroupId) return;
    try {
      const updated = await Api.updateGroupSettings(Number(selectedGroupId), payload);
      setGroup((prev) => (prev ? { ...prev, settings: updated } : prev));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to save settings");
    }
  };

  const lockConstitution = async () => {
    if (!selectedGroupId) return;
    try {
      const updated = await Api.lockGroupConstitution(Number(selectedGroupId));
      setGroup((prev) => (prev ? { ...prev, settings: updated } : prev));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to lock constitution");
    }
  };

  const header = (
    <Box display="flex" alignItems="center" gap={1} width="100%" minWidth={0}>
      <Box minWidth={260} maxWidth={520} flex={1}>
        <Autocomplete
          size="small"
          options={groups}
          value={groups.find((g) => g.id === Number(selectedGroupId)) ?? null}
          getOptionLabel={(option) => option.name}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          disableClearable={groups.length > 0}
          onChange={(_, value) => void refresh(value?.id)}
          renderInput={(params) => <TextField {...params} label="Group" placeholder="Search groups..." />}
          slotProps={{
            popper: { sx: { zIndex: (t) => t.zIndex.modal + 1 } },
            paper: { sx: { borderRadius: 2, mt: 1, border: "1px solid rgba(15, 23, 42, 0.10)" } },
          }}
          sx={{
            "& .MuiOutlinedInput-root": {
              backgroundColor: "background.paper",
              borderRadius: 2,
              boxShadow: "0 1px 2px rgba(15,23,42,0.06)",
            },
          }}
        />
      </Box>
      {selectedGroupId && (
        <Chip
          size="small"
          label={constitutionLocked ? "Constitution locked" : "Constitution unlocked"}
          color={constitutionLocked ? "success" : "warning"}
          variant={constitutionLocked ? "filled" : "outlined"}
        />
      )}
    </Box>
  );

  const actions = (
    <>
      <Button
        startIcon={<AddIcon />}
        variant="contained"
        onClick={openCreateGroup}
        aria-label="New group"
        sx={{ "& .MuiButton-startIcon": { mr: { xs: 0, sm: 1 } } }}
      >
        <Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>
          New group
        </Box>
      </Button>
      <Button
        startIcon={<PersonAddAlt1Icon />}
        variant="outlined"
        disabled={!selectedGroupId}
        onClick={openInvite}
        aria-label="Add member"
        sx={{ "& .MuiButton-startIcon": { mr: { xs: 0, sm: 1 } } }}
      >
        <Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>
          Add member
        </Box>
      </Button>
      <Button
        startIcon={<CreditCardIcon />}
        variant="outlined"
        disabled={!selectedGroupId || constitutionLocked}
        onClick={openManualLoan}
        aria-label="Manual loan"
        sx={{ "& .MuiButton-startIcon": { mr: { xs: 0, sm: 1 } } }}
      >
        <Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>
          Manual loan
        </Box>
      </Button>
    </>
  );

  const navItems: NavItem[] = useMemo(
    () => [
      { to: "/admin/overview", label: "Overview", icon: <DashboardIcon /> },
      { to: "/admin/members", label: "Members", icon: <GroupIcon />, badge: members.length },
      { to: "/admin/loans", label: "Loans", icon: <CreditCardIcon />, badge: activeLoansCount },
      { to: "/admin/requests", label: "Requests", icon: <ChecklistIcon />, badge: pendingRequestsCount },
      { to: "/admin/settings", label: "Constitution", icon: <GavelIcon />, badge: constitutionLocked ? "" : "!" },
    ],
    [activeLoansCount, constitutionLocked, members.length, pendingRequestsCount]
  );

  useEffect(() => {
    // Ensure the user always lands on a valid route.
    if (location.pathname === "/admin" || location.pathname === "/admin/") {
      navigate("/admin/overview", { replace: true });
    }
  }, [location.pathname, navigate]);

  const ctx: AdminContextValue = {
    busy,
    groups,
    selectedGroupId,
    group,
    members,
    loans,
    requests,
    constitutionLocked,
    refresh,
    openInvite,
    openManualLoan,
    openCreateGroup,
    saveSettings,
    lockConstitution,
  };

  return (
    <AdminContext.Provider value={ctx}>
      <AppShell
        title="Admin Console"
        user={currentUser}
        navItems={navItems}
        header={header}
        actions={actions}
        colorMode={mode}
        onToggleColorMode={toggle}
        onLogout={onLogout}
      >
        {!selectedGroupId ? (
          <Alert severity="info">Create a group to get started.</Alert>
        ) : (
          <>
            {!constitutionLocked && (
              <Alert
                severity="warning"
                sx={{ mb: 2 }}
                action={
                  <Button color="inherit" size="small" onClick={() => navigate("/admin/settings")}>
                    Review constitution
                  </Button>
                }
              >
                Lock the constitution to enable autonomous lending (members cannot request loans until it is locked).
              </Alert>
            )}

              <Grid container spacing={2} sx={{ mb: 2 }}>
                <Grid item xs={12} md={3}>
                  <StatCard label="Members" value={`${members.length}`} icon={<GroupIcon color="action" />} loading={busy} />
                </Grid>
                <Grid item xs={12} md={3}>
                  <StatCard label="Total savings" value={currency(totalSavings)} icon={<DashboardIcon color="action" />} loading={busy} />
                </Grid>
                <Grid item xs={12} md={3}>
                  <StatCard label="Active loans" value={`${activeLoansCount}`} icon={<CreditCardIcon color="action" />} loading={busy} />
                </Grid>
                <Grid item xs={12} md={3}>
                  <StatCard label="Pending requests" value={`${pendingRequestsCount}`} icon={<ChecklistIcon color="action" />} loading={busy} />
                </Grid>
              </Grid>

            <Outlet />
          </>
        )}

        <Dialog open={createGroupOpen} onClose={() => setCreateGroupOpen(false)} fullWidth maxWidth="sm">
          <DialogTitle>Create group</DialogTitle>
          <DialogContent>
            <TextField label="Group name" fullWidth value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)} sx={{ mt: 1 }} />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setCreateGroupOpen(false)}>Cancel</Button>
            <Button
              variant="contained"
              disabled={!newGroupName.trim() || busy}
              onClick={async () => {
                try {
                  const created = await Api.createGroup({
                    name: newGroupName.trim(),
                    terms: "By joining, you agree to contribute as scheduled and repay loans on time.",
                  });
                  setCreateGroupOpen(false);
                  setNewGroupName("");
                  await refresh(created.id);
                  navigate("/admin/settings");
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
                <TextField label="Initial contribution" fullWidth type="number" value={invite.min_initial_deposit ?? 0} onChange={(e) => setInvite((p) => ({ ...p, min_initial_deposit: Number(e.target.value) }))} />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setInviteOpen(false)}>Cancel</Button>
            <Button
              variant="contained"
              disabled={busy || !selectedGroupId || !invite.name.trim() || !invite.email.trim() || !invite.password}
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
          <DialogTitle>Create manual loan</DialogTitle>
          <DialogContent>
            <Alert severity="info" sx={{ mt: 1, mb: 2 }}>
              Manual loans are disabled once the constitution is locked (autonomous lending).
            </Alert>
            <Grid container spacing={2}>
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
              disabled={!selectedGroupId || constitutionLocked || busy || !loanDraft.borrower_account_id || loanDraft.principal <= 0}
              onClick={async () => {
                try {
                  await Api.createLoan(Number(selectedGroupId), loanDraft);
                  setLoanOpen(false);
                  setLoanDraft({ borrower_account_id: 0, principal: 0, term_months: 3, repayment_frequency: "monthly", description: "" });
                  await refresh(Number(selectedGroupId));
                  navigate("/admin/loans");
                } catch (err) {
                  onError(err instanceof Error ? err.message : "Failed to create loan");
                }
              }}
            >
              Create
            </Button>
          </DialogActions>
        </Dialog>
      </AppShell>
    </AdminContext.Provider>
  );
}

export function AdminOverviewPage() {
  const { group, constitutionLocked } = useAdmin();
  if (!group) return null;
  return (
    <Box>
      <PageHeader
        title={group.name}
        subtitle={
          constitutionLocked
            ? `Constitution locked at ${formatDateTime(group.settings.constitution_locked_at)}`
            : "Constitution is not locked yet. Lock it to enable autonomous lending."
        }
      />
    </Box>
  );
}

export function AdminMembersPage() {
  const { busy, members, openInvite } = useAdmin();
  const columns: GridColDef<Account>[] = useMemo(
    () => [
      { field: "name", headerName: "Member", flex: 1, minWidth: 180 },
      { field: "email", headerName: "Email", flex: 1, minWidth: 220 },
      { field: "balance", headerName: "Savings", minWidth: 140, valueFormatter: (v) => currency(Number(v)) },
    ],
    []
  );
  return (
    <Box>
      <PageHeader
        title="Members"
        subtitle="Manage membership for this group."
        action={
          <Button variant="contained" startIcon={<PersonAddAlt1Icon />} onClick={openInvite}>
            Add member
          </Button>
        }
      />
      {members.length === 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>
          No members yet. Add your first member to start contributions and enable lending.
        </Alert>
      )}
      <Box height={520}>
        <DataGrid
          rows={members}
          columns={columns}
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } }, density: "compact" }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
      </Box>
    </Box>
  );
}

export function AdminLoansPage() {
  const { busy, loans, constitutionLocked, openManualLoan, members } = useAdmin();
  const memberNameByAccountId = useMemo(() => {
    const map = new Map<number, string>();
    for (const m of members) map.set(Number(m.id), m.name);
    return map;
  }, [members]);
  const columns: GridColDef<Loan>[] = useMemo(
    () => [
      { field: "id", headerName: "Loan", width: 90 },
      {
        field: "borrower_account_id",
        headerName: "Borrower",
        width: 200,
        valueGetter: (_, row) => memberNameByAccountId.get(Number(row.borrower_account_id)) ?? `Account ${row.borrower_account_id}`,
      },
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
    [memberNameByAccountId]
  );
  return (
    <Box>
      <PageHeader
        title="Loans"
        subtitle="View active and historical loans."
        action={
          <Button variant="contained" startIcon={<CreditCardIcon />} disabled={constitutionLocked} onClick={openManualLoan}>
            Manual loan
          </Button>
        }
      />
      {constitutionLocked && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Manual loans are disabled because the constitution is locked (autonomous lending).
        </Alert>
      )}
      <Box height={520}>
        <DataGrid
          rows={loans}
          columns={columns}
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } }, density: "compact" }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
      </Box>
    </Box>
  );
}

export function AdminRequestsPage() {
  const { busy, requests, members } = useAdmin();
  const [scorecardOpen, setScorecardOpen] = useState(false);
  const [scorecard, setScorecard] = useState<ScorecardItem[] | null>(null);

  const memberNameByAccountId = useMemo(() => {
    const map = new Map<number, string>();
    for (const m of members) map.set(Number(m.id), m.name);
    return map;
  }, [members]);

  const columns: GridColDef<LoanRequest>[] = useMemo(
    () => [
      { field: "id", headerName: "Request", width: 110 },
      {
        field: "borrower_account_id",
        headerName: "Borrower",
        width: 200,
        valueGetter: (_, row) => memberNameByAccountId.get(Number(row.borrower_account_id)) ?? `Account ${row.borrower_account_id}`,
      },
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
      { field: "decision_reason", headerName: "Reason", flex: 1, minWidth: 240, valueGetter: (_, row) => row.decision_reason ?? "" },
      { field: "created_at", headerName: "Created", width: 170, valueFormatter: (v) => formatDateTime(String(v)) },
    ],
    [memberNameByAccountId]
  );
  return (
    <Box>
      <PageHeader title="Requests" subtitle="Auto-decisions (approve/reject/queue) with transparent reasons." />
      <Alert severity="info" sx={{ mb: 2 }}>
        Requests are auto-approved, rejected, or queued by the constitution. There is no manual approval step.
      </Alert>
      <Box height={520}>
        <DataGrid
          rows={requests}
          columns={columns}
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } }, density: "compact" }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
      </Box>
      <ScorecardDialog open={scorecardOpen} onClose={() => setScorecardOpen(false)} scorecard={scorecard} />
    </Box>
  );
}

export function AdminSettingsPage() {
  const { group, busy, constitutionLocked, saveSettings, lockConstitution } = useAdmin();
  const [draft, setDraft] = useState<GroupSettingsUpdatePayload>(() => ({}));
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (!group) return;
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

  if (!group) return null;

  return (
    <Box>
      <PageHeader
        title="Constitution (cycle rules)"
        subtitle={
          constitutionLocked
            ? `Locked at ${formatDateTime(group.settings.constitution_locked_at)}. Only corrections via reversals are allowed.`
            : "Set rules for this cycle, then lock them to enable autonomous lending."
        }
      />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <TextField label="Minimum monthly contribution" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.min_monthly_contribution ?? 0} onChange={(e) => setDraft((p) => ({ ...p, min_monthly_contribution: Number(e.target.value) }))} />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField label="Admin fee (% of loan interest)" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.admin_fee_percent ?? 0} onChange={(e) => setDraft((p) => ({ ...p, admin_fee_percent: Number(e.target.value) }))} />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField label="Loan interest (%)" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.loan_interest_percent ?? 10} onChange={(e) => setDraft((p) => ({ ...p, loan_interest_percent: Number(e.target.value) }))} />
        </Grid>
        <Grid item xs={12} md={6}>
          <FormControlLabel
            control={<Switch checked={draft.enforce_loan_limit ?? true} disabled={busy || constitutionLocked} onChange={(e) => setDraft((p) => ({ ...p, enforce_loan_limit: e.target.checked }))} />}
            label="Enforce loan limit"
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField label="Loan limit multiplier" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.loan_limit_multiplier ?? 2} onChange={(e) => setDraft((p) => ({ ...p, loan_limit_multiplier: Number(e.target.value) }))} helperText={(draft.enforce_loan_limit ?? true) ? "Max loan = contribution x multiplier" : "Loan limit disabled"} />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField label="Liquidity cap (% outstanding)" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.liquidity_max_outstanding_percent ?? 80} onChange={(e) => setDraft((p) => ({ ...p, liquidity_max_outstanding_percent: Number(e.target.value) }))} helperText="Total outstanding principal must stay below this % of the pool" />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField label="Min term (months)" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.min_term_months ?? 1} onChange={(e) => setDraft((p) => ({ ...p, min_term_months: Number(e.target.value) }))} />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField label="Max term (months)" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.max_term_months ?? 12} onChange={(e) => setDraft((p) => ({ ...p, max_term_months: Number(e.target.value) }))} />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField label="Max active loans per member" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.max_active_loans_per_member ?? 1} onChange={(e) => setDraft((p) => ({ ...p, max_active_loans_per_member: Number(e.target.value) }))} />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField label="Cooldown after settlement (days)" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.cooldown_days_after_settlement ?? 0} onChange={(e) => setDraft((p) => ({ ...p, cooldown_days_after_settlement: Number(e.target.value) }))} />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField label="Withdrawal cycle (days)" type="number" fullWidth disabled={busy || constitutionLocked} value={draft.withdrawal_cycle_days ?? 30} onChange={(e) => setDraft((p) => ({ ...p, withdrawal_cycle_days: Number(e.target.value) }))} />
        </Grid>
        <Grid item xs={12} md={6}>
          <FormControlLabel
            control={<Switch checked={draft.allow_advance_contribution ?? true} disabled={busy || constitutionLocked} onChange={(e) => setDraft((p) => ({ ...p, allow_advance_contribution: e.target.checked }))} />}
            label="Allow advance contributions"
          />
        </Grid>
      </Grid>

      <Box display="flex" justifyContent="space-between">
        <Button
          variant="outlined"
          color="warning"
          disabled={busy || constitutionLocked}
          onClick={() => setConfirmOpen(true)}
        >
          Lock constitution
        </Button>
        <Button variant="contained" disabled={busy || constitutionLocked} onClick={() => void saveSettings(draft)}>
          Save
        </Button>
      </Box>

      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Lock constitution?"
        description="This locks the rules for the cycle. Members can request loans, and decisions become fully automatic. You cannot edit these settings after locking."
        confirmLabel="Lock"
        confirmColor="warning"
        busy={busy}
        onConfirm={async () => {
          setConfirmOpen(false);
          await lockConstitution();
        }}
      />
    </Box>
  );
}
