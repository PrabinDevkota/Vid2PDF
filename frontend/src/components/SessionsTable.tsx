import { useMemo, useState } from "react";
import { FileVideo, Search, Trash2 } from "lucide-react";
import { useToast } from "./Toast";
import type { ProcessingJob } from "../types";

interface SessionsTableProps {
  jobs: ProcessingJob[];
  activeJobId?: string | null;
  isLoading: boolean;
  onSelectJob: (jobId: string) => void;
  onDeleteJob?: (jobId: string) => Promise<void>;
  limit?: number;
  showViewAll?: boolean;
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
  onDeleteJob,
  limit,
  showViewAll,
}: SessionsTableProps) {
  const { toast } = useToast();
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

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

  async function handleDelete(jobId: string) {
    if (!onDeleteJob) {
      return;
    }
    if (confirmingId !== jobId) {
      setConfirmingId(jobId);
      return;
    }
    setConfirmingId(null);
    setDeletingId(jobId);
    try {
      await onDeleteJob(jobId);
      toast("Session deleted.", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete session.";
      toast(message, "error");
    } finally {
      setDeletingId(null);
    }
  }

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
        <FileVideo size={28} aria-hidden="true" />
        <strong>No sessions yet</strong>
        <p>Upload your first document video to get started.</p>
      </div>
    );
  }

  return (
    <div className="sessions-table-wrap">
      <div className="sessions-table-toolbar">
        <div className="search-input">
          <Search size={15} aria-hidden="true" />
          <input
            aria-label="Search sessions"
            placeholder="Search sessions"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        {showViewAll && limit && jobs.length > limit ? (
          <button
            className="link-button"
            onClick={() => setShowAll((current) => !current)}
            type="button"
          >
            {showAll ? "Show fewer" : `View all ${jobs.length}`}
          </button>
        ) : null}
      </div>

      {filteredJobs.length === 0 ? (
        <div className="sessions-table__empty">
          <p>No sessions match &ldquo;{search}&rdquo;</p>
        </div>
      ) : (
        <ul className="sessions-list">
          {filteredJobs.map((job) => {
            const activePageCount = job.pages.filter((page) => !page.deleted).length;
            const isConfirming = confirmingId === job.id;
            return (
              <li
                key={job.id}
                className={`session-row ${activeJobId === job.id ? "session-row--active" : ""}`}
              >
                <button
                  className="session-row__main"
                  onClick={() => onSelectJob(job.id)}
                  type="button"
                >
                  <span className="session-row__name" title={job.filename}>
                    {job.filename}
                  </span>
                  <span className="session-row__meta">
                    {job.processingMode === "camera" ? "Camera" : "Screen"}
                    {" · "}
                    {activePageCount} page{activePageCount === 1 ? "" : "s"}
                    {" · "}
                    {formatDate(job.updatedAt)}
                  </span>
                </button>
                <span className={`status-pill status-pill--${job.status}`}>{job.status}</span>
                {onDeleteJob ? (
                  <button
                    className={`session-row__delete ${isConfirming ? "session-row__delete--confirm" : ""}`}
                    disabled={deletingId === job.id}
                    onClick={() => void handleDelete(job.id)}
                    onBlur={() => setConfirmingId(null)}
                    title={isConfirming ? "Click again to delete permanently" : "Delete session"}
                    type="button"
                  >
                    {isConfirming ? "Confirm" : <Trash2 size={15} aria-hidden="true" />}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
