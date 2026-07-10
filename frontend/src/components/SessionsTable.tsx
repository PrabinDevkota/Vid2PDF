import { useMemo, useState } from "react";
import { FileVideo, Search } from "lucide-react";
import type { ProcessingJob } from "../types";

interface SessionsTableProps {
  jobs: ProcessingJob[];
  activeJobId?: string | null;
  isLoading: boolean;
  onSelectJob: (jobId: string) => void;
  limit?: number;
  showViewAll?: boolean;
  onViewAll?: () => void;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function SessionsTable({
  jobs,
  activeJobId,
  isLoading,
  onSelectJob,
  limit,
  showViewAll,
  onViewAll,
}: SessionsTableProps) {
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);

  const filteredJobs = useMemo(() => {
    const query = search.trim().toLowerCase();
    const sorted = [...jobs].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    );
    const filtered = query
      ? sorted.filter((job) => job.filename.toLowerCase().includes(query))
      : sorted;
    const effectiveLimit = showAll ? undefined : limit;
    return effectiveLimit ? filtered.slice(0, effectiveLimit) : filtered;
  }, [jobs, search, limit, showAll]);

  if (isLoading) {
    return (
      <div className="skeleton-table" aria-label="Loading sessions">
        <span />
        <span />
        <span />
        <span />
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="empty-state empty-state--compact">
        <FileVideo className="empty-state__lucide-icon" size={32} aria-hidden="true" />
        <strong>No sessions yet</strong>
        <p>Upload your first document-viewing video to start building a PDF.</p>
        <span className="empty-state__cta">Upload a video above to get started</span>
      </div>
    );
  }

  return (
    <div className="sessions-table-wrap">
      <div className="sessions-table-toolbar">
        <div className="search-input">
          <Search size={16} aria-hidden="true" />
          <input
            aria-label="Search sessions"
            placeholder="Search by filename..."
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        {showViewAll && limit && jobs.length > limit ? (
          <button
            className="secondary-button secondary-button--quiet"
            onClick={() => {
              setShowAll((current) => !current);
              onViewAll?.();
            }}
            type="button"
          >
            {showAll ? "Show less" : `View all (${jobs.length})`}
          </button>
        ) : null}
      </div>

      <div className="sessions-table" role="table">
        <div className="sessions-table__head" role="row">
          <span role="columnheader">Name</span>
          <span role="columnheader">Status</span>
          <span role="columnheader">Mode</span>
          <span role="columnheader">Pages</span>
          <span role="columnheader">Export</span>
          <span role="columnheader">Updated</span>
        </div>
        {filteredJobs.length === 0 ? (
          <div className="sessions-table__empty">
            <p>No sessions match &ldquo;{search}&rdquo;</p>
          </div>
        ) : (
          filteredJobs.map((job) => {
            const activePageCount = job.pages.filter((page) => !page.deleted).length;
            return (
              <button
                key={job.id}
                className={`sessions-table__row ${activeJobId === job.id ? "sessions-table__row--active" : ""}`}
                onClick={() => onSelectJob(job.id)}
                role="row"
                type="button"
              >
                <span className="sessions-table__name" role="cell" title={job.filename}>
                  {job.filename}
                </span>
                <span role="cell">
                  <span className={`status-pill status-pill--${job.status}`}>
                    {job.status}
                  </span>
                </span>
                <span role="cell">
                  <span className="mode-badge">
                    {job.processingMode === "camera" ? "Camera" : "Screen"}
                  </span>
                </span>
                <span role="cell">{activePageCount}</span>
                <span role="cell">
                  <span className={`status-pill status-pill--${job.export.status}`}>
                    {job.export.status === "idle" ? "not exported" : job.export.status}
                  </span>
                </span>
                <span className="sessions-table__date" role="cell">
                  {formatDate(job.updatedAt)}
                </span>
              </button>
            );
          })
        )}
      </div>

      <div className="sessions-cards" aria-label="Sessions list">
        {filteredJobs.map((job) => {
          const activePageCount = job.pages.filter((page) => !page.deleted).length;
          return (
            <button
              key={job.id}
              className={`session-card ${activeJobId === job.id ? "session-card--active" : ""}`}
              onClick={() => onSelectJob(job.id)}
              type="button"
            >
              <div className="session-card__head">
                <strong title={job.filename}>{job.filename}</strong>
                <span className={`status-pill status-pill--${job.status}`}>
                  {job.status}
                </span>
              </div>
              <div className="session-card__meta">
                <span className="mode-badge">
                  {job.processingMode === "camera" ? "Camera" : "Screen"}
                </span>
                <span>{activePageCount} pages</span>
                <span>{formatDate(job.updatedAt)}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
