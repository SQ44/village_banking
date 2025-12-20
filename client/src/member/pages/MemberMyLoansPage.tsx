import { useMemo } from "react";
import { Alert, Box } from "@mui/material";
import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { PageHeader } from "../../components/PageHeader";
import { StatusChip } from "../../components/StatusChip";
import { currency } from "../../lib/format";
import { useMember } from "../memberContext";
import type { Loan } from "../../types";

export default function MemberMyLoansPage() {
  const { busy, myLoans, openRepay, membershipAccepted } = useMember();
  const columns: GridColDef<Loan>[] = useMemo(
    () => [
      { field: "id", headerName: "Loan", width: 90 },
      { field: "principal", headerName: "Principal", width: 140, valueFormatter: (v) => currency(Number(v)) },
      {
        field: "outstanding_principal",
        headerName: "Outstanding",
        width: 160,
        valueGetter: (_, row) => Number(row.outstanding_principal) + Number(row.outstanding_interest),
        valueFormatter: (v) => currency(Number(v)),
      },
      { field: "status", headerName: "Status", width: 120, renderCell: ({ value }) => <StatusChip value={String(value)} /> },
    ],
    []
  );
  return (
    <Box>
      <PageHeader title="My loans" subtitle="Click a loan to make a repayment (interest first, then principal)." />
      {!membershipAccepted && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Accept group terms before repaying loans.
        </Alert>
      )}
      <Box height={520}>
        <DataGrid
          rows={myLoans}
          columns={columns}
          density="compact"
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.id}
          onRowClick={(params) => openRepay(Number(params.id))}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
      </Box>
    </Box>
  );
}
