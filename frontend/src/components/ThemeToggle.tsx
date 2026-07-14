import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemePreference } from "../hooks/useTheme";

const LABELS: Record<ThemePreference, string> = {
  system: "Theme: follows your system",
  dark: "Theme: dark",
  light: "Theme: light",
};

export function ThemeToggle({ showLabel = false }: { showLabel?: boolean }) {
  const { theme, cycleTheme } = useTheme();
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <button
      className={showLabel ? "nav-item theme-toggle" : "icon-button theme-toggle"}
      onClick={cycleTheme}
      title={`${LABELS[theme]} — click to change`}
      type="button"
    >
      <Icon size={showLabel ? 17 : 15} aria-hidden="true" />
      {showLabel ? (
        <span className="nav-item__label">
          {theme === "system" ? "System theme" : theme === "dark" ? "Dark theme" : "Light theme"}
        </span>
      ) : null}
    </button>
  );
}
