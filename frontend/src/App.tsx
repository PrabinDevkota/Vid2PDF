import { useEffect, useMemo, useState } from "react";
import { UploadPanel } from "./features/jobs/UploadPanel";
import { JobOverview } from "./features/jobs/JobOverview";
import { PageReviewBoard } from "./features/pages/PageReviewBoard";
import { SectionCard } from "./components/SectionCard";
import { fetchJobs } from "./lib/api";
import type { ProcessingJob } from "./types";

const pipelineSteps = [
  "Detect page changes",
  "Find stable viewing segments",
  "Select the clearest frame per page",
  "Remove duplicates and weak pages",
  "Prepare previews for review",
  "Export a final PDF",
];

export default function App() {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    fetchJobs()
      .then((initialJobs) => {
        setJobs(initialJobs);
        setActiveJobId(initialJobs[0]?.id ?? null);
      })
      .catch((error) => {
        setLoadError(error instanceof Error ? error.message : "Failed to load.");
      });
  }, []);

  const activeJob = useMemo(
    () => jobs.find((job) => job.id === activeJobId) ?? null,
    [activeJobId, jobs],
  );

  function handleJobCreated(job: ProcessingJob) {
    setJobs((currentJobs) => [job, ...currentJobs]);
    setActiveJobId(job.id);
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div className="hero__content">
          <p className="hero__eyebrow">Vid2PDF</p>
          <h1>Turn document screen recordings into clean, reviewable PDFs.</h1>
          <p className="hero__copy">
            Built for screen recordings of reports, ebooks, manuals, and slide
            decks viewed page by page. Vid2PDF is structured around
            reconstruction, not bulk screenshot extraction.
          </p>
        </div>
        <div className="hero__panel">
          <span className="panel-label">Pipeline</span>
          <ol>
            {pipelineSteps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      </header>

      <main className="main-grid">
        <div className="main-grid__left">
          <UploadPanel onJobCreated={handleJobCreated} />
          <JobOverview
            activeJob={activeJob}
            jobs={jobs}
            onSelectJob={setActiveJobId}
          />
        </div>
        <div className="main-grid__right">
          <SectionCard eyebrow="Product" title="What makes this different">
            <ul className="feature-list">
              <li>Focuses on stable page segments instead of arbitrary frame grabs.</li>
              <li>Creates one best representative frame for each viewed page.</li>
              <li>Prepares the workflow for review, cleanup, and final export.</li>
            </ul>
            {loadError ? <p className="error-text">{loadError}</p> : null}
          </SectionCard>
          <PageReviewBoard job={activeJob} />
        </div>
      </main>
    </div>
  );
}
