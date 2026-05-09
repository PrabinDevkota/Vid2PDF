import { SectionCard } from "../../components/SectionCard";
import type { ProcessingJob } from "../../types";

interface JobOverviewProps {
  jobs: ProcessingJob[];
  activeJob: ProcessingJob | null;
  isLoading: boolean;
  onSelectJob: (jobId: string) => void;
}

export function JobOverview({
  jobs,
  activeJob,
  isLoading,
  onSelectJob,
}: JobOverviewProps) {
  function formatDate(value: string) {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(value));
  }

  return (
    <SectionCard
      eyebrow="Sessions"
      title="Sessions"
      subtitle="Recent reconstruction runs and review sets."
    >
      {isLoading ? (
        <div className="skeleton-list" aria-label="Loading sessions">
          <span />
          <span />
          <span />
        </div>
      ) : jobs.length === 0 ? (
        <div className="empty-state empty-state--compact">
          <span className="empty-state__icon" aria-hidden="true" />
          <strong>No sessions yet</strong>
          <p>Upload your first document-viewing video to start building a PDF.</p>
          <span className="empty-state__cta">Create session above</span>
        </div>
      ) : (
        <div className="job-list">
          {jobs.map((job) => {
            const activePageCount = job.pages.filter((page) => !page.deleted).length;
            return (
              <button
                key={job.id}
                className={`job-tile ${activeJob?.id === job.id ? "active" : ""}`}
                onClick={() => onSelectJob(job.id)}
                type="button"
              >
                <div className="job-tile__head">
                  <span className="job-tile__title" title={job.filename}>
                    {job.filename}
                  </span>
                  <span className={`status-pill status-pill--${job.status}`}>{job.status}</span>
                </div>
                <div className="job-tile__meta-row">
                  <span className="mode-badge">
                    {job.processingMode === "camera" ? "Camera" : "Screen"}
                  </span>
                  <span className={`status-pill status-pill--${job.export.status}`}>
                    {job.export.status === "idle" ? "not exported" : job.export.status}
                  </span>
                </div>
                <div className="job-tile__detail-grid">
                  <span>{activePageCount} pages</span>
                  <span>Updated {formatDate(job.updatedAt)}</span>
                  <span>Created {formatDate(job.createdAt)}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}
