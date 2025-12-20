import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  IconButton,
  LinearProgress,
  Skeleton,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { PageHeader } from "../../components/PageHeader";
import { StatusChip } from "../../components/StatusChip";
import { currency, formatDateTime } from "../../lib/format";
import { useAdmin } from "../adminContext";

export default function AdminOverviewPage() {
  const navigate = useNavigate();
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up("md"));
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
  const lockedAt = group?.settings?.constitution_locked_at;
  const hasGroup = Boolean(group);
  const hasMembers = members.length > 0;
  const hasLoanIssued = loans.length > 0;
  const constitutionConfigured = Boolean(
    group?.settings &&
      (group.settings.min_monthly_contribution > 0 ||
        group.settings.admin_fee_percent > 0 ||
        group.settings.loan_interest_percent > 0)
  );

  const memberNameByAccountId = useMemo(() => {
    const map = new Map<number, string>();
    for (const m of members) map.set(Number(m.id), m.name);
    return map;
  }, [members]);

  const totalSavings = useMemo(() => members.reduce((sum, member) => sum + Number(member.balance), 0), [members]);
  const activeLoans = useMemo(() => loans.filter((l) => l.status === "active"), [loans]);
  const activeLoanCount = activeLoans.length;
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
  const utilizationTone =
    liquidityUtilizationPct >= 90 ? "error" : liquidityUtilizationPct >= 70 ? "warning" : "success";
  const utilizationLabel =
    liquidityUtilizationPct >= 90 ? "High risk" : liquidityUtilizationPct >= 70 ? "Watch" : "Healthy";

  const pipeline = useMemo(() => {
    const counts = { requested: 0, queued: 0, approved: 0, rejected: 0, canceled: 0 };
    let openAmount = 0;
    for (const r of requests) {
      const key = r.status as keyof typeof counts;
      if (counts[key] !== undefined) counts[key] += 1;
      if (r.status === "requested" || r.status === "queued") openAmount += Number(r.principal) || 0;
    }
    return { counts, openAmount };
  }, [requests]);

  const interestBreakdown = useMemo(() => {
    let adminFee = 0;
    for (const loan of activeLoans) {
      const feePct = Number(loan.admin_fee_percent ?? 0);
      adminFee += (Number(loan.outstanding_interest) || 0) * (feePct / 100);
    }
    adminFee = Math.max(0, adminFee);
    const distributable = Math.max(0, outstandingInterest - adminFee);
    return { adminFee, distributable };
  }, [activeLoans, outstandingInterest]);

  const topContributors = useMemo(() => {
    const sorted = [...contributions].sort((a, b) => Number(b.net_contribution) - Number(a.net_contribution));
    const positive = sorted.filter((c) => Number(c.net_contribution) > 0);
    const total = positive.reduce((sum, c) => sum + Number(c.net_contribution), 0);
    return { total, rows: positive.slice(0, 6) };
  }, [contributions]);

  const recentRequests = useMemo(() => {
    const sorted = [...requests].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    return sorted.slice(0, 6);
  }, [requests]);

  const recentLoans = useMemo(() => {
    const sorted = [...loans].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    return sorted.slice(0, 6);
  }, [loans]);

  const steps = [
    { label: "Group created", done: hasGroup },
    { label: "Members added", done: hasMembers },
    { label: "Constitution configured", done: constitutionConfigured },
    { label: "Constitution locked", done: constitutionLocked },
    { label: "First loan issued", done: hasLoanIssued },
  ];
  const activeStepIndex = Math.max(0, steps.findIndex((step) => !step.done));

  const primaryAction = !hasMembers
    ? { label: "Add first member", onClick: openInvite }
    : !constitutionLocked
      ? { label: "Review and lock constitution", onClick: () => navigate("/admin/settings") }
      : { label: "View loan requests", onClick: () => navigate("/admin/requests") };

  const cardSx = {
    borderRadius: 3,
    border: "1px solid",
    borderColor: "divider",
    background: (theme: { palette: { mode: string } }) =>
      theme.palette.mode === "dark"
        ? "linear-gradient(160deg, rgba(15,23,42,0.98) 0%, rgba(30,41,59,0.78) 100%)"
        : "linear-gradient(160deg, rgba(255,255,255,1) 0%, rgba(248,250,252,0.92) 100%)",
  };
  const cardContentSx = { p: { xs: 2, md: 2.5 } };
  const progressSx = {
    height: 10,
    borderRadius: 999,
    backgroundColor: (theme: { palette: { mode: string } }) =>
      theme.palette.mode === "dark" ? "rgba(148,163,184,0.16)" : "rgba(15,23,42,0.08)",
    "& .MuiLinearProgress-bar": {
      borderRadius: 999,
      background:
        utilizationTone === "error"
          ? "linear-gradient(90deg, #ef4444 0%, #f97316 100%)"
          : utilizationTone === "warning"
            ? "linear-gradient(90deg, #f59e0b 0%, #f97316 100%)"
            : "linear-gradient(90deg, #2563eb 0%, #22c55e 100%)",
    },
  };

  return (
    <Box>
      <PageHeader
        title={groupName}
        subtitle={
          hasGroup
            ? constitutionLocked
              ? `Constitution locked at ${formatDateTime(lockedAt)}`
              : "Constitution is not locked yet. Lock it to enable autonomous lending."
            : "Select a group to see pool analytics and lending activity."
        }
        action={
          hasGroup ? (
            <Button variant="contained" onClick={() => navigate("/admin/settings")}>
              Constitution settings
            </Button>
          ) : null
        }
      />

      {!constitutionLocked && (
        <Card
          sx={{
            ...cardSx,
            mb: 2,
            borderColor: "rgba(37,99,235,0.35)",
            background: (theme) =>
              theme.palette.mode === "dark"
                ? "linear-gradient(135deg, rgba(37,99,235,0.18) 0%, rgba(15,23,42,0.95) 70%)"
                : "linear-gradient(135deg, rgba(37,99,235,0.16) 0%, rgba(248,250,252,0.95) 70%)",
          }}
        >
          <CardContent sx={{ p: { xs: 2, md: 2.5 } }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
              <Box flex={1}>
                <Typography variant="subtitle1" fontWeight={800}>
                  Launch the lending cycle
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  Complete the steps below, then lock the constitution to enable autonomous lending.
                </Typography>
              </Box>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                <Button variant="contained" size="large" onClick={primaryAction.onClick}>
                  {primaryAction.label}
                </Button>
                {!hasMembers && (
                  <Button variant="outlined" size="large" onClick={() => navigate("/admin/settings")}>
                    Configure constitution
                  </Button>
                )}
              </Stack>
            </Stack>

            <Box sx={{ mt: 2 }}>
              <Stepper
                activeStep={activeStepIndex === -1 ? steps.length - 1 : activeStepIndex}
                alternativeLabel={isDesktop}
                orientation={isDesktop ? "horizontal" : "vertical"}
              >
                {steps.map((step) => (
                  <Step key={step.label} completed={step.done}>
                    <StepLabel>{step.label}</StepLabel>
                  </Step>
                ))}
              </Stepper>
            </Box>
          </CardContent>
        </Card>
      )}

      <Grid container spacing={2}>
        <Grid item xs={12} lg={6}>
          <Card sx={cardSx}>
            <CardContent sx={cardContentSx}>
              <Box display="flex" justifyContent="space-between" alignItems="center" gap={2}>
                <Typography variant="subtitle1" fontWeight={800}>
                  Pool liquidity
                </Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Chip size="small" label={`Cap ${liquidityCapPct}%`} variant="outlined" />
                  <Tooltip title="The pool cannot lend beyond the agreed cap to stay liquid.">
                    <IconButton size="small">
                      <InfoOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Outstanding principal must stay under {liquidityCapPct}% of the pool.
              </Typography>

              <Box sx={{ mt: 2 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.75}>
                  <Typography variant="body2" color="text.secondary">
                    Utilization
                  </Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Chip size="small" color={utilizationTone} label={utilizationLabel} />
                    <Typography variant="body2" fontWeight={800}>
                      {busy ? "-" : `${Math.round(liquidityUtilizationPct)}%`}
                    </Typography>
                  </Box>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={busy ? 0 : liquidityUtilizationPct}
                  sx={progressSx}
                />
              </Box>

              <Grid container spacing={2} sx={{ mt: 1 }}>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Pool (savings)
                  </Typography>
                  <Typography variant="h6">{busy ? "-" : currency(totalSavings)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Outstanding principal
                  </Typography>
                  <Typography variant="h6">{busy ? "-" : currency(outstandingPrincipal)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Available to lend
                  </Typography>
                  <Typography variant="h6">{busy ? "-" : currency(availableToLend)}</Typography>
                </Grid>
              </Grid>

              <Divider sx={{ my: 2 }} />
              <Typography variant="body2" color="text.secondary">
                Pending transactions:{" "}
                <Typography component="span" fontWeight={800}>
                  {dashboard ? String(dashboard.pending_transactions) : busy ? "-" : "0"}
                </Typography>
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={6}>
          <Card sx={cardSx}>
            <CardContent sx={cardContentSx}>
              <Box display="flex" justifyContent="space-between" alignItems="center" gap={2}>
                <Typography variant="subtitle1" fontWeight={800}>
                  Interest outlook
                </Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Chip size="small" label={`${activeLoanCount} active loans`} variant="outlined" />
                  <Tooltip title="Interest grows as loans are repaid. Distribution happens at cycle end.">
                    <IconButton size="small">
                      <InfoOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Based on outstanding interest across active loans and per-loan admin fees.
              </Typography>

              <Grid container spacing={2} sx={{ mt: 1 }}>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Outstanding interest
                  </Typography>
                  <Typography variant="h6">{busy ? "-" : currency(outstandingInterest)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Admin fee (expected)
                  </Typography>
                  <Typography variant="h6">{busy ? "-" : currency(interestBreakdown.adminFee)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Distributable to members
                  </Typography>
                  <Typography variant="h6">{busy ? "-" : currency(interestBreakdown.distributable)}</Typography>
                </Grid>
              </Grid>

              <Divider sx={{ my: 2 }} />
              <Typography variant="body2" color="text.secondary">
                Contribution pool:{" "}
                <Typography component="span" fontWeight={800}>
                  {busy ? "-" : currency(topContributors.total)}
                </Typography>
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={7}>
          <Card sx={cardSx}>
            <CardContent sx={cardContentSx}>
              <Typography variant="subtitle1" fontWeight={800}>
                Activity
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1 }}>
                Recent loan requests and loan creations.
              </Typography>

              <Stack spacing={1.25}>
                <Box>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                    <Typography variant="body2" fontWeight={800}>
                      Recent requests
                    </Typography>
                    <Button size="small" variant="text" onClick={() => navigate("/admin/requests")}>
                      View all
                    </Button>
                  </Box>
                  {busy && recentRequests.length === 0 ? (
                    <Stack spacing={1}>
                      <Skeleton height={28} />
                      <Skeleton height={28} />
                      <Skeleton height={28} />
                    </Stack>
                  ) : recentRequests.length === 0 ? (
                    <Box display="flex" alignItems="center" justifyContent="space-between" gap={2}>
                      <Typography variant="body2" color="text.secondary">
                        No requests yet. Lock the constitution to enable lending.
                      </Typography>
                      {!constitutionLocked && (
                        <Button size="small" variant="outlined" onClick={() => navigate("/admin/settings")}>
                          Review constitution
                        </Button>
                      )}
                    </Box>
                  ) : (
                    <Stack spacing={1}>
                      {recentRequests.map((r) => (
                        <Box key={r.id} display="flex" alignItems="center" justifyContent="space-between" gap={2}>
                          <Box minWidth={0}>
                            <Typography variant="body2" fontWeight={700} noWrap>
                              {memberNameByAccountId.get(Number(r.borrower_account_id)) ?? `Account ${r.borrower_account_id}`} -{" "}
                              {currency(Number(r.principal))}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" noWrap>
                              {formatDateTime(r.created_at)}
                            </Typography>
                          </Box>
                          <StatusChip value={String(r.status)} />
                        </Box>
                      ))}
                    </Stack>
                  )}
                </Box>

                <Divider />

                <Box>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                    <Typography variant="body2" fontWeight={800}>
                      Recent loans
                    </Typography>
                    <Button size="small" variant="text" onClick={() => navigate("/admin/loans")}>
                      View all
                    </Button>
                  </Box>
                  {busy && recentLoans.length === 0 ? (
                    <Stack spacing={1}>
                      <Skeleton height={28} />
                      <Skeleton height={28} />
                      <Skeleton height={28} />
                    </Stack>
                  ) : recentLoans.length === 0 ? (
                    <Box display="flex" alignItems="center" justifyContent="space-between" gap={2}>
                      <Typography variant="body2" color="text.secondary">
                        No loans yet. Members can request after the constitution is locked.
                      </Typography>
                      {!constitutionLocked && (
                        <Button size="small" variant="outlined" onClick={() => navigate("/admin/settings")}>
                          Lock constitution
                        </Button>
                      )}
                    </Box>
                  ) : (
                    <Stack spacing={1}>
                      {recentLoans.map((l) => (
                        <Box key={l.id} display="flex" alignItems="center" justifyContent="space-between" gap={2}>
                          <Box minWidth={0}>
                            <Typography variant="body2" fontWeight={700} noWrap>
                              #{l.id} - {memberNameByAccountId.get(Number(l.borrower_account_id)) ?? `Account ${l.borrower_account_id}`} -{" "}
                              {currency(Number(l.principal))}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" noWrap>
                              {formatDateTime(l.created_at)}
                            </Typography>
                          </Box>
                          <StatusChip value={String(l.status)} />
                        </Box>
                      ))}
                    </Stack>
                  )}
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={5}>
          <Card sx={cardSx}>
            <CardContent sx={cardContentSx}>
              <Typography variant="subtitle1" fontWeight={800}>
                Top contributors
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Contribution share is used to split distributable loan interest.
              </Typography>

              <Divider sx={{ my: 2 }} />

              {busy && contributions.length === 0 ? (
                <Stack spacing={1}>
                  <Skeleton height={36} />
                  <Skeleton height={36} />
                  <Skeleton height={36} />
                </Stack>
              ) : topContributors.rows.length === 0 ? (
                <Box display="flex" alignItems="center" justifyContent="space-between" gap={2}>
                  <Typography variant="body2" color="text.secondary">
                    No contributions recorded yet. Add members and record the first contribution.
                  </Typography>
                  <Button size="small" variant="outlined" onClick={openInvite}>
                    Add member
                  </Button>
                </Box>
              ) : (
                <Stack spacing={1.25}>
                  {topContributors.rows.map((c) => {
                    const pct = topContributors.total > 0 ? (Number(c.net_contribution) / topContributors.total) * 100 : 0;
                    return (
                      <Box key={c.account_id}>
                        <Box display="flex" justifyContent="space-between" alignItems="center" gap={2}>
                          <Typography variant="body2" fontWeight={700} noWrap>
                            {c.member_name}
                          </Typography>
                          <Typography variant="body2" fontWeight={800} noWrap>
                            {currency(Number(c.net_contribution))}
                          </Typography>
                        </Box>
                        <Box display="flex" alignItems="center" gap={1} mt={0.5}>
                          <Box flex={1}>
                            <LinearProgress variant="determinate" value={pct} sx={{ height: 8, borderRadius: 999 }} />
                          </Box>
                          <Typography variant="caption" color="text.secondary" sx={{ minWidth: 46, textAlign: "right" }}>
                            {pct.toFixed(1)}%
                          </Typography>
                        </Box>
                      </Box>
                    );
                  })}
                </Stack>
              )}

              <Divider sx={{ my: 2 }} />

              <Typography variant="body2" color="text.secondary">
                Pipeline:{" "}
                <Typography component="span" fontWeight={800}>
                  {busy ? "-" : `${pipeline.counts.requested + pipeline.counts.queued} open`}
                </Typography>{" "}
                - Open amount{" "}
                <Typography component="span" fontWeight={800}>
                  {busy ? "-" : currency(pipeline.openAmount)}
                </Typography>
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
