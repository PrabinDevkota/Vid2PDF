import { useEffect, useMemo, useState } from "react";
import { SectionCard } from "./components/SectionCard";
import { UploadPanel } from "./features/jobs/UploadPanel";
import { JobOverview } from "./features/jobs/JobOverview";
import { PageReviewBoard } from "./features/pages/PageReviewBoard";
import { fetchJob, fetchJobs } from "./lib/api";
import type { ProcessingJob, StageStatus } from "./types";

const navItems = ["Dashboard", "Sessions", "Review", "Exports", "Settings"];

const pipelineSteps = [
  { key: "upload", label: "Upload" },
  { key: "stable_segments", label: "Detect stable segments" },
  { key: "best_frames", label: "Select best frames" },
  { key: "dedupe", label: "Remove duplicates" },
  { key: "review", label: "Review pages" },
  { key: "export", label: "Export PDF" },
];

function formatCount(value: number, label: string) {
  return `${value} ${label}${value === 1 ? "" : "s"}`;
}

function mapStepStatus(job: ProcessingJob | null, stepKey: string): StageStatus {
  if (!job) {
    return "pending";
  }

  if (stepKey === "upload") {
    return job.status === "failed" ? "failed" : "complete";
  }

  if (stepKey === "review") {
    if (job.status === "failed") {
      return "failed";
    }
    if (job.status === "ready") {
      return "processing";
    }
    return "pending";
  }

  if (stepKey === "export") {
    if (job.export.status === "failed") {
      return "failed";
    }
    if (job.export.status === "ready") {
      return "complete";
    }
    if (job.export.status === "processing") {
      return "processing";
    }
    return job.status === "ready" ? "pending" : "pending";
  }

  const matchingStage = job.stages.find((stage) => {
    const key = stage.key.toLowerCase();
    return (
      key.includes(stepKey) ||
      (stepKey === "stable_segments" && (key.includes("segment") || key.includes("detect"))) ||
      (stepKey === "best_frames" && (key.includes("frame") || key.includes("select"))) ||
      (stepKey === "dedupe" && (key.includes("dedupe") || key.includes("duplicate")))
    );
  });

  if (matchingStage) {
    return matchingStage.status;
  }

  if (job.status === "ready") {
    return "complete";
  }

  return job.currentStageKey ? "pending" : "pending";
}

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <div className="brand-mark">V2</div>
        <div>
          <strong>Vid2PDF</strong>
          <span>Reconstruction studio</span>
        </div>
      </div>
      <nav className="sidebar-nav" aria-label="Workspace navigation">
        {navItems.map((item, index) => (
          <button className={`nav-item ${index === 0 ? "active" : ""}`} key={item} type="button">
            <span className="nav-item__icon" aria-hidden="true" />
            {item}
          </button>
        ))}
      </nav>
      <div className="sidebar-status">
        <span className="live-dot" />
        <div>
          <strong>Processing engine active</strong>
          <p>Local MVP workspace</p>
        </div>
      </div>
    </aside>
  );
}

function StatPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Topbar({
  exportsReady,
  jobsCount,
  readyJobs,
  totalPages,
}: {
  exportsReady: number;
  jobsCount: number;
  readyJobs: number;
  totalPages: number;
}) {
  return (
    <header className="workspace-topbar">
      <div>
        <p className="workspace-kicker">Vid2PDF workspace</p>
        <h1>Document reconstruction</h1>
        <p>Convert page-viewing videos into clean, reviewable PDFs.</p>
      </div>
      <div className="topbar-stats">
        <StatPill label="Sessions" value={jobsCount} />
        <StatPill label="Pages" value={totalPages} />
        <StatPill label="Ready" value={readyJobs} />
        <StatPill label="Exports" value={exportsReady} />
      </div>
    </header>
  );
}

function PipelineStepper({ job }: { job: ProcessingJob | null }) {
  return (
    <SectionCard
      eyebrow="Pipeline"
      title="Reconstruction pipeline"
      subtitle="Stable segments, best-frame selection, deduplication, review, export."
    >
      <div className="pipeline-stepper">
        {pipelineSteps.map((step, index) => {
          const status = mapStepStatus(job, step.key);
          return (
            <div className={`pipeline-step pipeline-step--${status}`} key={step.key}>
              <div className="pipeline-step__marker">{index + 1}</div>
              <div>
                <strong>{step.label}</strong>
                <span>{status}</span>
              </div>
            </div>
          );
        })}
      </div>
    </SectionCard>
  );
}

function ProcessingStatusCard({
  activeJob,
  loadError,
}: {
  activeJob: ProcessingJob | null;
  loadError: string | null;
}) {
  return (
    <SectionCard
      eyebrow="Status"
      title="Processing status"
      subtitle="Live state from the active backend job."
    >
      {loadError ? (
        <div className="status-banner status-banner--error">
          <strong>Workspace sync needs attention.</strong>
          <span>{loadError}</span>
        </div>
      ) : !activeJob ? (
        <div className="empty-state empty-state--compact">
          <span className="empty-state__icon" aria-hidden="true" />
          <strong>No active session</strong>
          <p>Upload a page-viewing video or select a session to inspect progress.</p>
        </div>
      ) : (
        <div className="processing-card">
          <div className="processing-card__header">
            <div>
              <span className={`status-pill status-pill--${activeJob.status}`}>
                {activeJob.status}
              </span>
              <h3>{activeJob.filename}</h3>
            </div>
            <strong>{activeJob.progress.percent}%</strong>
          </div>
          <div className="progress-block">
            <div className="progress-block__track">
              <div
                className="progress-block__fill"
                style={{ width: `${activeJob.progress.percent}%` }}
              />
            </div>
            <span>{activeJob.progress.message}</span>
          </div>
          <div className="processing-meta-grid">
            <div>
              <span>Mode</span>
              <strong>
                {activeJob.processingMode === "camera" ? "Camera pages" : "Screen recording"}
              </strong>
            </div>
            <div>
              <span>Pages</span>
              <strong>{activeJob.pages.filter((page) => !page.deleted).length}</strong>
            </div>
            <div>
              <span>Export</span>
              <strong>{activeJob.export.status}</strong>
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

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
  const exportsReady = jobs.filter((job) => job.export.status === "ready").length;

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
      <Sidebar />
      <main className="workspace">
        <Topbar
          exportsReady={exportsReady}
          jobsCount={jobs.length}
          readyJobs={readyJobs}
          totalPages={totalPages}
        />
        <section className="dashboard-grid" aria-label="Document reconstruction dashboard">
          <div className="dashboard-grid__upload">
            <UploadPanel onJobCreated={upsertJob} />
          </div>
          <div className="dashboard-grid__pipeline">
            <PipelineStepper job={activeJob} />
          </div>
          <div className="dashboard-grid__sessions">
            <JobOverview
              activeJob={activeJob}
              isLoading={isBootstrapping}
              jobs={jobs}
              onSelectJob={setActiveJobId}
            />
          </div>
          <div className="dashboard-grid__status">
            <ProcessingStatusCard activeJob={activeJob} loadError={loadError} />
          </div>
          <div className="dashboard-grid__review">
            <PageReviewBoard job={activeJob} onJobUpdated={upsertJob} />
          </div>
        </section>
        <p className="workspace-footnote">
          {formatCount(jobs.length, "session")} tracked locally. Backend polling remains active while jobs process or export.
        </p>
      </main>
    </div>
  );
}
