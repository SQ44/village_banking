import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  CardContent,
  Divider,
  Grid,
  LinearProgress,
  Skeleton,
  Stack,
  Typography,
} from "@mui/material";
import AccountBalanceIcon from "@mui/icons-material/AccountBalance";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ChecklistIcon from "@mui/icons-material/Checklist";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import GroupIcon from "@mui/icons-material/Group";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";

import { Metric } from "../../components/Metric";
import { PageHeader } from "../../components/PageHeader";
import { Section } from "../../components/Section";
import { StatCard } from "../../components/StatCard";
import { StatusChip } from "../../components/StatusChip";
import { currency, formatDate } from "../../lib/format";
import { useAdmin } from "../adminContext";

const RECENT_LIMIT = 5;

export default function AdminOverviewPage() {
  const navigate = useNavigate();
  const {
    group,
    constitutionLocked,
    members,
    loans,
    requests,
    contributions,
    dashboard,
    busy,
    openInvite,
  } = useAdmin();

  const groupName = group?.name ?? "Admin Overview";
  const hasGroup = Boolean(group);
  const hasMembers = members.length > 0;
  const hasLoanIssued = loans.length > 0;
  const constitutionConfigured = Boolean(
    group?.settings &&
      (group.settings.min_monthly_contribution > 0 ||
        group.settings.admin_fee_percent > 0 ||
        group.settings.loan_interest_percent > 0)
  );

  // Skeletons on the first load only. A background refresh keeps the previous
  // figures on screen rather than blinking every number on the page.
  const firstLoad = busy && !hasMembers && !hasLoanIssued && !dashboard;

  const memberNameByAccountId = useMemo(() => {
    const map = new Map<number, string>();
    for (const m of members) map.set(Number(m.id), m.name);
    return map;
  }, [members]);

  const totalSavings = useMemo(() => members.reduce((sum, member) => sum + Number(member.balance), 0), [members]);
  const activeLoans = useMemo(() => loans.filter((l) => l.status === "active"), [loans]);
  const outstandingPrincipal = useMemo(
    () => activeLoans.reduce((sum, loan) => sum + Number(loan.outstanding_principal), 0),
    [activeLoans]
  );
  const outstandingInterest = useMemo(
    () => activeLoans.reduce((sum, loan) => sum + Number(loan.outstanding_interest), 0),
    [activeLoans]
  );

  const liquidityCapPct = Number(group?.settings?.liquidity_max_outstanding_percent ?? 80);
  const liquidityCapAmount = (totalSavings * liquidityCapPct) / 100;
  const liquidityUtilizationPct =
    liquidityCapAmount > 0 ? Math.min(100, (outstandingPrincipal / liquidityCapAmount) * 100) : 0;
  const availableToLend = Math.max(0, liquidityCapAmount - outstandingPrincipal);
  const utilizationTone: "success" | "warning" | "error" =
    liquidityUtilizationPct >= 90 ? "error" : liquidityUtilizationPct >= 70 ? "warning" : "success";

  const pipeline = useMemo(() => {
    let open = 0;
    let openAmount = 0;
    for (const r of requests) {
      if (r.status === "requested" || r.status === "queued") {
        open += 1;
        openAmount += Number(r.principal) || 0;
      }
    }
    return { open, openAmount };
  }, [requests]);

  const adminFee = useMemo(() => {
    let fee = 0;
    for (const loan of activeLoans) {
      const feePct = Number(loan.admin_fee_percent ?? 0);
      fee += (Number(loan.outstanding_interest) || 0) * (feePct / 100);
    }
    return Math.max(0, fee);
  }, [activeLoans]);
  const distributableInterest = Math.max(0, outstandingInterest - adminFee);

  const topContributors = useMemo(() => {
    const positive = [...contributions]
      .filter((c) => Number(c.net_contribution) > 0)
      .sort((a, b) => Number(b.net_contribution) - Number(a.net_contribution));
    const total = positive.reduce((sum, c) => sum + Number(c.net_contribution), 0);
    return { total, rows: positive.slice(0, RECENT_LIMIT) };
  }, [contributions]);

  const recentRequests = useMemo(
    () => [...requests].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, RECENT_LIMIT),
    [requests]
  );

  const recentLoans = useMemo(
    () => [...loans].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, RECENT_LIMIT),
    [loans]
  );

  const steps = [
    { label: "Group created", done: hasGroup },
    { label: "Members added", done: hasMembers },
    { label: "Constitution configured", done: constitutionConfigured },
    { label: "Constitution locked", done: constitutionLocked },
    { label: "First loan issued", done: hasLoanIssued },
  ];

  const primaryAction = !hasMembers
    ? { label: "Add first member", onClick: openInvite }
    : { label: "Review constitution", onClick: () => navigate("/admin/settings") };

  return (
    <Box>
      <PageHeader
        title={groupName}
        subtitle={
          hasGroup
            ? constitutionLocked
              ? "Lending is autonomous. Requests are decided against the locked constitution."
              : "Lending is paused until the constitution is locked."
            : "Select a group to see pool analytics and lending activity."
        }
        action={
          hasGroup ? (
            <Button variant="outlined" onClick={() => navigate("/admin/settings")}>
              Constitution
            </Button>
          ) : null
        }
      />

      {hasGroup && !constitutionLocked && (
        <Card sx={{ mb: 2.5 }}>
          <CardContent sx={{ p: { xs: 2, md: 2.25 }, "&:last-child": { pb: { xs: 2, md: 2.25 } } }}>
            <Stack
              direction={{ xs: "column", md: "row" }}
              spacing={2}
              alignItems={{ md: "center" }}
              justifyContent="space-between"
            >
              <Box minWidth={0}>
                <Typography variant="subtitle1">Finish setup</Typography>
                <Stack direction="row" flexWrap="wrap" rowGap={0.5} columnGap={2} sx={{ mt: 1 }}>
                  {steps.map((step) => (
                    <Box key={step.label} display="flex" alignItems="center" gap={0.75}>
                      {step.done ? (
                        <CheckCircleIcon sx={{ fontSize: 16, color: "success.main" }} />
                      ) : (
                        <RadioButtonUncheckedIcon sx={{ fontSize: 16, color: "text.disabled" }} />
                      )}
                      <Typography
                        variant="body2"
                        color={step.done ? "text.secondary" : "text.primary"}
                        sx={{ textDecoration: step.done ? "line-through" : "none" }}
                      >
                        {step.label}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>
              <Button variant="contained" onClick={primaryAction.onClick} sx={{ flexShrink: 0 }}>
                {primaryAction.label}
              </Button>
            </Stack>
          </CardContent>
        </Card>
      )}

      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid item xs={6} md={3}>
          <StatCard label="Members" value={`${members.length}`} icon={<GroupIcon />} loading={firstLoad} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Total savings"
            value={currency(totalSavings)}
            icon={<AccountBalanceIcon />}
            loading={firstLoad}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Active loans"
            value={`${activeLoans.length}`}
            icon={<CreditCardIcon />}
            loading={firstLoad}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Open requests"
            value={`${pipeline.open}`}
            icon={<ChecklistIcon />}
            loading={firstLoad}
          />
        </Grid>
      </Grid>

      {/* Two columns that size to their own content. Stretching a short card to
          match a tall neighbour only manufactures empty space. */}
      <Grid container spacing={2.5} alignItems="flex-start">
        <Grid item xs={12} lg={8}>
          <Stack spacing={2.5}>
            <Section title="Pool">
              <Box mb={2.5}>
                <Box display="flex" justifyContent="space-between" alignItems="baseline" mb={1}>
                  <Typography variant="body2" color="text.secondary">
                    Lent out, against a {liquidityCapPct}% cap
                  </Typography>
                  <Typography variant="body2" fontWeight={600} color={`${utilizationTone}.main`}>
                    {firstLoad ? "—" : `${Math.round(liquidityUtilizationPct)}%`}
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  color={utilizationTone}
                  value={firstLoad ? 0 : liquidityUtilizationPct}
                />
              </Box>

              <Grid container spacing={2.5}>
                <Grid item xs={6}>
                  <Metric label="Lent out" value={currency(outstandingPrincipal)} loading={firstLoad} />
                </Grid>
                <Grid item xs={6}>
                  <Metric label="Available to lend" value={currency(availableToLend)} loading={firstLoad} />
                </Grid>
              </Grid>

              <Divider sx={{ my: 2.5 }} />

              <Grid container spacing={2.5}>
                <Grid item xs={6} sm={4}>
                  <Metric label="Interest accrued" value={currency(outstandingInterest)} loading={firstLoad} />
                </Grid>
                <Grid item xs={6} sm={4}>
                  <Metric label="Admin fee" value={currency(adminFee)} loading={firstLoad} />
                </Grid>
                <Grid item xs={6} sm={4}>
                  <Metric label="To members" value={currency(distributableInterest)} loading={firstLoad} />
                </Grid>
              </Grid>
            </Section>

            <Section title="Activity">
              <ActivityList
                heading="Requests"
                onViewAll={() => navigate("/admin/requests")}
                loading={busy && recentRequests.length === 0}
                empty="No requests yet."
                rows={recentRequests.map((r) => ({
                  key: `r-${r.id}`,
                  primary:
                    memberNameByAccountId.get(Number(r.borrower_account_id)) ?? `Account ${r.borrower_account_id}`,
                  amount: currency(Number(r.principal)),
                  secondary: formatDate(r.created_at),
                  status: String(r.status),
                }))}
              />

              <Divider sx={{ my: 2.5 }} />

              <ActivityList
                heading="Loans"
                onViewAll={() => navigate("/admin/loans")}
                loading={busy && recentLoans.length === 0}
                empty="No loans issued yet."
                rows={recentLoans.map((l) => ({
                  key: `l-${l.id}`,
                  primary:
                    memberNameByAccountId.get(Number(l.borrower_account_id)) ?? `Account ${l.borrower_account_id}`,
                  amount: currency(Number(l.principal)),
                  secondary: `#${l.id} · ${formatDate(l.created_at)}`,
                  status: String(l.status),
                }))}
              />
            </Section>
          </Stack>
        </Grid>

        <Grid item xs={12} lg={4}>
          <Stack spacing={2.5}>
            <Section
              title="Pipeline"
              action={
                <Button size="small" onClick={() => navigate("/admin/requests")}>
                  Review
                </Button>
              }
            >
              <Stack spacing={2.5}>
                <Metric label="Open amount" value={currency(pipeline.openAmount)} loading={firstLoad} size="lg" />
                <Metric
                  label="Pending transactions"
                  value={dashboard ? String(dashboard.pending_transactions) : "0"}
                  loading={firstLoad}
                />
              </Stack>
            </Section>

            <Section title="Top contributors" subtitle="Interest is split by contribution share.">
              {busy && topContributors.rows.length === 0 ? (
                <Stack spacing={2}>
                  <Skeleton height={30} />
                  <Skeleton height={30} />
                  <Skeleton height={30} />
                </Stack>
              ) : topContributors.rows.length === 0 ? (
                <Stack spacing={1.5} alignItems="flex-start">
                  <Typography variant="body2" color="text.secondary">
                    No contributions recorded yet.
                  </Typography>
                  <Button size="small" variant="outlined" onClick={openInvite}>
                    Add member
                  </Button>
                </Stack>
              ) : (
                <Stack spacing={1.75}>
                  {topContributors.rows.map((c) => {
                    const pct =
                      topContributors.total > 0 ? (Number(c.net_contribution) / topContributors.total) * 100 : 0;
                    return (
                      <Box key={c.account_id}>
                        <Box display="flex" justifyContent="space-between" alignItems="baseline" gap={2} mb={0.75}>
                          <Typography variant="body2" noWrap>
                            {c.member_name}
                          </Typography>
                          <Typography variant="body2" fontWeight={600} noWrap>
                            {currency(Number(c.net_contribution))}
                          </Typography>
                        </Box>
                        <LinearProgress variant="determinate" value={pct} sx={{ height: 4 }} />
                      </Box>
                    );
                  })}
                </Stack>
              )}
            </Section>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
}

type ActivityRow = {
  key: string;
  primary: string;
  amount: string;
  secondary: string;
  status: string;
};

/**
 * Both activity lists on the overview render identically — one shape, so
 * requests and loans scan the same way instead of each inventing a layout.
 */
function ActivityList({
  heading,
  rows,
  loading,
  empty,
  onViewAll,
}: {
  heading: string;
  rows: ActivityRow[];
  loading: boolean;
  empty: string;
  onViewAll: () => void;
}) {
  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1.25}>
        <Typography variant="overline" color="text.secondary">
          {heading}
        </Typography>
        <Button size="small" onClick={onViewAll}>
          View all
        </Button>
      </Box>

      {loading ? (
        <Stack spacing={1.5}>
          <Skeleton height={26} />
          <Skeleton height={26} />
          <Skeleton height={26} />
        </Stack>
      ) : rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {empty}
        </Typography>
      ) : (
        <Stack spacing={1.5}>
          {rows.map((row) => (
            <Box key={row.key} display="flex" alignItems="center" justifyContent="space-between" gap={2}>
              <Box minWidth={0}>
                <Typography variant="body2" fontWeight={550} noWrap>
                  {row.primary}
                </Typography>
                <Typography variant="caption" color="text.secondary" noWrap display="block">
                  {row.secondary}
                </Typography>
              </Box>
              <Box display="flex" alignItems="center" gap={1.5} flexShrink={0}>
                <Typography variant="body2" fontWeight={600}>
                  {row.amount}
                </Typography>
                <StatusChip value={row.status} />
              </Box>
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  );
}
