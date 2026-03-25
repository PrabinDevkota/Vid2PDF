import { useEffect, useMemo, useState } from "react";
import { UploadPanel } from "./features/jobs/UploadPanel";
import { JobOverview } from "./features/jobs/JobOverview";
import { PageReviewBoard } from "./features/pages/PageReviewBoard";
import { SectionCard } from "./components/SectionCard";
import { fetchJob, fetchJobs } from "./lib/api";
import type { ProcessingJob } from "./types";

const pipelineSteps = [
  {
    title: "Detect page turns",
    description: "Spot transitions between viewed pages instead of collecting arbitrary frames.",
  },
  {
    title: "Lock stable segments",
    description: "Keep only the moments where a page is fully visible and steady on screen.",
  },
  {
    title: "Pick the best frame",
    description: "Select the cleanest candidate from each segment for a sharper final document.",
  },
  {
    title: "Review before export",
    description: "Inspect previews, remove weak pages, reorder, rotate, and export a clean PDF.",
  },
];

export default function App() {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);

  useEffect(() => {
    let isActive = true;

    async function loadInitialJobs() {
      try {
        const initialJobs = await fetchJobs();
        if (!isActive) {
          return;
        }
        setJobs(initialJobs);
        setActiveJobId((currentJobId) => currentJobId ?? initialJobs[0]?.id ?? null);
        setLoadError(null);
      } catch (error) {
        if (!isActive) {
          return;
        }
        setLoadError(error instanceof Error ? error.message : "Failed to load jobs.");
      } finally {
        if (isActive) {
          setIsBootstrapping(false);
        }
      }
    }

    void loadInitialJobs();
    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(async () => {
      try {
        const latestJobs = await fetchJobs();
        setJobs(latestJobs);
        setLoadError(null);
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "Failed to sync jobs.");
      }
    }, 2500);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    if (!activeJobId) {
      return;
    }

    const hasLiveActivity = jobs.some(
      (job) =>
        job.id === activeJobId &&
        (job.status === "queued" ||
          job.status === "processing" ||
          job.export.status === "processing"),
    );
    if (!hasLiveActivity) {
      return;
    }

    const intervalId = window.setInterval(async () => {
      try {
        const freshJob = await fetchJob(activeJobId);
        setJobs((currentJobs) => {
          const nextJobs = currentJobs.map((job) =>
            job.id === freshJob.id ? freshJob : job,
          );
          return nextJobs.some((job) => job.id === freshJob.id)
            ? nextJobs
            : [freshJob, ...currentJobs];
        });
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "Failed to sync active job.");
      }
    }, 1200);

    return () => window.clearInterval(intervalId);
  }, [activeJobId, jobs]);

  const activeJob = useMemo(
    () => jobs.find((job) => job.id === activeJobId) ?? null,
    [activeJobId, jobs],
  );
  const totalPages = jobs.reduce(
    (sum, job) => sum + job.pages.filter((page) => !page.deleted).length,
    0,
  );
  const readyJobs = jobs.filter((job) => job.status === "ready").length;

  function upsertJob(updatedJob: ProcessingJob) {
    setJobs((currentJobs) => {
      const nextJobs = currentJobs.map((job) =>
        job.id === updatedJob.id ? updatedJob : job,
      );
      return nextJobs.some((job) => job.id === updatedJob.id)
        ? nextJobs
        : [updatedJob, ...currentJobs];
    });
    setActiveJobId(updatedJob.id);
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div className="hero__content">
          <div className="hero-badge-row">
            <p className="hero__eyebrow">Vid2PDF</p>
            <span className="hero-badge">Screen recordings to polished PDFs</span>
          </div>
          <h1>Reconstruct clean PDFs from page-by-page screen recordings.</h1>
          <p className="hero__copy">
            Built for reports, ebooks, manuals, and slide decks viewed page by
            page. Vid2PDF focuses on stable segments, best-frame selection, and
            reviewable page reconstruction rather than raw screenshot capture.
          </p>
          <div className="hero__stats">
            <div className="stat-card">
              <strong>{jobs.length}</strong>
              <span>Sessions tracked</span>
            </div>
            <div className="stat-card">
              <strong>{totalPages}</strong>
              <span>Pages prepared</span>
            </div>
            <div className="stat-card">
              <strong>{readyJobs}</strong>
              <span>Ready to export</span>
            </div>
          </div>
        </div>
        <div className="hero__panel">
          <div className="panel-topline">
            <span className="panel-label">Reconstruction flow</span>
            <span className="panel-tag">v1 workspace</span>
          </div>
          <div className="pipeline-list">
            {pipelineSteps.map((step, index) => (
              <article className="pipeline-item" key={step.title}>
                <span className="pipeline-item__index">0{index + 1}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </header>

      <main className="main-grid">
        <div className="main-grid__left">
          <UploadPanel onJobCreated={upsertJob} />
          <JobOverview
            activeJob={activeJob}
            isLoading={isBootstrapping}
            jobs={jobs}
            onSelectJob={setActiveJobId}
          />
        </div>
        <div className="main-grid__right">
          <SectionCard
            eyebrow="Product"
            title="A tighter workflow than basic video-to-PDF conversion"
            subtitle="The interface is organized around the actual reconstruction job: upload, inspect, refine, and export."
          >
            <div className="feature-grid">
              <article className="feature-card">
                <span className="feature-card__label">Page-aware</span>
                <p>Optimized for recordings where a document is viewed page by page.</p>
              </article>
              <article className="feature-card">
                <span className="feature-card__label">Quality-first</span>
                <p>Designed to choose the strongest frame from each stable page segment.</p>
              </article>
              <article className="feature-card">
                <span className="feature-card__label">Reviewable</span>
                <p>Pages can be checked before export instead of trusting a blind batch conversion.</p>
              </article>
            </div>
            {loadError ? (
              <div className="status-banner status-banner--error">
                <strong>Workspace sync needs attention.</strong>
                <span>{loadError}</span>
              </div>
            ) : (
              <div className="status-banner">
                <strong>Live workspace state is connected.</strong>
                <span>Jobs, page actions, and export status are now synchronized through the backend contracts.</span>
              </div>
            )}
          </SectionCard>
          <PageReviewBoard job={activeJob} onJobUpdated={upsertJob} />
        </div>
      </main>
    </div>
  );
}
