import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  GripVertical,
  Loader2,
  Pencil,
  RotateCw,
  Trash2,
} from "lucide-react";
import type { ExtractedPage, PageEdits, ProcessingJob } from "../../types";
import { SectionCard } from "../../components/SectionCard";
import { useToast } from "../../components/Toast";
import {
  addManualPage,
  bulkUpdatePages,
  reorderPages,
  resolveArtifactUrl,
  updatePage,
} from "../../lib/api";
import { PageEditorModal } from "./PageEditorModal";

type ReviewTab = "pages" | "video" | "deleted";

interface PageReviewBoardProps {
  job: ProcessingJob | null;
  onJobUpdated: (job: ProcessingJob) => void;
}

export function PageReviewBoard({ job, onJobUpdated }: PageReviewBoardProps) {
  const { toast } = useToast();
  const [actionError, setActionError] = useState<string | null>(null);
  const [isMutating, setIsMutating] = useState(false);
  const [draggedPageId, setDraggedPageId] = useState<string | null>(null);
  const [videoCurrentTime, setVideoCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [isVideoReady, setIsVideoReady] = useState(false);
  const [editingPage, setEditingPage] = useState<ExtractedPage | null>(null);
  const [activeTab, setActiveTab] = useState<ReviewTab>("pages");
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
    setActiveTab("pages");
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.currentTime = 0;
    }
  }, [job?.id]);

  useEffect(() => {
    if (visiblePages.length > 0 && activeTab === "video") {
      return;
    }
    if (deletedPages.length > 0 && activeTab === "deleted") {
      return;
    }
  }, [visiblePages.length, deletedPages.length, activeTab]);

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

  async function handleSaveEdits(pageId: string, edits: PageEdits) {
    if (!job) {
      return;
    }

    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await updatePage(job.id, pageId, { edits });
      onJobUpdated(updatedJob);
      setEditingPage(null);
      toast("Page edits saved.", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save page edits.";
      setActionError(message);
      toast(message, "error");
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
      toast(deleted ? "Page removed." : "Page restored.", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update page.";
      setActionError(message);
      toast(message, "error");
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

    const deletedPageIds = job.pages.filter((page) => page.deleted).map((page) => page.id);
    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await reorderPages(job.id, [
        ...reordered.map((page) => page.id),
        ...deletedPageIds,
      ]);
      onJobUpdated(updatedJob);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to reorder pages.";
      setActionError(message);
      toast(message, "error");
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
      const message = error instanceof Error ? error.message : "Failed to reorder pages.";
      setActionError(message);
      toast(message, "error");
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
      toast("All active pages removed.", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to remove pages.";
      setActionError(message);
      toast(message, "error");
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
      toast("All removed pages restored.", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to restore pages.";
      setActionError(message);
      toast(message, "error");
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
      toast("Frame added as a new page.", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to add manual page.";
      setActionError(message);
      toast(message, "error");
    } finally {
      setIsMutating(false);
    }
  }

  if (!job) {
    return null;
  }

  return (
    <SectionCard
      eyebrow="Review"
      title="Page review"
      subtitle="Inspect extracted pages, make corrections, and prepare for export."
    >
      <div className="review-board">
        <div className="review-summary-row">
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
              <strong>
                {job.stages.filter((stage) => stage.status === "complete").length}
              </strong>
              <span>Stages complete</span>
            </div>
            <div className="review-metric">
              <strong>{manualPages.length}</strong>
              <span>Manual recovery</span>
            </div>
          </div>

          <div className="progress-block">
            <div className="progress-block__track">
              <div
                className="progress-block__fill"
                style={{ width: `${job.progress.percent}%` }}
              />
            </div>
            <span>{job.progress.percent}% — {job.progress.message}</span>
          </div>
        </div>

        {job.status === "processing" || job.status === "queued" ? (
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
        ) : null}

        {job.export.status !== "idle" ? (
          <div
            className={`status-banner ${job.export.status === "failed" ? "status-banner--error" : ""}`}
          >
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
                  ? `${job.export.progressPercent}% complete. Preparing the final PDF.`
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

        <div className="review-tabs" role="tablist" aria-label="Review sections">
          <button
            className={`review-tab ${activeTab === "pages" ? "review-tab--active" : ""}`}
            onClick={() => setActiveTab("pages")}
            role="tab"
            aria-selected={activeTab === "pages"}
            type="button"
          >
            Pages ({visiblePages.length})
          </button>
          <button
            className={`review-tab ${activeTab === "video" ? "review-tab--active" : ""}`}
            onClick={() => setActiveTab("video")}
            role="tab"
            aria-selected={activeTab === "video"}
            type="button"
          >
            Source video
          </button>
          {deletedPages.length > 0 ? (
            <button
              className={`review-tab ${activeTab === "deleted" ? "review-tab--active" : ""}`}
              onClick={() => setActiveTab("deleted")}
              role="tab"
              aria-selected={activeTab === "deleted"}
              type="button"
            >
              Deleted ({deletedPages.length})
            </button>
          ) : null}
        </div>

        {activeTab === "pages" ? (
          <div className="review-tab-panel" role="tabpanel">
            <div className="review-toolbar">
              <div className="review-toolbar__group">
                <button
                  className="secondary-button danger-button"
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
                Drag page cards to reorder, or use the arrow buttons.
              </span>
            </div>

            {job.status !== "ready" ? (
              <div className="page-grid-skeleton" aria-label="Processing pages">
                <span />
                <span />
                <span />
                <span />
              </div>
            ) : visiblePages.length === 0 ? (
              <div className="empty-state empty-state--large">
                <strong>No active pages available</strong>
                <p>Restore removed pages or recover frames from the source video.</p>
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
                      onDragOver={(event) => event.preventDefault()}
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
                        <div className="page-card__preview-tag">Page {index + 1}</div>
                        <div className="page-card__drag-handle">
                          <GripVertical size={12} aria-hidden="true" />
                          Drag
                        </div>
                        {thumbnailUrl ? (
                          <img
                            alt={page.previewLabel}
                            className="page-preview-image"
                            src={thumbnailUrl}
                          />
                        ) : (
                          <div className="page-placeholder">
                            <span>{page.previewLabel}</span>
                          </div>
                        )}
                      </div>
                      <div className="page-card__content">
                        <div className="page-card__header">
                          <div className="page-card__title">
                            <h4>Page {index + 1}</h4>
                            {page.manual ? (
                              <span className="page-origin-badge page-origin-badge--manual">
                                Manual
                              </span>
                            ) : (
                              <span className="page-origin-badge">Auto</span>
                            )}
                            {hasEdits(page) ? (
                              <span className="page-origin-badge page-origin-badge--edited">
                                Edited
                              </span>
                            ) : null}
                            {page.ocrStatus === "ready" ? (
                              <span className="page-origin-badge page-origin-badge--manual">
                                OCR
                              </span>
                            ) : page.ocrStatus === "empty" ? (
                              <span className="page-origin-badge">No text</span>
                            ) : page.ocrStatus === "failed" ? (
                              <span className="page-origin-badge page-origin-badge--edited">
                                OCR failed
                              </span>
                            ) : null}
                          </div>
                          <span className="page-score">
                            {page.sharpnessScore.toFixed(2)}
                          </span>
                        </div>
                        <div className="page-meta-row">
                          <span>
                            {page.manual
                              ? `Recovered at ${page.sourceTimestamp.toFixed(1)}s`
                              : `Segment ${page.segmentStart.toFixed(1)}s–${page.segmentEnd.toFixed(1)}s`}
                          </span>
                          <span>{page.edits.rotation}°</span>
                        </div>
                      </div>
                      <div className="page-card__actions">
                        <button
                          className="icon-button"
                          disabled={isMutating || index === 0}
                          onClick={() => void handleShift(page.id, -1)}
                          title="Move up"
                          type="button"
                        >
                          <ArrowUp size={14} aria-hidden="true" />
                          <span>Up</span>
                        </button>
                        <button
                          className="icon-button"
                          disabled={isMutating || index === visiblePages.length - 1}
                          onClick={() => void handleShift(page.id, 1)}
                          title="Move down"
                          type="button"
                        >
                          <ArrowDown size={14} aria-hidden="true" />
                          <span>Down</span>
                        </button>
                        <button
                          className="icon-button"
                          disabled={isMutating}
                          onClick={() => setEditingPage(page)}
                          title="Edit page"
                          type="button"
                        >
                          <Pencil size={14} aria-hidden="true" />
                          <span>Edit</span>
                        </button>
                        <button
                          className="icon-button icon-button--danger"
                          disabled={isMutating}
                          onClick={() => void handleDelete(page.id, true)}
                          title="Delete page"
                          type="button"
                        >
                          <Trash2 size={14} aria-hidden="true" />
                          <span>Delete</span>
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        ) : null}

        {activeTab === "video" ? (
          <div className="review-tab-panel" role="tabpanel">
            <div className="review-video-panel">
              <div className="review-video-panel__header">
                <div>
                  <h3>Recover missed pages</h3>
                  <p className="muted">
                    Scrub to a clean frame and save it as a reviewable page.
                  </p>
                </div>
                <button
                  className="primary-button"
                  disabled={!sourceVideoUrl || isMutating || !isVideoReady}
                  onClick={() => void handleAddManualPage()}
                  type="button"
                >
                  {isMutating ? (
                    <Loader2 size={16} className="spin" aria-hidden="true" />
                  ) : null}
                  Add current frame
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
                      onTimeUpdate={(event) =>
                        setVideoCurrentTime(event.currentTarget.currentTime)
                      }
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
                  <p>This session does not expose a playable source video yet.</p>
                </div>
              )}
            </div>
          </div>
        ) : null}

        {activeTab === "deleted" && deletedPages.length > 0 ? (
          <div className="review-tab-panel" role="tabpanel">
            <div className="deleted-pages-panel">
              <div className="deleted-pages-panel__header">
                <div>
                  <strong>Removed pages</strong>
                  <p>These pages are excluded from export but can be restored.</p>
                </div>
                <button
                  className="secondary-button"
                  disabled={isMutating}
                  onClick={() => void handleRestoreAll()}
                  type="button"
                >
                  Restore all
                </button>
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
                    <button
                      className="secondary-button"
                      disabled={isMutating}
                      onClick={() => void handleDelete(page.id, false)}
                      type="button"
                    >
                      Restore
                    </button>
                  </article>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <PageEditorModal
        isSaving={isMutating}
        page={editingPage}
        onClose={() => setEditingPage(null)}
        onSave={(edits) => handleSaveEdits(editingPage!.id, edits)}
      />
    </SectionCard>
  );
}

function hasEdits(page: ExtractedPage): boolean {
  return (
    page.edits.rotation !== 0 ||
    page.edits.crop !== null ||
    page.edits.strokes.length > 0 ||
    page.edits.texts.length > 0 ||
    page.edits.blurRegions.length > 0
  );
}
