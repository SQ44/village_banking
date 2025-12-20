import { Box, Typography } from "@mui/material";

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <Box display="flex" justifyContent="space-between" alignItems="flex-start" gap={2} mb={2}>
      <Box minWidth={0}>
        <Typography variant="h6">{title}</Typography>
        {subtitle && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {action ? <Box flexShrink={0}>{action}</Box> : null}
    </Box>
  );
}

