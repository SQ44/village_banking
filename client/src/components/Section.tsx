import { Box, Card, CardContent, Typography } from "@mui/material";

/**
 * The single card shape used across the dashboard. Every panel gets the same
 * padding, the same heading size and the same border, so the eye can tell
 * content apart by its content rather than by its wrapper.
 */
export function Section({
  title,
  subtitle,
  action,
  dense,
  children,
}: {
  title: string;
  subtitle?: string;
  /** Rendered at the top right — a "View all" link, a status chip, nothing else. */
  action?: React.ReactNode;
  dense?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent
        sx={{
          p: dense ? { xs: 2, md: 2.25 } : { xs: 2.25, md: 2.75 },
          "&:last-child": { pb: dense ? { xs: 2, md: 2.25 } : { xs: 2.25, md: 2.75 } },
        }}
      >
        <Box display="flex" alignItems="flex-start" justifyContent="space-between" gap={2} mb={subtitle ? 2 : 1.75}>
          <Box minWidth={0}>
            <Typography variant="subtitle1">{title}</Typography>
            {subtitle && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
                {subtitle}
              </Typography>
            )}
          </Box>
          {action ? <Box flexShrink={0}>{action}</Box> : null}
        </Box>
        {children}
      </CardContent>
    </Card>
  );
}
