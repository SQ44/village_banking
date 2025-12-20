import { useMemo } from "react";
import { Box } from "@mui/material";
import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { PageHeader } from "../../components/PageHeader";
import { currency, formatDateTime } from "../../lib/format";
import { useMember } from "../memberContext";
import type { Transaction } from "../../types";

export default function MemberTransactionsPage() {
  const { busy, transactions } = useMember();
  const columns: GridColDef<Transaction>[] = useMemo(
    () => [
      { field: "created_at", headerName: "Date", width: 180, valueFormatter: (v) => formatDateTime(String(v)) },
      { field: "type", headerName: "Type", width: 160 },
      { field: "amount", headerName: "Amount", width: 140, valueFormatter: (v) => currency(Number(v)) },
      { field: "description", headerName: "Description", flex: 1, minWidth: 220 },
      { field: "status", headerName: "Status", width: 120 },
    ],
    []
  );
  return (
    <Box>
      <PageHeader title="Transactions" subtitle="Deposits, repayments, interest distribution, and adjustments." />
      <Box height={520}>
        <DataGrid
          rows={transactions}
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
