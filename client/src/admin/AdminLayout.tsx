import { useEffect, useMemo, useState } from "react";
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
  Snackbar,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import GroupIcon from "@mui/icons-material/Group";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import ChecklistIcon from "@mui/icons-material/Checklist";
import GavelIcon from "@mui/icons-material/Gavel";
import AddIcon from "@mui/icons-material/Add";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";

import { Api } from "../api";
import { AppShell, type NavItem } from "../layout/AppShell";
import { StatCard } from "../components/StatCard";
import { currency } from "../lib/format";
import { useColorMode } from "../colorMode";
import { AdminContext, type AdminContextValue } from "./adminContext";
import type {
  Account,
  DashboardStats,
  Group,
  GroupContributionItem,
  GroupSettingsUpdatePayload,
  GroupWithSettings,
  Loan,
  LoanCreatePayload,
  LoanRequest,
  MemberInvitePayload,
  User,
} from "../types";

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
  const [contributions, setContributions] = useState<GroupContributionItem[]>([]);
  const [dashboard, setDashboard] = useState<DashboardStats | null>(null);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [requests, setRequests] = useState<LoanRequest[]>([]);
  const [busy, setBusy] = useState(false);

  // Confirmation for actions whose result is not visible on screen — a payment
  // prompt sent to a member's handset, for instance.
  const [notice, setNotice] = useState<string | null>(null);
  const onNotice = (msg: string) => setNotice(msg);

  const [createGroupOpen, setCreateGroupOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");

  const [inviteOpen, setInviteOpen] = useState(false);
  const [invite, setInvite] = useState<MemberInvitePayload>({
    email: "",
    full_name: "",
    password: "",
    name: "",
    phone_number: "",
    min_initial_deposit: 0,
    collect_initial_contribution: false,
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
        setContributions([]);
        setDashboard(null);
        setLoans([]);
        setRequests([]);
        return;
      }

      setSelectedGroupId(resolved);
      localStorage.setItem(GROUP_STORAGE_KEY, String(resolved));

      const [details, accounts, contrib, stats, groupLoans, loanRequests] = await Promise.all([
        Api.getGroup(resolved),
        Api.getGroupAccounts(resolved),
        Api.getGroupContributions(resolved).catch(() => []),
        Api.getDashboardForGroup(resolved).catch(() => null),
        Api.getGroupLoans(resolved),
        Api.listLoanRequests(resolved),
      ]);
      setGroup(details);
      setMembers(accounts);
      setContributions(contrib);
      setDashboard(stats);
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
    </>
  );

  const navItems: NavItem[] = useMemo(
    () => [
      { to: "/admin/overview", label: "Overview", icon: <DashboardIcon /> },
      { to: "/admin/members", label: "Members", icon: <GroupIcon />, badge: members.length },
      { to: "/admin/loans", label: "Loans", icon: <CreditCardIcon />, badge: activeLoansCount },
      { to: "/admin/requests", label: "Requests", icon: <ChecklistIcon />, badge: pendingRequestsCount },
      { to: "/admin/settings", label: "Constitution", icon: <GavelIcon />, badge: constitutionLocked ? "" : "!" },
      // An action, not a destination. Only available while the constitution is
      // open — once it is locked, lending is autonomous and a hand-written loan
      // would sidestep the rules the group just agreed to.
      {
        label: "Manual loan",
        icon: <CreditCardIcon />,
        onClick: openManualLoan,
        disabled: !selectedGroupId || constitutionLocked,
      },
    ],
    [activeLoansCount, constitutionLocked, members.length, pendingRequestsCount, selectedGroupId]
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
    contributions,
    dashboard,
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
                  <StatCard
                    label="Members"
                    value={`${members.length}`}
                    icon={<GroupIcon color="action" />}
                    loading={busy}
                    helper={members.length < 5 ? "Min 5 recommended" : "Active group"}
                  />
                </Grid>
                <Grid item xs={12} md={3}>
                  <StatCard
                    label="Total savings"
                    value={currency(totalSavings)}
                    icon={<DashboardIcon color="action" />}
                    loading={busy}
                    helper={totalSavings <= 0 ? "Start collecting to lend" : "Pool ready"}
                  />
                </Grid>
                <Grid item xs={12} md={3}>
                  <StatCard
                    label="Active loans"
                    value={`${activeLoansCount}`}
                    icon={<CreditCardIcon color="action" />}
                    loading={busy}
                    helper={constitutionLocked ? "Autonomous lending" : "Lock to enable"}
                  />
                </Grid>
                <Grid item xs={12} md={3}>
                  <StatCard
                    label="Pending requests"
                    value={`${pendingRequestsCount}`}
                    icon={<ChecklistIcon color="action" />}
                    loading={busy}
                    helper={constitutionLocked ? "Auto decisions on" : "Requests open after lock"}
                  />
                </Grid>
              </Grid>

            <Outlet />
          </>
        )}

        <Snackbar
          open={Boolean(notice)}
          autoHideDuration={8000}
          onClose={() => setNotice(null)}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        >
          <Alert severity="info" onClose={() => setNotice(null)} sx={{ width: "100%" }}>
            {notice}
          </Alert>
        </Snackbar>

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
            {/* These fields describe someone else, not whoever is signed in. Left
                unmarked, the browser reads an email beside a password as a login
                form and fills the admin's own saved credentials — which would
                hand a new member the admin's password. `new-password` breaks the
                username/password pairing the password manager looks for. */}
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid item xs={12} md={6}>
                <TextField label="Member name" fullWidth name="member-name" autoComplete="off" value={invite.name} onChange={(e) => setInvite((p) => ({ ...p, name: e.target.value }))} />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField label="Email" fullWidth name="member-email" autoComplete="off" value={invite.email} onChange={(e) => setInvite((p) => ({ ...p, email: e.target.value }))} />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField label="Full name (optional)" fullWidth name="member-full-name" autoComplete="off" value={invite.full_name ?? ""} onChange={(e) => setInvite((p) => ({ ...p, full_name: e.target.value }))} />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField label="Temporary password" fullWidth type="password" name="member-temp-password" autoComplete="new-password" value={invite.password} onChange={(e) => setInvite((p) => ({ ...p, password: e.target.value }))} />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  label="Mobile number"
                  fullWidth
                  name="member-phone"
                  autoComplete="off"
                  placeholder="0977123456"
                  value={invite.phone_number ?? ""}
                  onChange={(e) => setInvite((p) => ({ ...p, phone_number: e.target.value }))}
                  helperText="Airtel, MTN or Zamtel. Used to collect contributions."
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField label="Initial contribution" fullWidth type="number" name="member-initial" autoComplete="off" value={invite.min_initial_deposit ?? 0} onChange={(e) => setInvite((p) => ({ ...p, min_initial_deposit: Number(e.target.value) }))} />
              </Grid>
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={invite.collect_initial_contribution ?? false}
                      onChange={(e) => setInvite((p) => ({ ...p, collect_initial_contribution: e.target.checked }))}
                    />
                  }
                  label="Request the contribution now"
                />
                <Typography variant="caption" color="text.secondary" display="block">
                  {invite.collect_initial_contribution
                    ? "The member gets a prompt on their phone. Their savings update only once they approve it."
                    : "The amount is recorded as owed. Collect it from the members list whenever they are ready."}
                </Typography>
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setInviteOpen(false)}>Cancel</Button>
            <Button
              variant="contained"
              disabled={
                busy ||
                !selectedGroupId ||
                !invite.name.trim() ||
                !invite.email.trim() ||
                !invite.password ||
                (invite.collect_initial_contribution &&
                  (!invite.phone_number?.trim() || !(invite.min_initial_deposit && invite.min_initial_deposit > 0)))
              }
              onClick={async () => {
                try {
                  const result = await Api.addGroupMember(Number(selectedGroupId), invite);
                  setInviteOpen(false);
                  setInvite({ email: "", full_name: "", password: "", name: "", phone_number: "", min_initial_deposit: 0, collect_initial_contribution: false, custom_fields: {} });
                  await refresh(Number(selectedGroupId));
                  if (result.payment) {
                    onNotice(
                      `Member added. A prompt for ${currency(result.payment.amount)} was sent to their phone — their savings update once they approve it.`,
                    );
                  } else if (result.initial_contribution_due) {
                    onNotice(
                      `Member added. ${currency(result.initial_contribution_due)} is recorded as owed — collect it from the members list when they are ready.`,
                    );
                  }
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
