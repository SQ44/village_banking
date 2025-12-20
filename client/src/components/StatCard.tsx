import { Box, Card, CardContent, Typography } from "@mui/material";

export function StatCard({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
          <Typography variant="body2" color="text.secondary">
            {label}
          </Typography>
          {icon}
        </Box>
        <Typography variant="h6">{value}</Typography>
      </CardContent>
    </Card>
  );
}

