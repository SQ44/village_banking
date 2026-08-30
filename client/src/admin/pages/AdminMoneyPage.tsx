import { useEffect, useState } from "react";
import { Alert, Box, Chip, CircularProgress, Grid, Paper, Stack, Typography } from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import GroupIcon from "@mui/icons-material/Group";
import AccountBalanceWalletIcon from "@mui/icons-material/AccountBalanceWallet";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import ReceiptLongIcon from "@mui/icons-material/ReceiptLong";

import { Api } from "../../api";
import { PageHeader } from "../../components/PageHeader";
import { StatCard } from "../../components/StatCard";
import { currency } from "../../lib/format";
import { useAdmin } from "../adminContext";
import type { JournalEntryRead, TrialBalanceReport } from "../../types";

/** Plain-language names for the chart of accounts. */
const LABELS: Record<string, string> = {
  member_savings: "Owed to members",
  lipila_settlement: "Held at Lipila",
  cash_on_hand: "Cash on hand",
  loans_receivable: "Out on loan",
  provider_fees: "Fees paid",
  interest_expense: "Interest paid to savers",
  interest_income: "Interest earned",
  fee_income: "Fees charged",
};

const label = (code: string) => LABELS[code] ?? code.replace(/_/g, " ");

export default function AdminMoneyPage() {
  const { selectedGroupId } = useAdmin();
  const [report, setReport] = useState<TrialBalanceReport | null>(null);
  const [entries, setEntries] = useState<JournalEntryRead[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setBusy(true);
      setError(null);
      try {
        const groupId = selectedGroupId ? Number(selectedGroupId) : undefined;
        const [balance, journal] = await Promise.all([
          Api.getTrialBalance(groupId),
          Api.getJournal(groupId, 100),
        ]);
        if (cancelled) return;
        setReport(balance);
        setEntries(journal);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load the books");
      } finally {
        if (!cancelled) setBusy(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedGroupId]);

  const find = (code: string) => report?.accounts.find((a) => a.account_code === code)?.balance ?? 0;

  const owed = Number(find("member_savings"));
  const held = Number(find("lipila_settlement")) + Number(find("cash_on_hand"));
  const fees = Number(find("provider_fees"));
  const onLoan = Number(find("loans_receivable"));

  // Rows are one line per side, so both halves of an entry are visible together.
  const rows = entries.flatMap((entry) =>
    entry.lines.map((line, i) => ({
      id: `${entry.id}-${i}`,
      when: entry.created_at,
      description: entry.description ?? "",
      account: label(line.account_code),
      debit: Number(line.debit),
      credit: Number(line.credit),
    })),
  );

  const columns: GridColDef[] = [
    {
      field: "when",
      headerName: "When",
      minWidth: 150,
      valueFormatter: (v) => new Date(String(v)).toLocaleString(),
    },
    { field: "description", headerName: "Event", flex: 1, minWidth: 180 },
    { field: "account", headerName: "Account", minWidth: 180 },
    {
      field: "debit",
      headerName: "In",
      minWidth: 110,
      valueFormatter: (v) => (Number(v) ? currency(Number(v)) : ""),
    },
    {
      field: "credit",
      headerName: "Out",
      minWidth: 110,
      valueFormatter: (v) => (Number(v) ? currency(Number(v)) : ""),
    },
  ];

  return (
    <Box>
      <PageHeader
        title="Money"
        subtitle="Where the group's money came from, where it went, and what is left."
      />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {report && !report.control_total_matches && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Member balances do not match the entries behind them. A balance has moved without a
          record of where the money came from — check the audit trail.
        </Alert>
      )}
      {report && !report.balanced && (
        <Alert severity="error" sx={{ mb: 2 }}>
          The books do not balance. Treat every figure on this page as unreliable until it is
          resolved.
        </Alert>
      )}

      {busy && !report ? (
        <Stack alignItems="center" py={6}>
          <CircularProgress />
        </Stack>
      ) : (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} md={3}>
              <StatCard label="Owed to members" value={currency(owed)} icon={<GroupIcon color="action" />} loading={busy} helper="What the group must return" />
            </Grid>
            <Grid item xs={12} md={3}>
              <StatCard
                label="Money held"
                value={currency(held)}
                icon={<AccountBalanceWalletIcon color="action" />}
                loading={busy}
                helper={held < owed ? `${currency(owed - held)} short of what is owed` : "At Lipila and in cash"}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <StatCard label="Out on loan" value={currency(onLoan)} icon={<CreditCardIcon color="action" />} loading={busy} helper="Principal with borrowers" />
            </Grid>
            <Grid item xs={12} md={3}>
              <StatCard label="Fees paid" value={currency(fees)} icon={<ReceiptLongIcon color="action" />} loading={busy} helper="Kept by the provider" />
            </Grid>
          </Grid>

          {/* Money held is normally below money owed: the difference is what the
              provider took, plus anything currently lent out. Saying so beats
              leaving an admin to wonder why the two never agree. */}
          {report && held < owed && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Holding {currency(held)} against {currency(owed)} owed. {currency(onLoan)} is out on
              loan and {currency(fees)} has gone to provider fees.
            </Alert>
          )}

          <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Every account
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1}>
              {report?.accounts.map((row) => (
                <Chip
                  key={row.account_code}
                  label={`${label(row.account_code)}: ${currency(Number(row.balance))}`}
                  variant="outlined"
                />
              ))}
              {!report?.accounts.length && (
                <Typography variant="body2" color="text.secondary">
                  Nothing booked yet. Entries appear here as soon as money moves.
                </Typography>
              )}
            </Stack>
          </Paper>

          <Typography variant="subtitle2" gutterBottom>
            Recent movements
          </Typography>
          <Box height={460}>
            <DataGrid
              rows={rows}
              columns={columns}
              loading={busy}
              disableRowSelectionOnClick
              pageSizeOptions={[10, 25, 50]}
              initialState={{
                pagination: { paginationModel: { pageSize: 25, page: 0 } },
                density: "compact",
              }}
            />
          </Box>
        </>
      )}
    </Box>
  );
}
