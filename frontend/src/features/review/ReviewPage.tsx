import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, FileCode2, FileSearch, FileText, Loader2, XCircle } from "lucide-react";
import { AppHeader } from "../../components/AppHeader";
import { WorkflowStepper } from "../../components/WorkflowStepper";
import { useToast } from "../../components/Toast";
import { PageReviewBoard } from "../pages/PageReviewBoard";
import { useJobs } from "../../hooks/useJobs";
import {
  cancelJob,
  resolveArtifactUrl,
  startExport,
  startSearchableExport,
  startTextExport,
} from "../../lib/api";
import type { ExportState, ProcessingJob } from "../../types";

const IDLE_EXPORT: ExportState = {
  status: "idle",
  progressPercent: 0,
  filename: null,
  downloadUrl: null,
  texUrl: null,
  requestedAt: null,
  completedAt: null,
  error: null,
};

function needsPolling(job: ProcessingJob | null): boolean {
  return (
    job?.status === "queued" ||
    job?.status === "processing" ||
    job?.export.status === "processing" ||
    job?.textExport?.status === "processing" ||
    job?.searchableExport?.status === "processing"
  );
}

export function ReviewPage() {
  const { toast } = useToast();
  const { activeJob, loadError, handleJobUpdated } = useJobs();
  const [pendingExport, setPendingExport] = useState<"image" | "text" | "searchable" | null>(
    null,
  );
  const [cancelling, setCancelling] = useState(false);

  async function runCancel() {
    if (!activeJob) {
      return;
    }

    setCancelling(true);
    try {
      const job = await cancelJob(activeJob.id);
      handleJobUpdated(job);
      toast("Cancellation requested.", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to cancel processing.";
      toast(message, "error");
    } finally {
      setCancelling(false);
    }
  }

  async function runExport(kind: "image" | "text" | "searchable") {
    if (!activeJob) {
      return;
    }

    setPendingExport(kind);
    try {
      if (kind === "image") {
        const exportState = await startExport(activeJob.id);
        handleJobUpdated({ ...activeJob, export: exportState });
      } else if (kind === "text") {
        const textExport = await startTextExport(activeJob.id);
        handleJobUpdated({ ...activeJob, textExport });
      } else {
        const searchableExport = await startSearchableExport(activeJob.id);
        handleJobUpdated({ ...activeJob, searchableExport });
      }
      toast("Export started.", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start export.";
      toast(message, "error");
    } finally {
      setPendingExport(null);
    }
  }

  if (!activeJob) {
    return (
      <main className="page-content">
        <div className="empty-state empty-state--large">
          <strong>No session selected</strong>
          <p>Choose a session from the dashboard or upload a new video to begin.</p>
          <Link className="primary-button" to="/app">
            Back to sessions
          </Link>
        </div>
      </main>
    );
  }

  const textExport = activeJob.textExport ?? IDLE_EXPORT;
  const searchableExport = activeJob.searchableExport ?? IDLE_EXPORT;
  const isReady = activeJob.status === "ready";

  const exports: {
    kind: "searchable" | "image" | "text";
    label: string;
    Icon: typeof Download;
    state: ExportState;
    primary?: boolean;
  }[] = [
    {
      kind: "searchable",
      label: "Searchable PDF",
      Icon: FileSearch,
      state: searchableExport,
      primary: true,
    },
    { kind: "image", label: "Image PDF", Icon: Download, state: activeJob.export },
    { kind: "text", label: "Text PDF", Icon: FileText, state: textExport },
  ];
  const texSourceUrl = resolveArtifactUrl(textExport.texUrl ?? null);
  const isCancellable = activeJob.status === "queued" || activeJob.status === "processing";
  const failedExports = exports.filter(
    (item) => item.state.status === "failed" && item.state.error,
  );

  return (
    <main className="page-content">
      <AppHeader
        title={activeJob.filename}
        subtitle={activeJob.progress.message}
        job={activeJob}
        isLive={needsPolling(activeJob)}
        actions={
          <div className="review-header-actions">
            {isCancellable ? (
              <button
                className="secondary-button danger-button"
                disabled={cancelling}
                onClick={() => void runCancel()}
                type="button"
              >
                {cancelling ? (
                  <Loader2 size={15} className="spin" aria-hidden="true" />
                ) : (
                  <XCircle size={15} aria-hidden="true" />
                )}
                Cancel processing
              </button>
            ) : null}
            {exports.map(({ kind, label, Icon, state, primary }) => {
              const downloadUrl = resolveArtifactUrl(state.downloadUrl);
              if (state.status === "ready" && downloadUrl) {
                return (
                  <a
                    className={primary ? "primary-button" : "secondary-button"}
                    href={downloadUrl}
                    key={kind}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Icon size={15} aria-hidden="true" />
                    {label}
                  </a>
                );
              }
              const busy = pendingExport === kind || state.status === "processing";
              return (
                <button
                  className={primary ? "primary-button" : "secondary-button"}
                  disabled={!isReady || busy}
                  key={kind}
                  onClick={() => void runExport(kind)}
                  type="button"
                >
                  {busy ? (
                    <>
                      <Loader2 size={15} className="spin" aria-hidden="true" />
                      Exporting…
                    </>
                  ) : (
                    <>
                      <Icon size={15} aria-hidden="true" />
                      Export {label.toLowerCase()}
                    </>
                  )}
                </button>
              );
            })}
            {texSourceUrl ? (
              <a
                className="secondary-button"
                href={texSourceUrl}
                target="_blank"
                rel="noreferrer"
                title="Download the LaTeX source of the text PDF"
              >
                <FileCode2 size={15} aria-hidden="true" />
                .tex
              </a>
            ) : null}
          </div>
        }
      />

      {loadError ? (
        <div className="status-banner status-banner--error">
          <strong>Backend unavailable</strong>
          <span>{loadError}</span>
        </div>
      ) : null}

      {failedExports.map((item) => (
        <div className="status-banner status-banner--error" key={item.kind}>
          <strong>{item.label} export failed</strong>
          <span>{item.state.error}</span>
        </div>
      ))}

      <WorkflowStepper job={activeJob} />

      <PageReviewBoard job={activeJob} onJobUpdated={handleJobUpdated} />
    </main>
  );
}
