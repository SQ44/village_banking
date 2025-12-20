import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ThemeProvider, useMediaQuery } from "@mui/material";

import { createAppTheme, type ColorMode } from "./theme";

const STORAGE_KEY = "vb_color_mode";

type ColorModeContextValue = {
  mode: ColorMode;
  setMode: (mode: ColorMode) => void;
  toggle: () => void;
};

const ColorModeContext = createContext<ColorModeContextValue | null>(null);

export function useColorMode() {
  const ctx = useContext(ColorModeContext);
  if (!ctx) throw new Error("useColorMode must be used within ColorModeProvider");
  return ctx;
}

export function ColorModeProvider({ children }: { children: React.ReactNode }) {
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");

  const [mode, setMode] = useState<ColorMode>(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as ColorMode | null;
    if (saved === "light" || saved === "dark") return saved;
    return prefersDark ? "dark" : "light";
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  const theme = useMemo(() => createAppTheme(mode), [mode]);
  const value = useMemo<ColorModeContextValue>(
    () => ({
      mode,
      setMode,
      toggle: () => setMode((prev) => (prev === "dark" ? "light" : "dark")),
    }),
    [mode]
  );

  return (
    <ColorModeContext.Provider value={value}>
      <ThemeProvider theme={theme}>{children}</ThemeProvider>
    </ColorModeContext.Provider>
  );
}

