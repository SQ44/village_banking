import { useMemo } from "react";
import { Box } from "@mui/material";
import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { PageHeader } from "../../components/PageHeader";
import { currency } from "../../lib/format";
import { useMember } from "../memberContext";
import type { GroupContributionItem } from "../../types";

export default function MemberSharesPage() {
  const { busy, contributions } = useMember();
  const columns: GridColDef<GroupContributionItem>[] = useMemo(
    () => [
      { field: "member_name", headerName: "Member", flex: 1, minWidth: 180 },
      { field: "net_contribution", headerName: "Net contribution", width: 170, valueFormatter: (v) => currency(Number(v)) },
      { field: "share_percent", headerName: "Share", width: 120, valueFormatter: (v) => `${Number(v).toFixed(2)}%` },
    ],
    []
  );
  return (
    <Box>
      <PageHeader title="Shares" subtitle="Contribution shares are used to split loan interest (after admin fee) across members." />
      <Box height={520}>
        <DataGrid
          rows={contributions}
          columns={columns}
          density="compact"
          disableRowSelectionOnClick
          loading={busy}
          getRowId={(row) => row.account_id}
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
          slots={{ toolbar: GridToolbar }}
          slotProps={{ toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 250 } } }}
        />
      </Box>
    </Box>
  );
}
