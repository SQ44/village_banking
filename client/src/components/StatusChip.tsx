import { Chip } from "@mui/material";

export function StatusChip({ value }: { value: string }) {
  const v = String(value || "").toLowerCase();
  const map: Record<string, { label: string; color: "default" | "success" | "warning" | "error" | "info" }> = {
    approved: { label: "Approved", color: "success" },
    rejected: { label: "Rejected", color: "error" },
    requested: { label: "Requested", color: "info" },
    queued: { label: "Queued", color: "warning" },
    canceled: { label: "Canceled", color: "default" },
    active: { label: "Active", color: "info" },
    closed: { label: "Closed", color: "default" },
  };
  const entry = map[v] ?? { label: value, color: "default" as const };
  return <Chip size="small" variant="outlined" label={entry.label} color={entry.color} />;
}

