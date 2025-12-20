import { useMemo, useState } from "react";
import { Alert, Box, Button } from "@mui/material";
import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { Api } from "../../api";
import { PageHeader } from "../../components/PageHeader";
import { ScorecardDialog, type ScorecardItem } from "../../components/ScorecardDialog";
import { StatusChip } from "../../components/StatusChip";
import { currency, formatDateTime } from "../../lib/format";
import { useMember } from "../memberContext";
import type { LoanRequest } from "../../types";

export default function MemberRequestsPage() {
  const { busy, requests, refresh, constitutionLocked, membershipAccepted, onError } = useMember();
  const [scorecardOpen, setScorecardOpen] = useState(false);
  const [scorecard, setScorecard] = useState<ScorecardItem[] | null>(null);
  const columns: GridColDef<LoanRequest>[] = useMemo(
    () => [
      { field: "id", headerName: "Request", width: 110 },
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
      { field: "decision_reason", headerName: "Reason", flex: 1, minWidth: 220, valueGetter: (_, row) => row.decision_reason ?? "" },
      { field: "created_at", headerName: "Created", width: 170, valueFormatter: (v) => formatDateTime(String(v)) },
      {
        field: "actions",
        headerName: "",
        width: 140,
        sortable: false,
        filterable: false,
        renderCell: ({ row }) => {
          if (row.status !== "requested" && row.status !== "queued") return null;
          return (
            <Button
              size="small"
              variant="outlined"
              color="error"
              disabled={busy}
              onClick={async () => {
                try {
                  await Api.cancelLoanRequest(row.id);
                  await refresh();
                } catch (err) {
                  onError(err instanceof Error ? err.message : "Failed to cancel request");
                }
              }}
            >
              Cancel
            </Button>
          );
        },
      },
    ],
    [busy, onError, refresh]
  );

  return (
    <Box>
      <PageHeader title="Requests" subtitle="Submit loan requests and see the system's decision scorecard (no gatekeeping)." />
      {!constitutionLocked && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Loan requests open after the group locks the constitution for this cycle.
        </Alert>
      )}
      {!membershipAccepted && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Accept group terms before requesting loans.
        </Alert>
      )}
      <Box height={520}>
        <DataGrid
          rows={requests}
          columns={columns}
          density="compact"
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
      </Box>
      <ScorecardDialog open={scorecardOpen} onClose={() => setScorecardOpen(false)} scorecard={scorecard} />
    </Box>
  );
}
