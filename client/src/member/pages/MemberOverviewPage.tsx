import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Grid,
  InputAdornment,
  LinearProgress,
  Skeleton,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import { PageHeader } from "../../components/PageHeader";
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
          <Card sx={{ height: "100%" }}>
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
                    {cycleEnd ? cycleEnd.toLocaleDateString() : "-"}
                  </Typography>
                </Box>
              </Box>

              <Grid container spacing={2} sx={{ mt: 0.5 }}>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Current savings
                  </Typography>
                  <Typography variant="h6">{busy && !summary ? "-" : currency(currentSavings)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Projected by cycle end
                  </Typography>
                  <Typography variant="h6">{busy && !summary ? "-" : currency(projectedSavings)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">
                    Avg net / day (cycle)
                  </Typography>
                  <Typography variant="h6">{busy && !summary ? "-" : currency(avgNetPerDay)}</Typography>
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
                      {busy && !summary ? "-" : `${Math.round(progress)}%`}
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
                  Deposits this cycle: {flow.depositCount} - Avg deposit:{" "}
                  {flow.depositCount ? currency(flow.depositTotal / flow.depositCount) : "-"}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Days remaining: {daysRemaining}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={5}>
          <Card sx={{ height: "100%" }}>
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
                  Net contribution: {currency(Number(forecast?.my_net_contribution ?? 0))} - Group total:{" "}
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
