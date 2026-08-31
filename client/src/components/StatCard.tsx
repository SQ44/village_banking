import { Box, Card, CardContent, Skeleton, Typography } from "@mui/material";

type Tone = "success" | "warning" | "error" | "inherit";

/**
 * The headline figures above the page content. Deliberately plainer than a
 * Section: a label, a number, and at most one line of context beneath it.
 *
 * The label wraps rather than truncating — on a phone these sit two to a row and
 * "Members contributing" does not fit on one line. The value is pushed to the
 * bottom so it still lines up across cards whose labels ran to different depths.
 *
 * `tone` colours the value itself, and is meant for a figure whose *level* is
 * the message: a portfolio 12% in arrears should look different from one at 1%,
 * without the reader having to know where the threshold sits.
 */
export function StatCard({
  label,
  value,
  icon,
  loading,
  helper,
  helperIcon,
  helperTone,
  tone = "inherit",
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
  loading?: boolean;
  helper?: string;
  /** A trend arrow, shown before the helper text. */
  helperIcon?: React.ReactNode;
  helperTone?: Tone;
  tone?: Tone;
}) {
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent
        sx={{ p: 2, "&:last-child": { pb: 2 }, height: "100%", display: "flex", flexDirection: "column" }}
      >
        <Box display="flex" alignItems="flex-start" gap={1} mb={0.75}>
          {icon ? (
            <Box display="flex" color="text.secondary" sx={{ mt: "1px", "& svg": { fontSize: 18 } }}>
              {icon}
            </Box>
          ) : null}
          <Typography variant="overline" color="text.secondary">
            {label}
          </Typography>
        </Box>

        <Box mt="auto">
          {loading ? (
            <Skeleton width="60%" sx={{ fontSize: "1.5rem" }} />
          ) : (
            <Typography
              color={tone === "inherit" ? "text.primary" : `${tone}.main`}
              sx={{
                fontSize: { xs: "1.25rem", sm: "1.5rem" },
                fontWeight: 600,
                letterSpacing: "-0.02em",
                lineHeight: 1.25,
              }}
              noWrap
            >
              {value}
            </Typography>
          )}
          {helper && !loading ? (
            <Box
              display="flex"
              alignItems="center"
              gap={0.375}
              mt={0.5}
              sx={{ "& svg": { flexShrink: 0 } }}
              color={helperTone && helperTone !== "inherit" ? `${helperTone}.main` : "text.secondary"}
            >
              {helperIcon}
              <Typography variant="caption">{helper}</Typography>
            </Box>
          ) : null}
        </Box>
      </CardContent>
    </Card>
  );
}
