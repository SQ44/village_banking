import { createTheme } from "@mui/material/styles";
import type {} from "@mui/x-data-grid/themeAugmentation";

import { DataGridNoResultsOverlay, DataGridNoRowsOverlay } from "./components/DataGridOverlays";

export type ColorMode = "light" | "dark";

/**
 * One flat surface, one border colour, one accent. Decoration is deliberately
 * absent: gradients, drop shadows and hover lifts were competing with the
 * numbers on the dashboard, which are the only thing on screen that matters.
 */
const tokens = {
  light: {
    canvas: "#f5f6f8",
    surface: "#ffffff",
    surfaceMuted: "#fafbfc",
    border: "rgba(15,23,42,0.09)",
    textPrimary: "#0f172a",
    textSecondary: "#5b6573",
  },
  dark: {
    canvas: "#0b1120",
    surface: "#111a2b",
    surfaceMuted: "#0e1626",
    border: "rgba(148,163,184,0.16)",
    textPrimary: "#e8ebf0",
    textSecondary: "rgba(232,235,240,0.62)",
  },
} as const;

export function createAppTheme(mode: ColorMode) {
  const isDark = mode === "dark";
  const t = isDark ? tokens.dark : tokens.light;

  return createTheme({
    palette: {
      mode,
      primary: { main: isDark ? "#60a5fa" : "#2563eb" },
      secondary: { main: "#7c3aed" },
      background: {
        default: t.canvas,
        paper: t.surface,
      },
      text: {
        primary: t.textPrimary,
        secondary: t.textSecondary,
      },
      divider: t.border,
    },
    shape: {
      borderRadius: 10,
    },
    typography: {
      fontFamily: ['"Inter"', "system-ui", "-apple-system", '"Segoe UI"', "Roboto", "Arial", "sans-serif"].join(","),
      h5: { fontWeight: 650, letterSpacing: "-0.01em" },
      h6: { fontWeight: 650, letterSpacing: "-0.01em" },
      subtitle1: { fontWeight: 600, fontSize: "0.9375rem" },
      subtitle2: { fontWeight: 600 },
      // Section eyebrows and metric labels. Small, wide, quiet — they should
      // read as furniture, not as content.
      overline: {
        fontWeight: 600,
        fontSize: "0.6875rem",
        letterSpacing: "0.07em",
        lineHeight: 1.6,
      },
      button: { fontWeight: 550 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          "html, body": { height: "100%" },
          body: {
            margin: 0,
            colorScheme: mode,
            backgroundColor: t.canvas,
            WebkitFontSmoothing: "antialiased",
            MozOsxFontSmoothing: "grayscale",
          },
          "*:focus-visible": {
            outline: "2px solid",
            outlineColor: isDark ? "#60a5fa" : "#2563eb",
            outlineOffset: 2,
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: { textTransform: "none" },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { fontWeight: 550 },
        },
      },
      MuiCard: {
        defaultProps: { elevation: 0 },
        styleOverrides: {
          root: {
            border: `1px solid ${t.border}`,
            boxShadow: "none",
            backgroundImage: "none",
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: "none" },
        },
      },
      MuiAlert: {
        styleOverrides: {
          root: { border: `1px solid ${t.border}` },
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: { border: `1px solid ${t.border}` },
        },
      },
      MuiLinearProgress: {
        styleOverrides: {
          root: {
            height: 6,
            borderRadius: 999,
            backgroundColor: isDark ? "rgba(148,163,184,0.16)" : "rgba(15,23,42,0.07)",
          },
          bar: { borderRadius: 999 },
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
            border: `1px solid ${t.border}`,
            borderRadius: 10,
            backgroundColor: t.surface,
          },
          columnHeaders: {
            backgroundColor: t.surfaceMuted,
            borderBottom: `1px solid ${t.border}`,
          },
          columnHeaderTitle: {
            fontWeight: 600,
            fontSize: "0.8125rem",
            color: t.textSecondary,
          },
          row: {
            "&:hover": { backgroundColor: isDark ? "rgba(148,163,184,0.06)" : "rgba(15,23,42,0.02)" },
          },
          cell: {
            borderColor: t.border,
            alignItems: "center",
          },
          toolbarContainer: {
            padding: "8px 12px",
            borderBottom: `1px solid ${t.border}`,
            gap: 8,
          },
        },
      },
    },
  });
}
