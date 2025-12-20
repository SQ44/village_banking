import { useEffect, useState } from "react";
import { Box, Button, FormControlLabel, Grid, Switch, TextField } from "@mui/material";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { PageHeader } from "../../components/PageHeader";
import { formatDateTime } from "../../lib/format";
import { useAdmin } from "../adminContext";
import type { GroupSettingsUpdatePayload } from "../../types";

export default function AdminSettingsPage() {
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
