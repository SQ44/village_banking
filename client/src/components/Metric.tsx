import { Box, Skeleton, Typography } from "@mui/material";

/**
 * A labelled figure. Label above, value below, nothing else — the dashboard has
 * enough of these that any per-metric decoration multiplies into clutter.
 */
export function Metric({
  label,
  value,
  loading,
  size = "md",
}: {
  label: string;
  value: string;
  loading?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  const fontSize = size === "lg" ? "1.5rem" : size === "sm" ? "1rem" : "1.25rem";

  return (
    <Box minWidth={0}>
      <Typography variant="overline" color="text.secondary" display="block">
        {label}
      </Typography>
      {loading ? (
        <Skeleton width="70%" sx={{ fontSize }} />
      ) : (
        <Typography sx={{ fontSize, fontWeight: 600, letterSpacing: "-0.02em", lineHeight: 1.3 }} noWrap>
          {value}
        </Typography>
      )}
    </Box>
  );
}
