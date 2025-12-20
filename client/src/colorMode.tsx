import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ThemeProvider, useMediaQuery } from "@mui/material";

import { createAppTheme } from "./theme";

const STORAGE_KEY = "vb_color_mode";

type ThemeMode = "light" | "dark";
type ColorPreference = ThemeMode | "system";

type ColorModeContextValue = {
  mode: ThemeMode;
  preference: ColorPreference;
  setPreference: (mode: ColorPreference) => void;
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

  const [preference, setPreference] = useState<ColorPreference>(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as ColorPreference | null;
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
    return "system";
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, preference);
  }, [preference]);

  const resolvedMode: ThemeMode = preference === "system" ? (prefersDark ? "dark" : "light") : preference;
  const theme = useMemo(() => createAppTheme(resolvedMode), [resolvedMode]);
  const value = useMemo<ColorModeContextValue>(
    () => ({
      mode: resolvedMode,
      preference,
      setPreference,
      toggle: () =>
        setPreference((prev) =>
          prev === "dark" || (prev === "system" && prefersDark) ? "light" : "dark"
        ),
    }),
    [prefersDark, preference, resolvedMode]
  );

  return (
    <ColorModeContext.Provider value={value}>
      <ThemeProvider theme={theme}>{children}</ThemeProvider>
    </ColorModeContext.Provider>
  );
}
