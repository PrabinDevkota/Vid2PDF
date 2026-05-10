import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BrowserRouter,
  NavLink,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import { JobOverview } from "./features/jobs/JobOverview";
import { UploadPanel } from "./features/jobs/UploadPanel";
import { PageReviewBoard } from "./features/pages/PageReviewBoard";
import { fetchJob, fetchJobs } from "./lib/api";
import type { ProcessingJob } from "./types";

function formatShortDate(value: string | null): string {
  if (!value) {
    return "Not yet";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function needsPolling(job: ProcessingJob | null): boolean {
  return (
    job?.status === "queued" ||
    job?.status === "processing" ||
    job?.export.status === "processing"
  );
}

function Workspace() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [activeJob, setActiveJob] = useState<ProcessingJob | null>(null);
  const [isLoadingJobs, setIsLoadingJobs] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const readyCount = useMemo(
    () => jobs.filter((job) => job.status === "ready").length,
    [jobs],
  );
  const activePageCount = activeJob?.pages.filter((page) => !page.deleted).length ?? 0;

  const refreshJobs = useCallback(async () => {
    setLoadError(null);
    const nextJobs = await fetchJobs();
    setJobs(nextJobs);

    if (!jobId) {
      setActiveJob((current) => {
        if (current) {
          return nextJobs.find((job) => job.id === current.id) ?? current;
        }
        return nextJobs[0] ?? null;
      });
    }

    return nextJobs;
  }, [jobId]);

  const loadActiveJob = useCallback(async () => {
    if (!jobId) {
      await refreshJobs();
      return;
    }

    setLoadError(null);
    const [nextJobs, selectedJob] = await Promise.all([fetchJobs(), fetchJob(jobId)]);
    setJobs(nextJobs);
    setActiveJob(selectedJob);
  }, [jobId, refreshJobs]);

  useEffect(() => {
    setIsLoadingJobs(true);
    loadActiveJob()
      .catch((error) => {
        setLoadError(error instanceof Error ? error.message : "Failed to load sessions.");
      })
      .finally(() => setIsLoadingJobs(false));
  }, [loadActiveJob]);

  useEffect(() => {
    if (!needsPolling(activeJob)) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadActiveJob().catch((error) => {
        setLoadError(error instanceof Error ? error.message : "Failed to refresh session.");
      });
    }, 2500);

    return () => window.clearInterval(timer);
  }, [activeJob, loadActiveJob]);

  function handleJobCreated(job: ProcessingJob) {
    setJobs((currentJobs) => [job, ...currentJobs.filter((item) => item.id !== job.id)]);
    setActiveJob(job);
    navigate(`/review/${job.id}`);
  }

  function handleJobUpdated(job: ProcessingJob) {
    setActiveJob(job);
    setJobs((currentJobs) =>
      currentJobs.map((item) => (item.id === job.id ? job : item)),
    );
  }

  function handleSelectJob(nextJobId: string) {
    navigate(`/review/${nextJobId}`);
  }

  return (
    <main className="workspace">
      <header className="workspace-topbar">
        <div>
          <p className="workspace-kicker">Video to PDF studio</p>
          <h1>Reconstruct clean PDFs from recorded page flows</h1>
          <p>
            Upload a source video, let the backend extract stable pages, then review,
            recover, reorder, and export the final document.
          </p>
        </div>
        <div className="topbar-stats" aria-label="Workspace stats">
          <div className="stat-pill">
            <span>Sessions</span>
            <strong>{jobs.length}</strong>
          </div>
          <div className="stat-pill">
            <span>Ready</span>
            <strong>{readyCount}</strong>
          </div>
          <div className="stat-pill">
            <span>Active pages</span>
            <strong>{activePageCount}</strong>
          </div>
        </div>
      </header>

      {loadError ? (
        <div className="status-banner status-banner--error workspace-alert">
          <strong>Backend unavailable</strong>
          <span>{loadError}</span>
        </div>
      ) : null}

      <div className="dashboard-grid">
        <div className="dashboard-grid__upload">
          <UploadPanel onJobCreated={handleJobCreated} />
        </div>
        <div className="dashboard-grid__sessions">
          <JobOverview
            activeJob={activeJob}
            isLoading={isLoadingJobs}
            jobs={jobs}
            onSelectJob={handleSelectJob}
          />
        </div>
        <div className="dashboard-grid__review">
          <PageReviewBoard job={activeJob} onJobUpdated={handleJobUpdated} />
        </div>
      </div>

      <p className="workspace-footnote">
        Latest session update: {formatShortDate(activeJob?.updatedAt ?? null)}
      </p>
    </main>
  );
}

function AppShell() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">VP</div>
          <div>
            <strong>Vid2PDF</strong>
            <span>Document reconstruction</span>
          </div>
        </div>
        <nav className="sidebar-nav" aria-label="Primary navigation">
          <NavLink className="nav-item" to="/" end>
            <span className="nav-item__icon" aria-hidden="true" />
            Studio
          </NavLink>
          <NavLink className="nav-item" to="/review" end>
            <span className="nav-item__icon" aria-hidden="true" />
            Review
          </NavLink>
        </nav>
        <div className="sidebar-status">
          <span className="live-dot" aria-hidden="true" />
          <div>
            <strong>Backend-backed edits</strong>
            <p>Rotation, deletion, restore, manual capture, reorder, and export persist through API state.</p>
          </div>
        </div>
      </aside>
      <Routes>
        <Route path="/" element={<Workspace />} />
        <Route path="/review" element={<Workspace />} />
        <Route path="/review/:jobId" element={<Workspace />} />
      </Routes>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}
