import { useCallback, useEffect, useState } from "react";

export type ThemePreference = "light" | "dark" | "system";

const THEME_KEY = "vid2pdf-theme";

function readStoredTheme(): ThemePreference {
  const stored = localStorage.getItem(THEME_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

function applyTheme(theme: ThemePreference) {
  if (theme === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", theme);
  }
}

export function useTheme(): {
  theme: ThemePreference;
  cycleTheme: () => void;
} {
  const [theme, setTheme] = useState<ThemePreference>(readStoredTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const cycleTheme = useCallback(() => {
    setTheme((current) => {
      const next: ThemePreference =
        current === "system" ? "dark" : current === "dark" ? "light" : "system";
      if (next === "system") {
        localStorage.removeItem(THEME_KEY);
      } else {
        localStorage.setItem(THEME_KEY, next);
      }
      return next;
    });
  }, []);

  return { theme, cycleTheme };
}
