import type { ProcessingJob } from "../../types";
import { SectionCard } from "../../components/SectionCard";

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
  return (
    <SectionCard
      eyebrow="Sessions"
      title="Sessions"
      subtitle="Each upload creates its own backend-backed reconstruction run and review set."
    >
      {isLoading ? (
        <div className="empty-state">
          <strong>Loading sessions</strong>
          <p>Reading the current reconstruction workspace.</p>
        </div>
      ) : jobs.length === 0 ? (
        <div className="empty-state">
          <strong>No sessions yet</strong>
          <p>Upload your first recording to start building a reviewable page set.</p>
        </div>
      ) : (
        <div className="job-list">
          {jobs.map((job) => (
            <button
              key={job.id}
              className={`job-tile ${activeJob?.id === job.id ? "active" : ""}`}
              onClick={() => onSelectJob(job.id)}
              type="button"
            >
              <div className="job-tile__head">
                <span className="job-tile__title">{job.filename}</span>
                <span className={`job-status job-status--${job.status}`}>{job.status}</span>
              </div>
              <div className="job-tile__meta-row">
                <span className="job-tile__meta">{job.pages.length} extracted pages</span>
                <span className="job-tile__meta">
                  {job.processingMode === "camera" ? "Camera / physical pages" : "Screen recording"}
                </span>
              </div>
              <span className="job-tile__meta">
                Created {new Date(job.createdAt).toLocaleDateString()}
              </span>
            </button>
          ))}
        </div>
      )}
    </SectionCard>
  );
}
