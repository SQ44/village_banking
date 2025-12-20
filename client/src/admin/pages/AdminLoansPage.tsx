import { useMemo } from "react";
import { Alert, Box, Button } from "@mui/material";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { PageHeader } from "../../components/PageHeader";
import { StatusChip } from "../../components/StatusChip";
import { currency } from "../../lib/format";
import { useAdmin } from "../adminContext";
import type { Loan } from "../../types";

export default function AdminLoansPage() {
  const { busy, loans, constitutionLocked, openManualLoan, members } = useAdmin();
  const memberNameByAccountId = useMemo(() => {
    const map = new Map<number, string>();
    for (const m of members) map.set(Number(m.id), m.name);
    return map;
  }, [members]);
  const columns: GridColDef<Loan>[] = useMemo(
    () => [
      { field: "id", headerName: "Loan", width: 90 },
      {
        field: "borrower_account_id",
        headerName: "Borrower",
        width: 200,
        valueGetter: (_, row) => memberNameByAccountId.get(Number(row.borrower_account_id)) ?? `Account ${row.borrower_account_id}`,
      },
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
    [memberNameByAccountId]
  );
  return (
    <Box>
      <PageHeader
        title="Loans"
        subtitle="View active and historical loans."
        action={
          <Button variant="contained" startIcon={<CreditCardIcon />} disabled={constitutionLocked} onClick={openManualLoan}>
            Manual loan
          </Button>
        }
      />
      {constitutionLocked && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Manual loans are disabled because the constitution is locked (autonomous lending).
        </Alert>
      )}
      <Box height={520}>
        <DataGrid
          rows={loans}
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
    </Box>
  );
}
