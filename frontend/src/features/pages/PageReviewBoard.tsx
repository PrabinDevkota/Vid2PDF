import { useEffect, useMemo, useRef, useState } from "react";
import type { ProcessingJob } from "../../types";
import { SectionCard } from "../../components/SectionCard";
import {
  addManualPage,
  bulkUpdatePages,
  reorderPages,
  resolveArtifactUrl,
  startExport,
  updatePage,
} from "../../lib/api";

interface PageReviewBoardProps {
  job: ProcessingJob | null;
  onJobUpdated: (job: ProcessingJob) => void;
}

export function PageReviewBoard({ job, onJobUpdated }: PageReviewBoardProps) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [isMutating, setIsMutating] = useState(false);
  const [draggedPageId, setDraggedPageId] = useState<string | null>(null);
  const [videoCurrentTime, setVideoCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [isVideoReady, setIsVideoReady] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const visiblePages = job?.pages.filter((page) => !page.deleted) ?? [];
  const deletedPages = job?.pages.filter((page) => page.deleted) ?? [];
  const manualPages = useMemo(
    () => visiblePages.filter((page) => page.manual),
    [visiblePages],
  );
  const exportDownloadUrl = resolveArtifactUrl(job?.export.downloadUrl ?? null);
  const sourceVideoUrl = resolveArtifactUrl(job?.sourceVideoUrl ?? null);

  useEffect(() => {
    setActionError(null);
    setVideoCurrentTime(0);
    setVideoDuration(0);
    setIsVideoReady(false);
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.currentTime = 0;
    }
  }, [job?.id]);

  function formatTime(seconds: number): string {
    const safeSeconds = Math.max(seconds, 0);
    const totalSeconds = Math.floor(safeSeconds);
    const minutes = Math.floor(totalSeconds / 60);
    const remainder = totalSeconds % 60;
    const tenths = Math.floor((safeSeconds - totalSeconds) * 10);
    return `${minutes}:${String(remainder).padStart(2, "0")}.${tenths}`;
  }

  function seekVideo(targetTime: number) {
    const element = videoRef.current;
    if (!element) {
      return;
    }
    const clamped = Math.max(0, Math.min(targetTime, videoDuration || targetTime));
    element.currentTime = clamped;
    setVideoCurrentTime(clamped);
  }

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

  async function handleReorder(activeOrder: string[]) {
    if (!job) {
      return;
    }

    const deletedPageIds = job.pages.filter((page) => page.deleted).map((page) => page.id);
    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await reorderPages(job.id, [...activeOrder, ...deletedPageIds]);
      onJobUpdated(updatedJob);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to reorder pages.");
    } finally {
      setIsMutating(false);
      setDraggedPageId(null);
    }
  }

  async function handleBulkDelete() {
    if (!job || visiblePages.length === 0) {
      return;
    }

    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await bulkUpdatePages(job.id, {
        pageIds: visiblePages.map((page) => page.id),
        deleted: true,
      });
      onJobUpdated(updatedJob);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to remove pages.");
    } finally {
      setIsMutating(false);
    }
  }

  async function handleRestoreAll() {
    if (!job || deletedPages.length === 0) {
      return;
    }

    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await bulkUpdatePages(job.id, {
        pageIds: deletedPages.map((page) => page.id),
        deleted: false,
      });
      onJobUpdated(updatedJob);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to restore pages.");
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

  async function handleAddManualPage() {
    if (!job) {
      return;
    }

    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await addManualPage(job.id, videoCurrentTime);
      onJobUpdated(updatedJob);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to add manual page.");
    } finally {
      setIsMutating(false);
    }
  }

  return (
    <SectionCard
      eyebrow="Review"
      title="Review board"
      subtitle="Inspect extracted pages, make lightweight corrections, and export the final document."
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
              <div className="review-summary-card__meta">
                <p className="muted">
                  {job.processingMode === "camera"
                    ? "Camera / physical-page mode"
                    : "Screen-recording mode"}
                </p>
                <p className="muted">{job.progress.message}</p>
              </div>
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
                <strong>{deletedPages.length}</strong>
                <span>Pages removed</span>
              </div>
              <div className="review-metric">
                <strong>{job.stages.filter((stage) => stage.status === "complete").length}</strong>
                <span>Stages complete</span>
              </div>
              <div className="review-metric">
                <strong>{manualPages.length}</strong>
                <span>Manual recovery pages</span>
              </div>
            </div>
          </div>
          <div className="review-workspace">
            <div className="review-video-panel">
              <div className="review-video-panel__header">
                <div>
                  <span className="review-summary-card__eyebrow">Source video</span>
                  <h3>Recover missed pages from the original recording</h3>
                  <p className="muted">
                    Pause on a clean frame, scrub precisely, and save it as a real review page.
                  </p>
                </div>
                <button
                  className="primary-button"
                  disabled={!sourceVideoUrl || isMutating || !isVideoReady}
                  onClick={() => void handleAddManualPage()}
                  type="button"
                >
                  Add current frame as page
                </button>
              </div>
              {sourceVideoUrl ? (
                <div className="video-reviewer">
                  <div className="video-reviewer__surface">
                    <video
                      className="video-reviewer__player"
                      controls
                      preload="metadata"
                      ref={videoRef}
                      src={sourceVideoUrl}
                      onLoadedMetadata={(event) => {
                        const duration = Number.isFinite(event.currentTarget.duration)
                          ? event.currentTarget.duration
                          : 0;
                        setVideoDuration(duration);
                        setVideoCurrentTime(event.currentTarget.currentTime);
                        setIsVideoReady(duration > 0);
                      }}
                      onTimeUpdate={(event) => setVideoCurrentTime(event.currentTarget.currentTime)}
                    />
                  </div>
                  <div className="video-reviewer__controls">
                    <div className="video-reviewer__timeline">
                      <input
                        aria-label="Video timeline"
                        className="video-reviewer__scrubber"
                        disabled={!isVideoReady}
                        max={videoDuration || 0}
                        min={0}
                        onChange={(event) => seekVideo(Number(event.target.value))}
                        step={0.05}
                        type="range"
                        value={Math.min(videoCurrentTime, videoDuration || videoCurrentTime)}
                      />
                      <div className="video-reviewer__time-row">
                        <strong>{formatTime(videoCurrentTime)}</strong>
                        <span>{formatTime(videoDuration)}</span>
                      </div>
                    </div>
                    <div className="video-reviewer__actions">
                      <button
                        className="secondary-button"
                        disabled={!isVideoReady}
                        onClick={() => seekVideo(videoCurrentTime - 1)}
                        type="button"
                      >
                        Back 1s
                      </button>
                      <button
                        className="secondary-button"
                        disabled={!isVideoReady}
                        onClick={() => seekVideo(videoCurrentTime - 0.2)}
                        type="button"
                      >
                        Back 0.2s
                      </button>
                      <button
                        className="secondary-button"
                        disabled={!isVideoReady}
                        onClick={() => seekVideo(videoCurrentTime + 0.2)}
                        type="button"
                      >
                        Forward 0.2s
                      </button>
                      <button
                        className="secondary-button"
                        disabled={!isVideoReady}
                        onClick={() => seekVideo(videoCurrentTime + 1)}
                        type="button"
                      >
                        Forward 1s
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="empty-state">
                  <strong>Source video unavailable</strong>
                  <p>This session does not expose a playable source video artifact yet.</p>
                </div>
              )}
            </div>
            <div className="review-recovery-panel">
              <span className="review-summary-card__eyebrow">Recovery status</span>
              <div className="review-recovery-panel__stats">
                <div className="review-recovery-stat">
                  <strong>{manualPages.length}</strong>
                  <span>Recovered manually</span>
                </div>
                <div className="review-recovery-stat">
                  <strong>{visiblePages.length - manualPages.length}</strong>
                  <span>Kept automatically</span>
                </div>
              </div>
              <p className="muted">
                Manual pages persist through the same rotate, reorder, delete, restore, and export path
                as automatically extracted pages.
              </p>
            </div>
          </div>
          <div className="review-toolbar">
            <div className="review-toolbar__group">
              <button
                className="secondary-button"
                disabled={isMutating || visiblePages.length === 0}
                onClick={() => void handleBulkDelete()}
                type="button"
              >
                Remove all active pages
              </button>
              <button
                className="secondary-button"
                disabled={isMutating || deletedPages.length === 0}
                onClick={() => void handleRestoreAll()}
                type="button"
              >
                Restore all removed pages
              </button>
            </div>
            <span className="review-toolbar__hint">
              Drag active page cards to reorder them faster than move up/down.
            </span>
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
              {exportDownloadUrl ? (
                <a
                  className="download-link"
                  href={exportDownloadUrl}
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
              {visiblePages.map((page, index) => {
                const thumbnailUrl = resolveArtifactUrl(page.thumbnailUrl);

                return (
                <article
                  className={`page-card ${draggedPageId === page.id ? "page-card--dragging" : ""}`}
                  draggable={!isMutating}
                  key={page.id}
                  onDragEnd={() => setDraggedPageId(null)}
                  onDragOver={(event) => {
                    event.preventDefault();
                  }}
                  onDragStart={() => setDraggedPageId(page.id)}
                  onDrop={() => {
                    if (!draggedPageId || draggedPageId === page.id) {
                      return;
                    }

                    const reorderedIds = [...visiblePages.map((item) => item.id)];
                    const fromIndex = reorderedIds.indexOf(draggedPageId);
                    const toIndex = reorderedIds.indexOf(page.id);
                    if (fromIndex < 0 || toIndex < 0) {
                      return;
                    }
                    reorderedIds.splice(fromIndex, 1);
                    reorderedIds.splice(toIndex, 0, draggedPageId);
                    void handleReorder(reorderedIds);
                  }}
                >
                  <div className="page-card__preview">
                    <div className="page-card__preview-tag">Page preview</div>
                    <div className="page-card__drag-handle">Drag to reorder</div>
                    {thumbnailUrl ? (
                      <img
                        alt={page.previewLabel}
                        className="page-preview-image"
                        src={thumbnailUrl}
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
                      <div className="page-card__title">
                        <h4>Page {index + 1}</h4>
                        {page.manual ? (
                          <span className="page-origin-badge page-origin-badge--manual">Manual</span>
                        ) : (
                          <span className="page-origin-badge">Auto</span>
                        )}
                      </div>
                      <span className="page-score">
                        Score {page.sharpnessScore.toFixed(2)}
                      </span>
                    </div>
                    <div className="page-meta-row">
                      <span>
                        {page.manual
                          ? `Recovered at ${page.sourceTimestamp.toFixed(1)}s`
                          : `Segment ${page.segmentStart.toFixed(1)}s to ${page.segmentEnd.toFixed(1)}s`}
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
                );
              })}
            </div>
          )}
          {deletedPages.length > 0 ? (
            <div className="deleted-pages-panel">
              <div className="deleted-pages-panel__header">
                <div>
                  <strong>Removed pages</strong>
                  <p>These pages are excluded from export, but can be restored.</p>
                </div>
              </div>
              <div className="deleted-pages-list">
                {deletedPages.map((page) => (
                  <article className="deleted-page-card" key={page.id}>
                    <div>
                      <strong>
                        {page.previewLabel} {page.manual ? "• Manual" : "• Auto"}
                      </strong>
                      <span>
                        Frame #{page.sourceFrameIndex} at {page.sourceTimestamp.toFixed(1)}s
                      </span>
                    </div>
                    <div className="deleted-page-card__actions">
                      <button
                        className="secondary-button"
                        disabled={isMutating}
                        onClick={() => void handleDelete(page.id, false)}
                        type="button"
                      >
                        Restore
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </SectionCard>
  );
}
