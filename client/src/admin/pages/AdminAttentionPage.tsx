import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import SyncProblemIcon from "@mui/icons-material/SyncProblem";
import ReportProblemIcon from "@mui/icons-material/ReportProblem";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";

import { Api } from "../../api";
import { PageHeader } from "../../components/PageHeader";
import { currency } from "../../lib/format";
import { useAdmin } from "../adminContext";
import type { AttentionReport, AuditEntry } from "../../types";

/** How long a member has been waiting, in words rather than minutes. */
function waited(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr`;
  return `${Math.floor(hours / 24)} d`;
}

function Section({
  title,
  description,
  count,
  severity,
  children,
}: {
  title: string;
  description: string;
  count: number;
  severity: "error" | "warning";
  children: React.ReactNode;
}) {
  // A clean section still renders, saying so. An operator needs to know the
  // check ran and found nothing, which is different from the page being blank.
  return (
    <Paper variant="outlined" sx={{ mb: 3, overflow: "hidden" }}>
      <Box px={2} py={1.5} display="flex" alignItems="center" gap={1}>
        {count > 0 ? (
          <ReportProblemIcon color={severity} fontSize="small" />
        ) : (
          <CheckCircleIcon color="success" fontSize="small" />
        )}
        <Typography variant="subtitle1" fontWeight={600}>
          {title}
        </Typography>
        {count > 0 && <Chip size="small" color={severity} label={count} />}
      </Box>
      <Typography variant="body2" color="text.secondary" px={2} pb={1.5}>
        {description}
      </Typography>
      <Divider />
      {count === 0 ? (
        <Typography variant="body2" color="text.secondary" px={2} py={2}>
          Nothing to do here.
        </Typography>
      ) : (
        children
      )}
    </Paper>
  );
}

export default function AdminAttentionPage() {
  const { selectedGroupId } = useAdmin();
  const [report, setReport] = useState<AttentionReport | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [attention, trail] = await Promise.all([
        Api.getAttention(selectedGroupId ? Number(selectedGroupId) : undefined),
        Api.getAuditTrail(25).catch(() => [] as AuditEntry[]),
      ]);
      setReport(attention);
      setAudit(trail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the attention queue");
    } finally {
      setBusy(false);
    }
  }, [selectedGroupId]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalIssues = report
    ? report.stuck_payments.length +
      report.dead_letter_events.length +
      report.balance_discrepancies.length +
      report.negative_balances.length
    : 0;

  return (
    <Box>
      <PageHeader
        title="Needs attention"
        subtitle="Payments that will not resolve themselves, and balances the ledger cannot explain."
        action={
          <Button startIcon={<RefreshIcon />} onClick={() => void load()} disabled={busy}>
            Refresh
          </Button>
        }
      />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {busy && !report && (
        <Box display="flex" justifyContent="center" py={6}>
          <CircularProgress />
        </Box>
      )}

      {report && totalIssues === 0 && (
        <Alert severity="success" icon={<CheckCircleIcon />} sx={{ mb: 3 }}>
          Everything reconciles. {report.accounts_checked} account
          {report.accounts_checked === 1 ? "" : "s"} checked, no payments waiting on a decision.
        </Alert>
      )}

      {report && (
        <>
          <Section
            title="Payments waiting on a decision"
            description="A member's money is in limbo. Either the provider gave an answer we could not trust, or no confirmation ever arrived. Their balance has correctly not moved — but somebody has to tell them what happened."
            count={report.stuck_payments.length}
            severity="error"
          >
            <TableContainer sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Member</TableCell>
                    <TableCell>Amount</TableCell>
                    <TableCell>Waiting</TableCell>
                    <TableCell>Why</TableCell>
                    <TableCell>Reference</TableCell>
                    <TableCell align="right">Action</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {report.stuck_payments.map((item) => (
                    <TableRow key={item.transaction_id}>
                      <TableCell>{item.account_name}</TableCell>
                      <TableCell>{currency(item.amount)}</TableCell>
                      <TableCell>{waited(item.minutes_waiting)}</TableCell>
                      <TableCell>
                        <Tooltip
                          title={
                            item.reason === "needs_review"
                              ? "The provider's answer did not match our ledger, or could not be read as paid or not paid."
                              : "No webhook arrived and the poller could not resolve it either."
                          }
                        >
                          <Chip
                            size="small"
                            color={item.reason === "needs_review" ? "error" : "warning"}
                            label={item.reason === "needs_review" ? "Needs review" : "No confirmation"}
                          />
                        </Tooltip>
                      </TableCell>
                      <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>
                        {item.provider_reference ?? "—"}
                      </TableCell>
                      <TableCell align="right">
                        <Button
                          size="small"
                          startIcon={<SyncProblemIcon />}
                          onClick={async () => {
                            try {
                              await Api.refreshTransaction(item.transaction_id);
                              await load();
                            } catch (err) {
                              setError(err instanceof Error ? err.message : "Could not re-check the payment");
                            }
                          }}
                        >
                          Re-check
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Section>

          <Section
            title="Unmatched provider messages"
            description="The provider told us about money we cannot match to any transaction. Each of these needs to be traced by hand before it is dismissed."
            count={report.dead_letter_events.length}
            severity="error"
          >
            <TableContainer sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Received</TableCell>
                    <TableCell>Reference</TableCell>
                    <TableCell>Webhook id</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {report.dead_letter_events.map((event) => (
                    <TableRow key={event.event_id}>
                      <TableCell>{new Date(event.created_at).toLocaleString()}</TableCell>
                      <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>
                        {event.provider_reference ?? "(none in payload)"}
                      </TableCell>
                      <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{event.webhook_id}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Section>

          <Section
            title="Balances the ledger does not explain"
            description="A member's savings should always equal the sum of their entries. Where they differ, the number cannot be defended in a meeting — so it is reported rather than quietly corrected."
            count={report.balance_discrepancies.length + report.negative_balances.length}
            severity="warning"
          >
            <TableContainer sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Member</TableCell>
                    <TableCell>Shown</TableCell>
                    <TableCell>Entries add up to</TableCell>
                    <TableCell>Difference</TableCell>
                    <TableCell>Entries</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {[...report.balance_discrepancies, ...report.negative_balances].map((item) => (
                    <TableRow key={`${item.account_id}-${item.difference}`}>
                      <TableCell>{item.account_name}</TableCell>
                      <TableCell>{currency(item.stored_balance)}</TableCell>
                      <TableCell>{currency(item.derived_balance)}</TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          color={item.difference === 0 ? "warning" : "error"}
                          label={
                            item.difference === 0
                              ? "Overdrawn"
                              : `${item.difference > 0 ? "+" : ""}${currency(item.difference)}`
                          }
                        />
                      </TableCell>
                      <TableCell>{item.transaction_count}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Section>

          <Paper variant="outlined" sx={{ overflow: "hidden" }}>
            <Box px={2} py={1.5}>
              <Typography variant="subtitle1" fontWeight={600}>
                Hand-made changes
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Every balance moved by a person rather than by a payment, and the reason they gave.
              </Typography>
            </Box>
            <Divider />
            {audit.length === 0 ? (
              <Typography variant="body2" color="text.secondary" px={2} py={2}>
                No balance has been changed by hand.
              </Typography>
            ) : (
              <TableContainer sx={{ overflowX: "auto" }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>When</TableCell>
                      <TableCell>Who</TableCell>
                      <TableCell>What</TableCell>
                      <TableCell>Reason</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {audit.map((entry) => (
                      <TableRow key={entry.id}>
                        <TableCell>{new Date(entry.created_at).toLocaleString()}</TableCell>
                        <TableCell>{entry.actor_email ?? "(system)"}</TableCell>
                        <TableCell>
                          <Stack spacing={0.25}>
                            <Typography variant="body2">{entry.action}</Typography>
                            <Typography variant="caption" color="text.secondary">
                              {entry.entity_type} #{entry.entity_id}
                            </Typography>
                          </Stack>
                        </TableCell>
                        <TableCell>{entry.reason ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Paper>
        </>
      )}
    </Box>
  );
}
