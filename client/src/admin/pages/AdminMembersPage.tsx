import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";
import PaymentsIcon from "@mui/icons-material/Payments";
import { DataGrid, GridToolbar, type GridColDef } from "@mui/x-data-grid";

import { Api } from "../../api";
import { PageHeader } from "../../components/PageHeader";
import { currency } from "../../lib/format";
import { useAdmin } from "../adminContext";
import type { Account, ContributionMethod } from "../../types";

/** What a member still owes on joining, if anything.
 *
 *  The server stores this as a decimal string, because the column is JSON and
 *  JSON has no exact decimal type — a number there would reintroduce the
 *  rounding error the ledger was converted away from. Older accounts still hold
 *  a raw number, so both are accepted. */
function amountDue(member: Account): number | null {
  const due = member.custom_fields?.initial_contribution_due;
  if (due === null || due === undefined) return null;
  const value = typeof due === "number" ? due : Number(due);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export default function AdminMembersPage() {
  const { busy, members, openInvite, selectedGroupId, refresh } = useAdmin();

  const [target, setTarget] = useState<Account | null>(null);
  const [amount, setAmount] = useState(0);
  const [phone, setPhone] = useState("");
  const [method, setMethod] = useState<ContributionMethod>("lipila");
  const [cashReason, setCashReason] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  const openCollect = (member: Account) => {
    setTarget(member);
    setAmount(amountDue(member) ?? 0);
    setPhone(String(member.custom_fields?.phone ?? ""));
    setMethod("lipila");
    setCashReason("");
    setError(null);
    setSent(null);
  };

  const columns: GridColDef<Account>[] = useMemo(
    () => [
      { field: "name", headerName: "Member", flex: 1, minWidth: 180 },
      { field: "email", headerName: "Email", flex: 1, minWidth: 220 },
      { field: "balance", headerName: "Savings", minWidth: 130, valueFormatter: (v) => currency(Number(v)) },
      {
        field: "custom_fields",
        headerName: "Owed",
        minWidth: 130,
        sortable: false,
        renderCell: ({ row }) => {
          const due = amountDue(row);
          return due ? <Chip size="small" color="warning" label={currency(due)} /> : null;
        },
      },
      {
        field: "actions",
        headerName: "",
        minWidth: 150,
        sortable: false,
        filterable: false,
        renderCell: ({ row }) => (
          <Button size="small" startIcon={<PaymentsIcon />} onClick={() => openCollect(row)}>
            {amountDue(row) ? "Collect" : "Request"}
          </Button>
        ),
      },
    ],
    []
  );

  const submit = async () => {
    if (!target || !selectedGroupId) return;
    setSending(true);
    setError(null);
    try {
      const payment = await Api.collectMemberContribution(Number(selectedGroupId), Number(target.id), {
        amount,
        method,
        phone_number: method === "lipila" ? phone.trim() || undefined : undefined,
        cash_reason: method === "cash" ? cashReason.trim() : undefined,
      });
      // `already_pending` means the server found a prompt still waiting on this
      // member's handset and handed that one back rather than sending a second.
      // Saying "sent" here would be a lie, and would invite another press.
      setSent(
        method === "cash"
          ? `${currency(payment.amount)} banked as cash for ${target.name}.`
          : payment.already_pending
            ? `${target.name} already has a prompt for ${currency(payment.amount)} waiting on their phone. No second request was sent.`
            : `Prompt for ${currency(payment.amount)} sent to ${target.name}. Their savings update once they approve it.`
      );
      setTarget(null);
      await refresh(Number(selectedGroupId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to request the contribution");
    } finally {
      setSending(false);
    }
  };

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
      {sent && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSent(null)}>
          {sent}
        </Alert>
      )}
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

      <Dialog open={Boolean(target)} onClose={() => setTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>Request contribution</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {method === "cash"
                ? `Banked immediately on your word. No provider confirms it, so the reason is kept against your name.`
                : `${target?.name ?? "The member"} gets a prompt on their phone. Their savings update only once they approve it.`}
            </Typography>
            <FormControl fullWidth>
              <InputLabel id="collect-method-label">Method</InputLabel>
              <Select
                labelId="collect-method-label"
                label="Method"
                value={method}
                onChange={(e) => setMethod(e.target.value as ContributionMethod)}
              >
                <MenuItem value="lipila">Request on their phone</MenuItem>
                <MenuItem value="cash">Cash received</MenuItem>
              </Select>
            </FormControl>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Amount"
              type="number"
              fullWidth
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
            />
            {method === "lipila" ? (
              <TextField
                label="Mobile number"
                fullWidth
                name="collect-phone"
                autoComplete="off"
                placeholder="0977123456"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            ) : (
              <TextField
                label="Reason"
                fullWidth
                name="collect-cash-reason"
                autoComplete="off"
                placeholder="Cash handed over at the meeting"
                value={cashReason}
                onChange={(e) => setCashReason(e.target.value)}
                helperText="Recorded against your name in the audit log."
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTarget(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              sending ||
              amount <= 0 ||
              (method === "lipila" && !phone.trim()) ||
              (method === "cash" && !cashReason.trim())
            }
            onClick={submit}
          >
            {sending ? "Saving..." : method === "cash" ? "Record cash" : "Send prompt"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
