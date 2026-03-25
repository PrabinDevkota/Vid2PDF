import type { ProcessingJob } from "../../types";
import { SectionCard } from "../../components/SectionCard";

interface JobOverviewProps {
  jobs: ProcessingJob[];
  activeJob: ProcessingJob | null;
  onSelectJob: (jobId: string) => void;
}

export function JobOverview({
  jobs,
  activeJob,
  onSelectJob,
}: JobOverviewProps) {
  return (
    <SectionCard eyebrow="Jobs" title="Processing sessions">
      {jobs.length === 0 ? (
        <p className="muted">No jobs yet. Upload a recording to create one.</p>
      ) : (
        <div className="job-list">
          {jobs.map((job) => (
            <button
              key={job.id}
              className={`job-tile ${activeJob?.id === job.id ? "active" : ""}`}
              onClick={() => onSelectJob(job.id)}
              type="button"
            >
              <span className="job-tile__title">{job.filename}</span>
              <span className="job-tile__meta">
                {job.pages.length} pages · {job.status}
              </span>
            </button>
          ))}
        </div>
      )}
    </SectionCard>
  );
}
