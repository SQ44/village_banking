import { Box, Chip, Dialog, DialogContent, DialogTitle, Divider, Typography } from "@mui/material";

export type ScorecardItem = {
  rule?: string;
  pass?: boolean;
  detail?: string;
};

export function ScorecardDialog({
  open,
  onClose,
  scorecard,
}: {
  open: boolean;
  onClose: () => void;
  scorecard: ScorecardItem[] | null;
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Decision scorecard</DialogTitle>
      <DialogContent>
        {!scorecard?.length ? (
          <Typography variant="body2" color="text.secondary">
            No scorecard available.
          </Typography>
        ) : (
          <Box>
            {scorecard.map((item, idx) => (
              <Box key={`${item.rule ?? "rule"}-${idx}`} py={1.5}>
                <Box display="flex" alignItems="center" justifyContent="space-between" gap={1}>
                  <Typography variant="subtitle2">{item.rule ?? "Rule"}</Typography>
                  <Chip size="small" label={item.pass ? "Pass" : "Fail"} color={item.pass ? "success" : "error"} />
                </Box>
                {item.detail && (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                    {item.detail}
                  </Typography>
                )}
                {idx < scorecard.length - 1 && <Divider sx={{ mt: 1.5 }} />}
              </Box>
            ))}
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}

