import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, FileCode2, FileText, Loader2 } from "lucide-react";
import { AppHeader } from "../../components/AppHeader";
import { WorkflowStepper } from "../../components/WorkflowStepper";
import { useToast } from "../../components/Toast";
import { PageReviewBoard } from "../pages/PageReviewBoard";
import { useJobs } from "../../hooks/useJobs";
import { resolveArtifactUrl, startExport, startTextExport } from "../../lib/api";
import type { ProcessingJob } from "../../types";

function needsPolling(job: ProcessingJob | null): boolean {
  return (
    job?.status === "queued" ||
    job?.status === "processing" ||
    job?.export.status === "processing" ||
    job?.textExport?.status === "processing"
  );
}

export function ReviewPage() {
  const { toast } = useToast();
  const { activeJob, loadError, handleJobUpdated } = useJobs();
  const [isExporting, setIsExporting] = useState(false);
  const [isTextExporting, setIsTextExporting] = useState(false);

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
          ? "Image PDF is ready to download."
          : "Image PDF export started.",
        "success",
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start export.";
      toast(message, "error");
    } finally {
      setIsExporting(false);
    }
  }

  async function handleTextExport() {
    if (!activeJob) {
      return;
    }

    setIsTextExporting(true);
    try {
      const textExport = await startTextExport(activeJob.id);
      handleJobUpdated({ ...activeJob, textExport });
      toast(
        textExport.status === "ready"
          ? "Text PDF is ready to download."
          : "Text PDF export started.",
        "success",
      );
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to start text export.";
      toast(message, "error");
    } finally {
      setIsTextExporting(false);
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

  const textExport = activeJob.textExport ?? {
    status: "idle" as const,
    progressPercent: 0,
    filename: null,
    downloadUrl: null,
    texUrl: null,
    requestedAt: null,
    completedAt: null,
    error: null,
  };
  const exportDownloadUrl = resolveArtifactUrl(activeJob.export.downloadUrl);
  const textExportDownloadUrl = resolveArtifactUrl(textExport.downloadUrl);
  const texSourceUrl = resolveArtifactUrl(textExport.texUrl ?? null);
  const canExport =
    activeJob.status === "ready" &&
    activeJob.export.status !== "processing" &&
    !isExporting;
  const canTextExport =
    activeJob.status === "ready" &&
    textExport.status !== "processing" &&
    !isTextExporting;

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
                <Download size={15} aria-hidden="true" />
                Image PDF
              </a>
            ) : null}
            {textExportDownloadUrl ? (
              <a
                className="secondary-button"
                href={textExportDownloadUrl}
                target="_blank"
                rel="noreferrer"
              >
                <FileText size={15} aria-hidden="true" />
                Text PDF
              </a>
            ) : null}
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
            <button
              className="secondary-button"
              disabled={!canTextExport}
              onClick={() => void handleTextExport()}
              type="button"
            >
              {isTextExporting || textExport.status === "processing" ? (
                <>
                  <Loader2 size={15} className="spin" aria-hidden="true" />
                  Exporting…
                </>
              ) : (
                "Export text PDF"
              )}
            </button>
            <button
              className="primary-button"
              disabled={!canExport}
              onClick={() => void handleExport()}
              type="button"
            >
              {isExporting || activeJob.export.status === "processing" ? (
                <>
                  <Loader2 size={15} className="spin" aria-hidden="true" />
                  Exporting…
                </>
              ) : (
                "Export image PDF"
              )}
            </button>
          </div>
        }
      />

      {loadError ? (
        <div className="status-banner status-banner--error">
          <strong>Backend unavailable</strong>
          <span>{loadError}</span>
        </div>
      ) : null}

      {textExport.status === "failed" && textExport.error ? (
        <div className="status-banner status-banner--error">
          <strong>Text PDF export failed</strong>
          <span>{textExport.error}</span>
        </div>
      ) : null}

      <WorkflowStepper job={activeJob} />

      <PageReviewBoard job={activeJob} onJobUpdated={handleJobUpdated} />
    </main>
  );
}
