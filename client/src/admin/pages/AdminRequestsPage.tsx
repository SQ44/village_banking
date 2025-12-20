import { useMemo, useState } from "react";
import { Alert, Box, Button } from "@mui/material";
import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { PageHeader } from "../../components/PageHeader";
import { ScorecardDialog, type ScorecardItem } from "../../components/ScorecardDialog";
import { StatusChip } from "../../components/StatusChip";
import { currency, formatDateTime } from "../../lib/format";
import { useAdmin } from "../adminContext";
import type { LoanRequest } from "../../types";

export default function AdminRequestsPage() {
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
