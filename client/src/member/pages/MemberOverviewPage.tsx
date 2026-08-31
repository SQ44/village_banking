import { useEffect, useState } from "react";
import { Box, Grid, InputAdornment, LinearProgress, Stack, TextField, Typography } from "@mui/material";
import AccountBalanceWalletIcon from "@mui/icons-material/AccountBalanceWallet";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import GroupIcon from "@mui/icons-material/Group";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";

import { Metric } from "../../components/Metric";
import { PageHeader } from "../../components/PageHeader";
import { Section } from "../../components/Section";
import { StatCard } from "../../components/StatCard";
import { currency, formatDate } from "../../lib/format";
import { useMember } from "../memberContext";

export default function MemberOverviewPage() {
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

  const loading = busy && !summary;
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
  const activeLoanCount = (forecast?.loans ?? []).length;
  const expectedInterest = (forecast?.loans ?? []).reduce((sum, item) => sum + Number(item.my_expected_interest ?? 0), 0);

  return (
    <Box>
      <PageHeader
        title="Overview"
        subtitle={
          daysRemaining > 0
            ? `${daysRemaining} ${daysRemaining === 1 ? "day" : "days"} left in this cycle.`
            : "This cycle has reached its withdrawal date."
        }
      />

      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Savings"
            value={currency(currentSavings)}
            icon={<AccountBalanceWalletIcon />}
            loading={loading}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Interest earned"
            value={currency(Number(summary?.interest_earned ?? 0))}
            icon={<TrendingUpIcon />}
            loading={loading}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Outstanding loans"
            value={currency(Number(summary?.loan_outstanding ?? 0))}
            icon={<CreditCardIcon />}
            loading={loading}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="My share"
            value={`${(forecast?.my_share_percent ?? 0).toFixed(2)}%`}
            icon={<GroupIcon />}
            loading={loading}
          />
        </Grid>
      </Grid>

      <Grid container spacing={2.5} alignItems="flex-start">
        <Grid item xs={12} lg={7}>
          <Section title="Savings" subtitle="Where you land by the withdrawal date at your current pace.">
            <Grid container spacing={2.5} sx={{ mb: 3 }}>
              <Grid item xs={6} sm={4}>
                <Metric label="Saved so far" value={currency(currentSavings)} loading={loading} size="lg" />
              </Grid>
              <Grid item xs={6} sm={4}>
                <Metric label="Projected" value={currency(projectedSavings)} loading={loading} size="lg" />
              </Grid>
              <Grid item xs={6} sm={4}>
                <Metric label="Average per day" value={currency(avgNetPerDay)} loading={loading} size="lg" />
              </Grid>
            </Grid>

            <Box mb={3}>
              <Box display="flex" justifyContent="space-between" alignItems="baseline" mb={1}>
                <Typography variant="body2" color="text.secondary">
                  {onTrack ? "On track for your target" : `Needs about ${currency(requiredPerWeek)} a week`}
                </Typography>
                <Typography variant="body2" fontWeight={600} color={onTrack ? "success.main" : "text.primary"}>
                  {loading ? "—" : `${Math.round(progress)}%`}
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                color={onTrack ? "success" : "primary"}
                value={loading ? 0 : progress}
              />
            </Box>

            <TextField
              label="Target by cycle end"
              type="number"
              size="small"
              fullWidth
              value={target}
              onChange={(e) => setTarget(e.target.value === "" ? "" : Number(e.target.value))}
              disabled={!summary}
              InputProps={{ startAdornment: <InputAdornment position="start">K</InputAdornment> }}
              helperText={target === "" ? `Suggested: ${currency(suggestedTarget)}` : " "}
            />
          </Section>
        </Grid>

        <Grid item xs={12} lg={5}>
          <Stack spacing={2.5} height="100%">
            <Section title="Key dates" dense>
              <Stack spacing={2}>
                <Metric
                  label="Next withdrawal"
                  value={summary?.next_withdrawal_at ? formatDate(summary.next_withdrawal_at) : "Not scheduled"}
                  loading={loading}
                  size="sm"
                />
                <Metric
                  label="Next interest accrual"
                  value={
                    summary?.next_interest_accrual_at ? formatDate(summary.next_interest_accrual_at) : "Not scheduled"
                  }
                  loading={loading}
                  size="sm"
                />
                <Metric
                  label="Deposits this cycle"
                  value={
                    flow.depositCount
                      ? `${flow.depositCount} · avg ${currency(flow.depositTotal / flow.depositCount)}`
                      : "None yet"
                  }
                  loading={loading}
                  size="sm"
                />
              </Stack>
            </Section>

            <Section title="Interest" subtitle="Your share of interest on the group's active loans." dense>
              <Metric label="Expected this cycle" value={currency(expectedInterest)} loading={loading} size="lg" />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {activeLoanCount === 0
                  ? "No active loans in the group yet."
                  : `From ${activeLoanCount} active ${activeLoanCount === 1 ? "loan" : "loans"}.`}
              </Typography>
            </Section>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
}
