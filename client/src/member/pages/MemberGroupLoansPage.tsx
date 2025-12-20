import { useMemo } from "react";
import { Box } from "@mui/material";
import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { PageHeader } from "../../components/PageHeader";
import { StatusChip } from "../../components/StatusChip";
import { currency, formatDate } from "../../lib/format";
import { useMember } from "../memberContext";
import type { LoanBoardItem } from "../../types";

export default function MemberGroupLoansPage() {
  const { busy, groupLoans, forecast } = useMember();
  const forecastByLoanId = useMemo(() => {
    const map = new Map<number, number>();
    for (const item of forecast?.loans ?? []) map.set(Number(item.loan_id), Number(item.my_expected_interest ?? 0));
    return map;
  }, [forecast]);
  const columns: GridColDef<LoanBoardItem>[] = useMemo(
    () => [
      { field: "borrower_name", headerName: "Borrower", flex: 1, minWidth: 180 },
      { field: "principal", headerName: "Principal", width: 140, valueFormatter: (v) => currency(Number(v)) },
      {
        field: "outstanding",
        headerName: "Outstanding",
        width: 160,
        valueGetter: (_, row) => Number(row.outstanding_principal) + Number(row.outstanding_interest),
        valueFormatter: (v) => currency(Number(v)),
      },
      { field: "next_due_date", headerName: "Next due", width: 160, valueGetter: (_, row) => row.next_due_date ?? "", valueFormatter: (v) => formatDate(String(v)) },
      {
        field: "my_expected_interest",
        headerName: "My expected interest",
        width: 180,
        valueGetter: (_, row) => forecastByLoanId.get(Number(row.id)) ?? 0,
        valueFormatter: (v) => currency(Number(v)),
      },
      { field: "status", headerName: "Status", width: 120, renderCell: ({ value }) => <StatusChip value={String(value)} /> },
    ],
    [forecastByLoanId]
  );
  return (
    <Box>
      <PageHeader title="Group loans" subtitle="Transparency board: outstanding loans and your expected interest share." />
      <Box height={520}>
        <DataGrid
          rows={groupLoans}
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
    </Box>
  );
}
