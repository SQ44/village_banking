import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#2563eb" },
    secondary: { main: "#7c3aed" },
    background: {
      default: "#f6f7fb",
      paper: "#ffffff",
    },
  },
  shape: {
    borderRadius: 12,
  },
  typography: {
    fontFamily: ['"Inter"', "system-ui", "-apple-system", '"Segoe UI"', "Roboto", "Arial", "sans-serif"].join(","),
    h5: { fontWeight: 700 },
    h6: { fontWeight: 700 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 600 },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: "1px solid rgba(15, 23, 42, 0.08)",
          boxShadow: "0 1px 2px rgba(15, 23, 42, 0.06)",
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { border: "1px solid rgba(15, 23, 42, 0.08)" },
      },
    },
  },
});
