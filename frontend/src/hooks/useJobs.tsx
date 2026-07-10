import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJob, fetchJobs } from "../lib/api";
import type { ProcessingJob } from "../types";

function needsPolling(job: ProcessingJob | null): boolean {
  return (
    job?.status === "queued" ||
    job?.status === "processing" ||
    job?.export.status === "processing"
  );
}

interface JobsContextValue {
  jobs: ProcessingJob[];
  activeJob: ProcessingJob | null;
  isLoadingJobs: boolean;
  loadError: string | null;
  readyCount: number;
  handleJobCreated: (job: ProcessingJob) => void;
  handleJobUpdated: (job: ProcessingJob) => void;
  handleSelectJob: (jobId: string) => void;
  refreshJobs: () => Promise<ProcessingJob[]>;
}

const JobsContext = createContext<JobsContextValue | null>(null);

export function JobsProvider({ children }: { children: ReactNode }) {
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

  const value: JobsContextValue = {
    jobs,
    activeJob,
    isLoadingJobs,
    loadError,
    readyCount,
    handleJobCreated,
    handleJobUpdated,
    handleSelectJob,
    refreshJobs,
  };

  return <JobsContext.Provider value={value}>{children}</JobsContext.Provider>;
}

export function useJobs(): JobsContextValue {
  const context = useContext(JobsContext);
  if (!context) {
    throw new Error("useJobs must be used within JobsProvider");
  }
  return context;
}
