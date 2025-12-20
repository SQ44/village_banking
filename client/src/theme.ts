import { createTheme } from "@mui/material/styles";
import type {} from "@mui/x-data-grid/themeAugmentation";

import { DataGridNoResultsOverlay, DataGridNoRowsOverlay } from "./components/DataGridOverlays";

export type ColorMode = "light" | "dark";

export function createAppTheme(mode: ColorMode) {
  const isDark = mode === "dark";

  return createTheme({
    palette: {
      mode,
      primary: { main: "#2563eb" },
      secondary: { main: "#7c3aed" },
      background: {
        default: isDark ? "#0b1220" : "#f6f7fb",
        paper: isDark ? "#0f172a" : "#ffffff",
      },
      text: {
        primary: isDark ? "#e5e7eb" : "#0f172a",
        secondary: isDark ? "rgba(229,231,235,0.72)" : "rgba(15,23,42,0.7)",
      },
      divider: isDark ? "rgba(148,163,184,0.18)" : "rgba(15,23,42,0.08)",
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
      MuiCssBaseline: {
        styleOverrides: {
          "html, body": {
            height: "100%",
          },
          body: {
            margin: 0,
            colorScheme: mode,
            background: isDark
              ? "radial-gradient(1000px 520px at 20% 0%, rgba(37, 99, 235, 0.16), transparent 60%), radial-gradient(800px 520px at 80% 10%, rgba(124, 58, 237, 0.14), transparent 55%), #0b1220"
              : "radial-gradient(900px 480px at 20% 0%, rgba(37, 99, 235, 0.10), transparent 60%), radial-gradient(700px 420px at 80% 10%, rgba(124, 58, 237, 0.09), transparent 55%), #f6f7fb",
            WebkitFontSmoothing: "antialiased",
            MozOsxFontSmoothing: "grayscale",
          },
          "*:focus-visible": {
            outline: "3px solid rgba(37,99,235,0.55)",
            outlineOffset: 2,
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: {
            textTransform: "none",
            fontWeight: 600,
            transition: "transform 140ms ease, box-shadow 140ms ease, background-color 140ms ease",
            "&:hover": { transform: "translateY(-1px)" },
            "&.Mui-disabled": { transform: "none" },
          },
        },
      },
      MuiIconButton: {
        styleOverrides: {
          root: {
            transition: "transform 140ms ease, background-color 140ms ease",
            "&:hover": { transform: "translateY(-1px)" },
            "&.Mui-disabled": { transform: "none" },
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            border: isDark ? "1px solid rgba(148,163,184,0.18)" : "1px solid rgba(15, 23, 42, 0.08)",
            boxShadow: isDark ? "0 1px 2px rgba(0,0,0,0.35)" : "0 1px 2px rgba(15, 23, 42, 0.06)",
            transition: "transform 160ms ease, box-shadow 160ms ease",
            "&:hover": {
              transform: "translateY(-1px)",
              boxShadow: isDark ? "0 10px 24px rgba(0,0,0,0.45)" : "0 10px 24px rgba(15,23,42,0.10)",
            },
          },
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: { border: isDark ? "1px solid rgba(148,163,184,0.20)" : "1px solid rgba(15, 23, 42, 0.08)" },
        },
      },
      MuiDataGrid: {
        defaultProps: {
          slots: {
            noRowsOverlay: DataGridNoRowsOverlay,
            noResultsOverlay: DataGridNoResultsOverlay,
          },
        },
        styleOverrides: {
          root: {
            border: isDark ? "1px solid rgba(148,163,184,0.22)" : "1px solid rgba(15, 23, 42, 0.10)",
            borderRadius: 12,
            backgroundColor: isDark ? "#0f172a" : "#ffffff",
          },
          columnHeaders: {
            background: isDark
              ? "linear-gradient(90deg, rgba(37,99,235,0.16) 0%, rgba(124,58,237,0.12) 60%, rgba(15,23,42,0.85) 100%)"
              : "linear-gradient(90deg, rgba(37,99,235,0.06) 0%, rgba(124,58,237,0.05) 60%, rgba(255,255,255,0.70) 100%)",
            borderBottom: isDark ? "1px solid rgba(148,163,184,0.20)" : "1px solid rgba(15, 23, 42, 0.10)",
          },
          columnHeaderTitle: { fontWeight: 700 },
          row: {
            transition: "background-color 120ms ease",
            "&:hover": { backgroundColor: isDark ? "rgba(37,99,235,0.10)" : "rgba(37,99,235,0.05)" },
          },
          cell: {
            borderColor: isDark ? "rgba(148,163,184,0.12)" : "rgba(15, 23, 42, 0.06)",
            alignItems: "center",
          },
          toolbarContainer: {
            padding: "10px 12px",
            borderBottom: isDark ? "1px solid rgba(148,163,184,0.16)" : "1px solid rgba(15, 23, 42, 0.08)",
            gap: 8,
          },
        },
      },
    },
  });
}
