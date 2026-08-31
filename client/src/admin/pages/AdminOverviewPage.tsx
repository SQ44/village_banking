import { useNavigate } from "react-router-dom";
import { Box, Button, Card, CardContent, Grid, LinearProgress, Stack, Typography } from "@mui/material";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";

import { Metric } from "../../components/Metric";
import { PageHeader } from "../../components/PageHeader";
import { Section } from "../../components/Section";
import { StatCard } from "../../components/StatCard";
import { currency } from "../../lib/format";
import { useAdmin } from "../adminContext";

/** A ratio the server could not compute — no loans, no members, nothing to
 *  divide by. Shown as an em dash rather than as a confident 0%. */
const NO_VALUE = "—";

function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return NO_VALUE;
  return `${value.toFixed(digits)}%`;
}

/** Traffic light for portfolio at risk. The thresholds are the ordinary
 *  microfinance ones: under 5% is a healthy book, over 10% needs a response. */
function riskTone(par: number | null): "success" | "warning" | "error" | "inherit" {
  if (par === null) return "inherit";
  if (par >= 10) return "error";
  if (par >= 5) return "warning";
  return "success";
}

export default function AdminOverviewPage() {
  const navigate = useNavigate();
  const { group, constitutionLocked, members, loans, performance, busy, openInvite } = useAdmin();

  const hasGroup = Boolean(group);
  const hasMembers = members.length > 0;
  const constitutionConfigured = Boolean(
    group?.settings &&
      (group.settings.min_monthly_contribution > 0 ||
        group.settings.admin_fee_percent > 0 ||
        group.settings.loan_interest_percent > 0)
  );

  const loading = busy && !performance;
  const portfolio = performance?.portfolio;
  const liquidity = performance?.liquidity;
  const earnings = performance?.earnings;
  const cycle = performance?.cycle;

  const par = portfolio?.par_percent ?? null;
  const tone = riskTone(par);

  const netSavings = cycle?.net_savings ?? 0;
  const previousNet = cycle?.previous_net_savings ?? 0;
  const growthDelta = netSavings - previousNet;
  const growthUp = growthDelta >= 0;

  const steps = [
    { label: "Members added", done: hasMembers },
    { label: "Constitution configured", done: constitutionConfigured },
    { label: "Constitution locked", done: constitutionLocked },
    { label: "First loan issued", done: loans.length > 0 },
  ];

  const primaryAction = !hasMembers
    ? { label: "Add first member", onClick: openInvite }
    : { label: "Review constitution", onClick: () => navigate("/admin/settings") };

  if (!hasGroup) {
    return (
      <Box>
        <PageHeader title="Overview" subtitle="Select a group to see how it is performing." />
      </Box>
    );
  }

  return (
    <Box>
      {/* The group's name is the sidebar heading, so this says what the page is
          rather than repeating which group it belongs to. */}
      <PageHeader
        title="Overview"
        subtitle={
          cycle
            ? `Performance over the last ${cycle.cycle_days} days.`
            : "How the group is performing."
        }
        action={
          <Button variant="outlined" onClick={() => navigate("/admin/money")}>
            Money
          </Button>
        }
      />

      {!constitutionLocked && (
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

      {/* The four headline answers, in the order an admin asks them: how much
          have we got, is any of it in trouble, are people paying, are we growing. */}
      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid item xs={6} md={3}>
          <StatCard label="Pool" value={currency(liquidity?.pool ?? 0)} loading={loading} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Portfolio at risk"
            value={percent(par, 1)}
            loading={loading}
            tone={tone}
            helper={
              portfolio && portfolio.at_risk_loans > 0
                ? `${portfolio.at_risk_loans} of ${portfolio.active_loans} loans in arrears`
                : "No loans in arrears"
            }
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Repaid on time"
            value={percent(portfolio?.on_time_percent ?? null)}
            loading={loading}
            helper={
              portfolio?.settled_installments
                ? `${portfolio.on_time_installments} of ${portfolio.settled_installments} installments`
                : "No repayments yet"
            }
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Net this cycle"
            value={currency(netSavings)}
            loading={loading}
            helper={
              cycle
                ? `${growthUp ? "+" : ""}${currency(growthDelta)} vs last cycle`
                : undefined
            }
            helperIcon={
              cycle && growthDelta !== 0 ? (
                growthUp ? (
                  <ArrowUpwardIcon sx={{ fontSize: 14 }} />
                ) : (
                  <ArrowDownwardIcon sx={{ fontSize: 14 }} />
                )
              ) : undefined
            }
            helperTone={cycle && growthDelta !== 0 ? (growthUp ? "success" : "error") : undefined}
          />
        </Grid>
      </Grid>

      <Grid container spacing={2.5} alignItems="flex-start">
        <Grid item xs={12} md={6}>
          <Section
            title="Portfolio quality"
            subtitle="How much of what is lent out is behind on a payment."
            action={
              <Button size="small" onClick={() => navigate("/admin/loans")}>
                Loans
              </Button>
            }
          >
            <Box mb={2.5}>
              <Box display="flex" justifyContent="space-between" alignItems="baseline" mb={1}>
                <Typography variant="body2" color="text.secondary">
                  Behind on a payment
                </Typography>
                <Typography
                  variant="body2"
                  fontWeight={600}
                  color={tone === "inherit" ? "text.secondary" : `${tone}.main`}
                >
                  {percent(par, 1)}
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                color={tone === "inherit" ? "primary" : tone}
                value={Math.min(100, par ?? 0)}
              />
            </Box>

            <Grid container spacing={2.5}>
              <Grid item xs={6}>
                <Metric label="At risk" value={currency(portfolio?.at_risk_amount ?? 0)} loading={loading} />
              </Grid>
              <Grid item xs={6}>
                <Metric label="Overdue now" value={currency(portfolio?.arrears_amount ?? 0)} loading={loading} />
              </Grid>
              <Grid item xs={6}>
                <Metric
                  label={`At risk ${portfolio?.par_benchmark_days ?? 30}+ days`}
                  value={percent(portfolio?.par_benchmark_percent ?? null, 1)}
                  loading={loading}
                />
              </Grid>
              <Grid item xs={6}>
                <Metric
                  label="Active / settled"
                  value={`${portfolio?.active_loans ?? 0} / ${portfolio?.closed_loans ?? 0}`}
                  loading={loading}
                />
              </Grid>
            </Grid>
          </Section>
        </Grid>

        <Grid item xs={12} md={6}>
          <Section
            title="Capital"
            subtitle="Money lent out earns; money sitting idle does not."
            action={
              <Button size="small" onClick={() => navigate("/admin/requests")}>
                Requests
              </Button>
            }
          >
            <Box mb={2.5}>
              <Box display="flex" justifyContent="space-between" alignItems="baseline" mb={1}>
                <Typography variant="body2" color="text.secondary">
                  Lent out, against a {liquidity?.cap_percent ?? 80}% cap
                </Typography>
                <Typography variant="body2" fontWeight={600}>
                  {percent(liquidity?.utilization_percent ?? null)}
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={Math.min(100, liquidity?.cap_used_percent ?? 0)}
              />
            </Box>

            <Grid container spacing={2.5}>
              <Grid item xs={6}>
                <Metric label="Lent out" value={currency(liquidity?.lent_out ?? 0)} loading={loading} />
              </Grid>
              <Grid item xs={6}>
                <Metric
                  label="Available to lend"
                  value={currency(liquidity?.available_to_lend ?? 0)}
                  loading={loading}
                />
              </Grid>
              <Grid item xs={6}>
                <Metric label="Open requests" value={String(cycle?.open_requests ?? 0)} loading={loading} />
              </Grid>
              <Grid item xs={6}>
                <Metric
                  label="Requested"
                  value={currency(cycle?.open_request_amount ?? 0)}
                  loading={loading}
                />
              </Grid>
            </Grid>
          </Section>
        </Grid>

        <Grid item xs={12} md={6}>
          <Section title="Earnings" subtitle="What lending has returned to the pool.">
            <Grid container spacing={2.5}>
              <Grid item xs={6}>
                <Metric
                  label="Interest earned"
                  value={currency(earnings?.interest_earned ?? 0)}
                  loading={loading}
                  size="lg"
                />
              </Grid>
              <Grid item xs={6}>
                <Metric
                  label="Return on pool"
                  value={percent(earnings?.return_on_pool_percent ?? null, 1)}
                  loading={loading}
                  size="lg"
                />
              </Grid>
              <Grid item xs={6}>
                <Metric label="Still accruing" value={currency(earnings?.interest_accruing ?? 0)} loading={loading} />
              </Grid>
              <Grid item xs={6}>
                <Metric label="Admin fees" value={currency(earnings?.admin_fees ?? 0)} loading={loading} />
              </Grid>
            </Grid>
          </Section>
        </Grid>

        <Grid item xs={12} md={6}>
          <Section
            title="This cycle"
            subtitle="Money in and out, and who took part."
            action={
              <Button size="small" onClick={() => navigate("/admin/members")}>
                Members
              </Button>
            }
          >
            <Grid container spacing={2.5}>
              <Grid item xs={6}>
                <Metric label="Deposits" value={currency(cycle?.deposits ?? 0)} loading={loading} />
              </Grid>
              <Grid item xs={6}>
                <Metric label="Withdrawals" value={currency(cycle?.withdrawals ?? 0)} loading={loading} />
              </Grid>
              <Grid item xs={6}>
                <Metric
                  label="Repayments"
                  value={currency(cycle?.repayments_collected ?? 0)}
                  loading={loading}
                />
              </Grid>
              <Grid item xs={6}>
                <Metric
                  label="Contributing"
                  value={
                    cycle
                      ? `${cycle.contributing_members} of ${cycle.member_count}`
                      : NO_VALUE
                  }
                  loading={loading}
                />
              </Grid>
            </Grid>
          </Section>
        </Grid>
      </Grid>
    </Box>
  );
}
