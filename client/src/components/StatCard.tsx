import { Box, Card, CardContent, Skeleton, Typography } from "@mui/material";

/**
 * The summary figures above the page content. Deliberately plainer than a
 * Section: a label, a number, and an icon held back to a hairline tint so a row
 * of four reads as one band rather than four competing tiles.
 *
 * The label wraps rather than truncating — on a phone these sit two to a row and
 * "Outstanding loans" does not fit on one line. The value is pushed to the
 * bottom so it still lines up across cards whose labels ran to different depths.
 */
export function StatCard({
  label,
  value,
  icon,
  loading,
  helper,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
  loading?: boolean;
  helper?: string;
}) {
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent
        sx={{
          p: 2,
          "&:last-child": { pb: 2 },
          height: "100%",
          display: "flex",
          flexDirection: "column",
        }}
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
          {helper ? (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              {helper}
            </Typography>
          ) : null}
        </Box>
      </CardContent>
    </Card>
  );
}
