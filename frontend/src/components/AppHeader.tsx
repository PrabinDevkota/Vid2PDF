import { Link } from "react-router-dom";
import { ChevronRight, Loader2 } from "lucide-react";
import type { ProcessingJob } from "../types";

interface AppHeaderProps {
  title: string;
  subtitle?: string;
  job?: ProcessingJob | null;
  stats?: { label: string; value: number | string }[];
  actions?: React.ReactNode;
  isLive?: boolean;
}

export function AppHeader({
  title,
  subtitle,
  job,
  stats,
  actions,
  isLive,
}: AppHeaderProps) {
  return (
    <header className="app-header">
      <div className="app-header__main">
        {job ? (
          <nav className="breadcrumbs" aria-label="Breadcrumb">
            <Link to="/app">Sessions</Link>
            <ChevronRight size={14} aria-hidden="true" />
            <span>{job.filename}</span>
          </nav>
        ) : null}
        <div className="app-header__title-row">
          <h1>{title}</h1>
          {isLive ? (
            <span className="live-badge">
              <Loader2 size={12} className="spin" aria-hidden="true" />
              Processing
            </span>
          ) : null}
          {job ? (
            <span className={`status-pill status-pill--${job.status}`}>
              {job.status}
            </span>
          ) : null}
        </div>
        {subtitle ? <p className="app-header__subtitle">{subtitle}</p> : null}
      </div>
      <div className="app-header__aside">
        {stats && stats.length > 0 ? (
          <div className="metric-cards" aria-label="Workspace stats">
            {stats.map((stat) => (
              <div className="metric-card" key={stat.label}>
                <span>{stat.label}</span>
                <strong>{stat.value}</strong>
              </div>
            ))}
          </div>
        ) : null}
        {actions ? <div className="app-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}
