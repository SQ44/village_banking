import { Box, Card, CardContent, Skeleton, Typography } from "@mui/material";

export function StatCard({
  label,
  value,
  icon,
  loading,
  helper,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  loading?: boolean;
  helper?: string;
}) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
          <Typography variant="body2" color="text.secondary">
            {label}
          </Typography>
          {icon}
        </Box>
        {loading ? <Skeleton height={32} width="60%" /> : <Typography variant="h6">{value}</Typography>}
        {helper ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            {helper}
          </Typography>
        ) : null}
      </CardContent>
    </Card>
  );
}
