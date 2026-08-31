import { useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  InputLabel,
  Menu,
  MenuItem,
  Select,
  Snackbar,
  TextField,
  Typography,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import GroupIcon from "@mui/icons-material/Group";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import ChecklistIcon from "@mui/icons-material/Checklist";
import GavelIcon from "@mui/icons-material/Gavel";
import AccountBalanceIcon from "@mui/icons-material/AccountBalance";
import ReportProblemIcon from "@mui/icons-material/ReportProblem";
import AddIcon from "@mui/icons-material/Add";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";

import { Api } from "../api";
import { AppShell, type NavItem } from "../layout/AppShell";
import { currency } from "../lib/format";
import { useColorMode } from "../colorMode";
import { AdminContext, type AdminContextValue } from "./adminContext";
import { isSystemAdmin } from "../types";
import type {
  Account,
  DashboardStats,
  Group,
  GroupContributionItem,
  GroupPerformance,
  GroupSettingsUpdatePayload,
  GroupWithSettings,
  Loan,
  LoanCreatePayload,
  LoanRequest,
  ContributionMethod,
  MemberInvitePayload,
  Membership,
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
  const systemAdmin = isSystemAdmin(currentUser);
  const [groupMenu, setGroupMenu] = useState<HTMLElement | null>(null);

  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<number | "">(() => {
    const saved = localStorage.getItem(GROUP_STORAGE_KEY);
    const num = saved ? Number(saved) : NaN;
    return Number.isFinite(num) ? num : "";
  });
  const [group, setGroup] = useState<GroupWithSettings | null>(null);
  const [members, setMembers] = useState<Account[]>([]);
  // Roles live on the membership, not the account, so who runs the group is a
  // separate read from who has money in it.
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [contributions, setContributions] = useState<GroupContributionItem[]>([]);
  const [dashboard, setDashboard] = useState<DashboardStats | null>(null);
  const [performance, setPerformance] = useState<GroupPerformance | null>(null);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [requests, setRequests] = useState<LoanRequest[]>([]);
  // How many things currently need a person. Loaded with everything else so the
  // sidebar badge is right on any page, not just the attention page itself.
  const [attentionCount, setAttentionCount] = useState(0);
  const [busy, setBusy] = useState(false);

  // Confirmation for actions whose result is not visible on screen — a payment
  // prompt sent to a member's handset, for instance.
  const [notice, setNotice] = useState<string | null>(null);
  const onNotice = (msg: string) => setNotice(msg);

  const [createGroupOpen, setCreateGroupOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [createGroupError, setCreateGroupError] = useState<string | null>(null);
  // Route to visit once the current commit is done. See submitCreateGroup.
  const [pendingRoute, setPendingRoute] = useState<string | null>(null);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [invite, setInvite] = useState<MemberInvitePayload>({
    email: "",
    full_name: "",
    password: "",
    name: "",
    phone_number: "",
    min_initial_deposit: 0,
    initial_contribution_method: "defer",
    cash_reason: "",
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

  const contributionMethod: ContributionMethod = invite.initial_contribution_method ?? "defer";
  const constitutionLocked = Boolean(group?.settings?.constitution_locked_at);
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
        setMemberships([]);
        setContributions([]);
        setDashboard(null);
        setPerformance(null);
        setLoans([]);
        setRequests([]);
        setAttentionCount(0);
        return;
      }

      setSelectedGroupId(resolved);
      localStorage.setItem(GROUP_STORAGE_KEY, String(resolved));

      const [details, accounts, roles, contrib, stats, perf, groupLoans, loanRequests, attention] = await Promise.all([
        Api.getGroup(resolved),
        Api.getGroupAccounts(resolved),
        Api.getGroupMembers(resolved).catch(() => []),
        Api.getGroupContributions(resolved).catch(() => []),
        Api.getDashboardForGroup(resolved).catch(() => null),
        Api.getGroupPerformance(resolved).catch(() => null),
        Api.getGroupLoans(resolved),
        Api.listLoanRequests(resolved),
        // Never fatal: a failure here must not blank the whole console.
        Api.getAttention(resolved).catch(() => null),
      ]);
      setGroup(details);
      setMembers(accounts);
      setMemberships(roles);
      setContributions(contrib);
      setDashboard(stats);
      setPerformance(perf);
      setLoans(groupLoans);
      setRequests(loanRequests);
      setAttentionCount(
        attention
          ? attention.stuck_payments.length +
              attention.dead_letter_events.length +
              attention.balance_discrepancies.length +
              attention.negative_balances.length
          : 0
      );
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

  const openCreateGroup = () => {
    // Always open onto a clean form. A previous attempt's name or error has
    // nothing to do with this one.
    setNewGroupName("");
    setCreateGroupError(null);
    setCreateGroupOpen(true);
  };
  const closeCreateGroup = () => {
    setCreateGroupOpen(false);
    setCreateGroupError(null);
  };
  const openInvite = () => setInviteOpen(true);
  const openManualLoan = () => setLoanOpen(true);

  const submitCreateGroup = async () => {
    const name = newGroupName.trim();
    if (!name || creatingGroup) return;
    setCreatingGroup(true);
    setCreateGroupError(null);
    try {
      const created = await Api.createGroup({
        name,
        terms: "By joining, you agree to contribute as scheduled and repay loans on time.",
      });
      // Close before anything that can suspend. Navigating in the same pass as
      // the close let an interrupted render discard it, leaving the dialog open
      // over a group that had in fact been created — and looking, to whoever
      // was using it, like a second prompt that would not go away.
      setCreateGroupOpen(false);
      setNewGroupName("");
      await refresh(created.id);
      setPendingRoute("/admin/settings");
    } catch (err) {
      setCreateGroupError(err instanceof Error ? err.message : "Failed to create group");
    } finally {
      setCreatingGroup(false);
    }
  };

  // Navigation runs in its own commit, once the dialog has already closed.
  useEffect(() => {
    if (!pendingRoute) return;
    setPendingRoute(null);
    navigate(pendingRoute);
  }, [navigate, pendingRoute]);

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

  // Switching groups is a system administrator's job. A group administrator has
  // exactly one group, so a picker offering it back to them is noise.
  //
  // The switcher deliberately does not restate the current group: its name is
  // the sidebar heading, and repeating it in the top bar put the same words on
  // screen twice with nothing to tell them apart.
  const header = (
    <Box display="flex" alignItems="center" gap={1.5} width="100%" minWidth={0}>
      {systemAdmin && groups.length > 1 ? (
        <Button
          size="small"
          color="inherit"
          startIcon={<SwapHorizIcon />}
          onClick={(e) => setGroupMenu(e.currentTarget)}
          sx={{ color: "text.secondary", flexShrink: 0 }}
        >
          Switch group
        </Button>
      ) : null}
      <Menu open={Boolean(groupMenu)} anchorEl={groupMenu} onClose={() => setGroupMenu(null)}>
        {groups.map((option) => (
          <MenuItem
            key={option.id}
            selected={option.id === Number(selectedGroupId)}
            onClick={() => {
              setGroupMenu(null);
              void refresh(option.id);
            }}
          >
            {option.name}
          </MenuItem>
        ))}
      </Menu>
      <Box flex={1} minWidth={0} />
      {selectedGroupId && !constitutionLocked && (
        <Chip size="small" label="Constitution not locked" color="warning" variant="outlined" />
      )}
    </Box>
  );

  const actions = (
    <>
      {systemAdmin && (
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
      )}
      <Button
        startIcon={<PersonAddAlt1Icon />}
        variant={systemAdmin ? "outlined" : "contained"}
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
      { to: "/admin/money", label: "Money", icon: <AccountBalanceIcon /> },
      { to: "/admin/settings", label: "Constitution", icon: <GavelIcon />, badge: constitutionLocked ? undefined : "!" },
      // Stuck payments and unexplained balances. Carries its own count so a
      // member's money sitting in limbo is visible from every page, rather than
      // only to whoever thinks to go looking for it.
      {
        to: "/admin/attention",
        label: "Needs attention",
        icon: <ReportProblemIcon />,
        badge: attentionCount || undefined,
      },
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
    [activeLoansCount, attentionCount, constitutionLocked, members.length, pendingRequestsCount, selectedGroupId]
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
    memberships,
    contributions,
    dashboard,
    performance,
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
        title={group?.name ?? "Admin Console"}
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

        <Dialog open={createGroupOpen} onClose={closeCreateGroup} fullWidth maxWidth="sm">
          <DialogTitle>Create group</DialogTitle>
          <DialogContent>
            {/* Reported inside the dialog rather than as a toast. A failure
                leaves the dialog open, and a message that vanishes after six
                seconds left it looking stuck for no visible reason. */}
            {createGroupError && (
              <Alert severity="error" sx={{ mt: 1 }} onClose={() => setCreateGroupError(null)}>
                {createGroupError}
              </Alert>
            )}
            <TextField
              label="Group name"
              fullWidth
              autoFocus
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newGroupName.trim() && !creatingGroup) {
                  e.preventDefault();
                  void submitCreateGroup();
                }
              }}
              sx={{ mt: 1 }}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={closeCreateGroup} disabled={creatingGroup}>
              Cancel
            </Button>
            <Button
              variant="contained"
              disabled={!newGroupName.trim() || creatingGroup}
              onClick={() => void submitCreateGroup()}
            >
              {creatingGroup ? "Creating..." : "Create"}
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
              <Grid item xs={12} md={6}>
                <FormControl fullWidth>
                  <InputLabel id="contribution-method-label">Initial contribution</InputLabel>
                  <Select
                    labelId="contribution-method-label"
                    label="Initial contribution"
                    value={contributionMethod}
                    onChange={(e) =>
                      setInvite((p) => ({ ...p, initial_contribution_method: e.target.value as ContributionMethod }))
                    }
                  >
                    <MenuItem value="defer">Collect later</MenuItem>
                    <MenuItem value="lipila">Request on their phone</MenuItem>
                    <MenuItem value="cash">Cash received</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              {contributionMethod === "cash" && (
                <Grid item xs={12} md={6}>
                  <TextField
                    label="Reason"
                    fullWidth
                    name="cash-reason"
                    autoComplete="off"
                    placeholder="Cash handed over at the meeting"
                    value={invite.cash_reason ?? ""}
                    onChange={(e) => setInvite((p) => ({ ...p, cash_reason: e.target.value }))}
                    helperText="Recorded against your name in the audit log."
                  />
                </Grid>
              )}
              <Grid item xs={12}>
                <Typography variant="caption" color="text.secondary" display="block">
                  {contributionMethod === "lipila"
                    ? "The member gets a prompt on their phone. Their savings update only once they approve it."
                    : contributionMethod === "cash"
                      ? "Banked immediately on your word — no provider confirms it, so the reason is kept on the record."
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
                (contributionMethod !== "defer" && !(invite.min_initial_deposit && invite.min_initial_deposit > 0)) ||
                (contributionMethod === "lipila" && !invite.phone_number?.trim()) ||
                (contributionMethod === "cash" && !invite.cash_reason?.trim())
              }
              onClick={async () => {
                try {
                  const result = await Api.addGroupMember(Number(selectedGroupId), invite);
                  setInviteOpen(false);
                  setInvite({ email: "", full_name: "", password: "", name: "", phone_number: "", min_initial_deposit: 0, initial_contribution_method: "defer", cash_reason: "", custom_fields: {} });
                  await refresh(Number(selectedGroupId));
                  if (result.payment) {
                    onNotice(
                      result.payment.status === "completed"
                        ? `Member added and ${currency(result.payment.amount)} banked as cash.`
                        : `Member added. A prompt for ${currency(result.payment.amount)} was sent to their phone — their savings update once they approve it.`,
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
