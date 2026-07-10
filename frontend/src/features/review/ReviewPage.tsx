import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, Loader2 } from "lucide-react";
import { AppHeader } from "../../components/AppHeader";
import { WorkflowStepper } from "../../components/WorkflowStepper";
import { useToast } from "../../components/Toast";
import { PageReviewBoard } from "../pages/PageReviewBoard";
import { useJobs } from "../../hooks/useJobs";
import { resolveArtifactUrl, startExport } from "../../lib/api";

function needsPolling(job: { status: string; export: { status: string } } | null): boolean {
  return (
    job?.status === "queued" ||
    job?.status === "processing" ||
    job?.export.status === "processing"
  );
}

export function ReviewPage() {
  const { toast } = useToast();
  const { activeJob, loadError, handleJobUpdated } = useJobs();
  const [isExporting, setIsExporting] = useState(false);

  async function handleExport() {
    if (!activeJob) {
      return;
    }

    setIsExporting(true);
    try {
      const exportState = await startExport(activeJob.id);
      handleJobUpdated({ ...activeJob, export: exportState });
      toast(
        exportState.status === "ready"
          ? "PDF export is ready to download."
          : "Export started — preparing your PDF.",
        "success",
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start export.";
      toast(message, "error");
    } finally {
      setIsExporting(false);
    }
  }

  if (!activeJob) {
    return (
      <main className="page-content">
        <div className="empty-state empty-state--large">
          <strong>No session selected</strong>
          <p>Choose a session from the dashboard or upload a new video to begin.</p>
          <Link className="primary-button" to="/">
            Back to dashboard
          </Link>
        </div>
      </main>
    );
  }

  const exportDownloadUrl = resolveArtifactUrl(activeJob.export.downloadUrl);
  const canExport =
    activeJob.status === "ready" &&
    activeJob.export.status !== "processing" &&
    !isExporting;

  return (
    <main className="page-content">
      <AppHeader
        title={activeJob.filename}
        subtitle={activeJob.progress.message}
        job={activeJob}
        isLive={needsPolling(activeJob)}
        actions={
          <div className="review-header-actions">
            {exportDownloadUrl ? (
              <a
                className="secondary-button"
                href={exportDownloadUrl}
                target="_blank"
                rel="noreferrer"
              >
                <Download size={16} aria-hidden="true" />
                Download PDF
              </a>
            ) : null}
            <button
              className="primary-button"
              disabled={!canExport}
              onClick={() => void handleExport()}
              type="button"
            >
              {isExporting || activeJob.export.status === "processing" ? (
                <>
                  <Loader2 size={16} className="spin" aria-hidden="true" />
                  Exporting…
                </>
              ) : (
                "Export PDF"
              )}
            </button>
          </div>
        }
      />

      {loadError ? (
        <div className="status-banner status-banner--error workspace-alert">
          <strong>Backend unavailable</strong>
          <span>{loadError}</span>
        </div>
      ) : null}

      <WorkflowStepper job={activeJob} />

      <PageReviewBoard job={activeJob} onJobUpdated={handleJobUpdated} />
    </main>
  );
}
