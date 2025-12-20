import { Box, Typography } from "@mui/material";
import InboxIcon from "@mui/icons-material/Inbox";
import SearchOffIcon from "@mui/icons-material/SearchOff";

function Overlay({
  icon,
  title,
  subtitle,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
}) {
  return (
    <Box
      height="100%"
      display="flex"
      alignItems="center"
      justifyContent="center"
      px={3}
      py={4}
      sx={{ textAlign: "center" }}
    >
      <Box>
        <Box
          sx={{
            width: 56,
            height: 56,
            borderRadius: 999,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background:
              "linear-gradient(135deg, rgba(37,99,235,0.14) 0%, rgba(124,58,237,0.10) 100%)",
            border: "1px solid rgba(37,99,235,0.18)",
            mb: 1.25,
          }}
        >
          {icon}
        </Box>
        <Typography variant="subtitle1" fontWeight={800}>
          {title}
        </Typography>
        {subtitle ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {subtitle}
          </Typography>
        ) : null}
      </Box>
    </Box>
  );
}

export function DataGridNoRowsOverlay() {
  return (
    <Overlay
      icon={<InboxIcon fontSize="small" />}
      title="Nothing here yet"
      subtitle="Once you have records, they will appear in this table."
    />
  );
}

export function DataGridNoResultsOverlay() {
  return (
    <Overlay
      icon={<SearchOffIcon fontSize="small" />}
      title="No matches"
      subtitle="Try adjusting your search or filters."
    />
  );
}

