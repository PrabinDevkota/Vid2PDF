import { useEffect, useState } from "react";
import { AppHeader } from "../../components/AppHeader";
import { SectionCard } from "../../components/SectionCard";
import type { ProcessingMode } from "../../types";

const DEFAULT_MODE_KEY = "vid2pdf-default-mode";

async function checkHealth(): Promise<{ ok: boolean; message: string }> {
  const baseUrl =
    import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ||
    `${window.location.protocol}//${window.location.hostname}:8000`;

  try {
    const response = await fetch(`${baseUrl}/health`);
    if (!response.ok) {
      return { ok: false, message: `Backend returned ${response.status}` };
    }
    return { ok: true, message: "Backend is reachable and healthy." };
  } catch {
    return { ok: false, message: "Could not reach the backend API." };
  }
}

export function SettingsPage() {
  const [defaultMode, setDefaultMode] = useState<ProcessingMode>("screen");
  const [health, setHealth] = useState<{ ok: boolean; message: string } | null>(null);
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem(DEFAULT_MODE_KEY);
    if (stored === "screen" || stored === "camera") {
      setDefaultMode(stored);
    }
  }, []);

  useEffect(() => {
    setIsChecking(true);
    checkHealth()
      .then(setHealth)
      .finally(() => setIsChecking(false));
  }, []);

  function handleModeChange(mode: ProcessingMode) {
    setDefaultMode(mode);
    localStorage.setItem(DEFAULT_MODE_KEY, mode);
  }

  return (
    <main className="page-content">
      <AppHeader
        title="Settings"
        subtitle="Configure defaults and check system status."
      />

      <div className="settings-grid">
        <SectionCard
          title="Default processing mode"
          subtitle="Choose the default source type for new uploads."
        >
          <div className="mode-selector" role="tablist" aria-label="Default processing mode">
            <button
              className={`mode-pill ${defaultMode === "screen" ? "active" : ""}`}
              onClick={() => handleModeChange("screen")}
              role="tab"
              aria-selected={defaultMode === "screen"}
              type="button"
            >
              Screen recording
            </button>
            <button
              className={`mode-pill ${defaultMode === "camera" ? "active" : ""}`}
              onClick={() => handleModeChange("camera")}
              role="tab"
              aria-selected={defaultMode === "camera"}
              type="button"
            >
              Camera / physical pages
            </button>
          </div>
          <p className="muted settings-hint">
            Saved locally in your browser. New uploads will use this default.
          </p>
        </SectionCard>

        <SectionCard
          title="API status"
          subtitle="Connection to the Vid2PDF backend."
        >
          {isChecking ? (
            <div className="skeleton-list" aria-label="Checking API status">
              <span />
            </div>
          ) : health?.ok ? (
            <div className="status-banner">
              <strong>Connected</strong>
              <span>{health.message}</span>
            </div>
          ) : (
            <div className="status-banner status-banner--error">
              <strong>Disconnected</strong>
              <span>{health?.message}</span>
            </div>
          )}
        </SectionCard>
      </div>
    </main>
  );
}
