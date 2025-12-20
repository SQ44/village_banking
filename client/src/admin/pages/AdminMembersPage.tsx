import { useMemo } from "react";
import { Alert, Box, Button } from "@mui/material";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";
import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { PageHeader } from "../../components/PageHeader";
import { currency } from "../../lib/format";
import { useAdmin } from "../adminContext";
import type { Account } from "../../types";

export default function AdminMembersPage() {
  const { busy, members, openInvite } = useAdmin();
  const columns: GridColDef<Account>[] = useMemo(
    () => [
      { field: "name", headerName: "Member", flex: 1, minWidth: 180 },
      { field: "email", headerName: "Email", flex: 1, minWidth: 220 },
      { field: "balance", headerName: "Savings", minWidth: 140, valueFormatter: (v) => currency(Number(v)) },
    ],
    []
  );
  return (
    <Box>
      <PageHeader
        title="Members"
        subtitle="Manage membership for this group."
        action={
          <Button variant="contained" startIcon={<PersonAddAlt1Icon />} onClick={openInvite}>
            Add member
          </Button>
        }
      />
      {members.length === 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>
          No members yet. Add your first member to start contributions and enable lending.
        </Alert>
      )}
      <Box height={520}>
        <DataGrid
          rows={members}
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
