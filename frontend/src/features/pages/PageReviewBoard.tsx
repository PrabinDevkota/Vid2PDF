import { useState } from "react";
import type { ProcessingJob } from "../../types";
import { SectionCard } from "../../components/SectionCard";
import { reorderPages, resolveArtifactUrl, startExport, updatePage } from "../../lib/api";

interface PageReviewBoardProps {
  job: ProcessingJob | null;
  onJobUpdated: (job: ProcessingJob) => void;
}

export function PageReviewBoard({ job, onJobUpdated }: PageReviewBoardProps) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [isMutating, setIsMutating] = useState(false);
  const visiblePages = job?.pages.filter((page) => !page.deleted) ?? [];

  async function handleRotate(pageId: string, rotation: number) {
    if (!job) {
      return;
    }

    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await updatePage(job.id, pageId, { rotation });
      onJobUpdated(updatedJob);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to rotate page.");
    } finally {
      setIsMutating(false);
    }
  }

  async function handleDelete(pageId: string, deleted: boolean) {
    if (!job) {
      return;
    }

    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await updatePage(job.id, pageId, { deleted });
      onJobUpdated(updatedJob);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to update page.");
    } finally {
      setIsMutating(false);
    }
  }

  async function handleShift(pageId: string, direction: -1 | 1) {
    if (!job) {
      return;
    }

    const currentIndex = visiblePages.findIndex((page) => page.id === pageId);
    const nextIndex = currentIndex + direction;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= visiblePages.length) {
      return;
    }

    const reordered = [...visiblePages];
    const [moved] = reordered.splice(currentIndex, 1);
    reordered.splice(nextIndex, 0, moved);

    const deletedPages = job.pages.filter((page) => page.deleted).map((page) => page.id);
    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await reorderPages(job.id, [
        ...reordered.map((page) => page.id),
        ...deletedPages,
      ]);
      onJobUpdated(updatedJob);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to reorder pages.");
    } finally {
      setIsMutating(false);
    }
  }

  async function handleExport() {
    if (!job) {
      return;
    }

    setIsMutating(true);
    setActionError(null);
    try {
      const exportState = await startExport(job.id);
      onJobUpdated({ ...job, export: exportState });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to start export.");
    } finally {
      setIsMutating(false);
    }
  }

  return (
    <SectionCard
      eyebrow="Review"
      title="Page review board"
      subtitle="Inspect extracted pages, adjust order, rotate misaligned captures, and prepare the final export."
      actions={
        job ? (
          <div className="review-actions">
            <button className="secondary-button" type="button">
              {visiblePages.length} reviewable pages
            </button>
            <button
              className="primary-button"
              disabled={job.status !== "ready" || job.export.status === "processing" || isMutating}
              onClick={() => void handleExport()}
              type="button"
            >
              {job.export.status === "processing" ? "Exporting..." : "Export PDF"}
            </button>
          </div>
        ) : null
      }
    >
      {!job ? (
        <div className="empty-state empty-state--large">
          <strong>No review session selected</strong>
          <p>Choose a processing session to inspect extracted pages and prepare the final document.</p>
        </div>
      ) : (
        <div className="review-board">
          <div className="review-board__summary">
            <div className="review-summary-card">
              <span className="review-summary-card__eyebrow">Current session</span>
              <h3>{job.filename}</h3>
              <p className="muted">{job.progress.message}</p>
              <div className="progress-block">
                <div className="progress-block__track">
                  <div
                    className="progress-block__fill"
                    style={{ width: `${job.progress.percent}%` }}
                  />
                </div>
                <span>{job.progress.percent}% complete</span>
              </div>
            </div>
            <div className="review-metrics">
              <div className="review-metric">
                <strong>{visiblePages.length}</strong>
                <span>Pages in review</span>
              </div>
              <div className="review-metric">
                <strong>{job.stages.filter((stage) => stage.status === "complete").length}</strong>
                <span>Stages complete</span>
              </div>
            </div>
          </div>
          <div className="stage-strip">
            {job.stages.map((stage) => (
              <div className="stage-chip" key={stage.key}>
                <span className={`stage-chip__dot stage-chip__dot--${stage.status}`} />
                <div>
                  <strong>{stage.label}</strong>
                  <span>{stage.status}</span>
                </div>
              </div>
            ))}
          </div>
          {job.export.status !== "idle" ? (
            <div className={`status-banner ${job.export.status === "failed" ? "status-banner--error" : ""}`}>
              <strong>
                {job.export.status === "ready"
                  ? "Export ready"
                  : job.export.status === "processing"
                    ? "Export in progress"
                    : "Export unavailable"}
              </strong>
              <span>
                {job.export.status === "ready"
                  ? `${job.export.filename} is ready to download.`
                  : job.export.status === "processing"
                    ? `${job.export.progressPercent}% complete. Preparing the final PDF artifact.`
                    : job.export.error ?? "Export could not be completed."}
              </span>
              {job.export.downloadUrl ? (
                <a
                  className="download-link"
                  href={resolveArtifactUrl(job.export.downloadUrl)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Download exported PDF
                </a>
              ) : null}
            </div>
          ) : null}
          {actionError ? (
            <div className="status-banner status-banner--error">
              <strong>Review action failed</strong>
              <span>{actionError}</span>
            </div>
          ) : null}
          {job.status !== "ready" ? (
            <div className="empty-state empty-state--large">
              <strong>Processing in progress</strong>
              <p>
                Pages will appear here once stable segments are processed and the
                best frame for each page is selected.
              </p>
            </div>
          ) : visiblePages.length === 0 ? (
            <div className="empty-state empty-state--large">
              <strong>No active pages available</strong>
              <p>Restore or keep more pages during review before exporting the final PDF.</p>
            </div>
          ) : (
            <div className="page-grid">
              {visiblePages.map((page, index) => (
                <article className="page-card" key={page.id}>
                  <div className="page-card__preview">
                    <div className="page-card__preview-tag">Page preview</div>
                    {resolveArtifactUrl(page.thumbnailUrl) ? (
                      <img
                        alt={page.previewLabel}
                        className="page-preview-image"
                        src={resolveArtifactUrl(page.thumbnailUrl) ?? undefined}
                        style={{ transform: `rotate(${page.rotation}deg)` }}
                      />
                    ) : (
                      <div
                        className="page-placeholder"
                        style={{ transform: `rotate(${page.rotation}deg)` }}
                      >
                        <span>{page.previewLabel}</span>
                      </div>
                    )}
                  </div>
                  <div className="page-card__content">
                    <div className="page-card__header">
                      <h4>Page {index + 1}</h4>
                      <span className="page-score">
                        Score {page.sharpnessScore.toFixed(2)}
                      </span>
                    </div>
                    <div className="page-meta-row">
                      <span>
                        Segment {page.segmentStart.toFixed(1)}s to {page.segmentEnd.toFixed(1)}s
                      </span>
                      <span>Rotation {page.rotation}°</span>
                    </div>
                    <div className="page-meta-row">
                      <span>Frame #{page.sourceFrameIndex}</span>
                      <span>Timestamp {page.sourceTimestamp.toFixed(1)}s</span>
                    </div>
                  </div>
                  <div className="page-card__actions">
                    <button
                      disabled={isMutating || index === 0}
                      onClick={() => void handleShift(page.id, -1)}
                      type="button"
                    >
                      Move up
                    </button>
                    <button
                      disabled={isMutating || index === visiblePages.length - 1}
                      onClick={() => void handleShift(page.id, 1)}
                      type="button"
                    >
                      Move down
                    </button>
                    <button
                      disabled={isMutating}
                      onClick={() => void handleRotate(page.id, page.rotation + 90)}
                      type="button"
                    >
                      Rotate
                    </button>
                    <button
                      disabled={isMutating}
                      onClick={() => void handleDelete(page.id, true)}
                      type="button"
                    >
                      Delete
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      )}
    </SectionCard>
  );
}
