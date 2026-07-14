import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ClipboardCopy,
  Download,
  FileText,
  GripVertical,
  Loader2,
  Pencil,
  RefreshCw,
  RotateCw,
  Trash2,
} from "lucide-react";
import type { ExtractedPage, PageEdits, ProcessingJob, Sensitivity } from "../../types";
import { SectionCard } from "../../components/SectionCard";
import { useToast } from "../../components/Toast";
import {
  addManualPage,
  bulkUpdatePages,
  reorderPages,
  reprocessJob,
  resolveArtifactUrl,
  updatePage,
} from "../../lib/api";
import { PageEditorModal } from "./PageEditorModal";

type ReviewTab = "pages" | "text" | "video" | "deleted";

/** Page artifacts are rewritten in place on rotate/edit; bust the browser cache. */
function withCacheKey(url: string | null, cacheKey: string): string | null {
  if (!url) {
    return null;
  }
  return `${url}${url.includes("?") ? "&" : "?"}v=${encodeURIComponent(cacheKey)}`;
}

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
  const [sensitivity, setSensitivity] = useState<Sensitivity>("balanced");
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const visiblePages = job?.pages.filter((page) => !page.deleted) ?? [];
  const deletedPages = job?.pages.filter((page) => page.deleted) ?? [];
  const sourceVideoUrl = resolveArtifactUrl(job?.sourceVideoUrl ?? null);

  useEffect(() => {
    setActionError(null);
    setVideoCurrentTime(0);
    setVideoDuration(0);
    setIsVideoReady(false);
    setActiveTab("pages");
    setSensitivity(job?.sensitivity ?? "balanced");
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.currentTime = 0;
    }
  }, [job?.id, job?.sensitivity]);

  useEffect(() => {
    if (activeTab === "deleted" && deletedPages.length === 0) {
      setActiveTab("pages");
    }
  }, [deletedPages.length, activeTab]);

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

  async function runPageAction(action: () => Promise<ProcessingJob>, failureMessage: string) {
    if (!job) {
      return false;
    }
    setIsMutating(true);
    setActionError(null);
    try {
      const updatedJob = await action();
      onJobUpdated(updatedJob);
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : failureMessage;
      setActionError(message);
      toast(message, "error");
      return false;
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSaveEdits(pageId: string, edits: PageEdits) {
    const ok = await runPageAction(
      () => updatePage(job!.id, pageId, { edits }),
      "Failed to save page edits.",
    );
    if (ok) {
      setEditingPage(null);
      toast("Page edits saved.", "success");
    }
  }

  async function handleRotate(page: ExtractedPage) {
    await runPageAction(
      () => updatePage(job!.id, page.id, { rotation: (page.edits.rotation + 90) % 360 }),
      "Failed to rotate page.",
    );
  }

  async function handleDelete(pageId: string, deleted: boolean) {
    const ok = await runPageAction(
      () => updatePage(job!.id, pageId, { deleted }),
      "Failed to update page.",
    );
    if (ok) {
      toast(deleted ? "Page removed." : "Page restored.", "success");
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
    const deletedPageIds = deletedPages.map((page) => page.id);
    await runPageAction(
      () => reorderPages(job.id, [...reordered.map((page) => page.id), ...deletedPageIds]),
      "Failed to reorder pages.",
    );
  }

  async function handleReorder(activeOrder: string[]) {
    if (!job) {
      return;
    }
    const deletedPageIds = deletedPages.map((page) => page.id);
    await runPageAction(
      () => reorderPages(job.id, [...activeOrder, ...deletedPageIds]),
      "Failed to reorder pages.",
    );
    setDraggedPageId(null);
  }

  async function handleRestoreAll() {
    if (!job || deletedPages.length === 0) {
      return;
    }
    const ok = await runPageAction(
      () =>
        bulkUpdatePages(job.id, {
          pageIds: deletedPages.map((page) => page.id),
          deleted: false,
        }),
      "Failed to restore pages.",
    );
    if (ok) {
      toast("All removed pages restored.", "success");
    }
  }

  async function handleAddManualPage() {
    if (!job) {
      return;
    }
    const ok = await runPageAction(
      () => addManualPage(job.id, videoCurrentTime),
      "Failed to add manual page.",
    );
    if (ok) {
      toast("Frame added as a new page.", "success");
    }
  }

  async function handleReprocess() {
    if (!job) {
      return;
    }
    const ok = await runPageAction(
      () => reprocessJob(job.id, sensitivity),
      "Failed to re-process the session.",
    );
    if (ok) {
      toast("Re-processing started with new detection settings.", "success");
    }
  }

  function collectExtractedText(): string {
    if (!job) {
      return "";
    }
    return visiblePages
      .map((page, index) => {
        const heading = `--- Page ${index + 1} ---`;
        if (page.ocrStatus === "ready" && page.ocrText) {
          return `${heading}\n${page.ocrText}`;
        }
        return `${heading}\n[no text]`;
      })
      .join("\n\n");
  }

  function handleDownloadText() {
    const blob = new Blob([collectExtractedText()], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${job?.filename.replace(/\.[^.]+$/, "") || "vid2pdf"}-text.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function handleCopyText() {
    try {
      await navigator.clipboard.writeText(collectExtractedText());
      toast("Extracted text copied to clipboard.", "success");
    } catch {
      toast("Could not access the clipboard.", "error");
    }
  }

  if (!job) {
    return null;
  }

  const isProcessing = job.status === "processing" || job.status === "queued";
  const pagesWithText = visiblePages.filter(
    (page) => page.ocrStatus === "ready" && page.ocrText,
  );

  return (
    <SectionCard
      title="Pages"
      subtitle={`${visiblePages.length} page${visiblePages.length === 1 ? "" : "s"} in the export${
        deletedPages.length > 0 ? ` · ${deletedPages.length} removed` : ""
      }`}
    >
      <div className="review-board">
        {isProcessing ? (
          <div className="progress-block">
            <div className="progress-block__track">
              <div
                className="progress-block__fill"
                style={{ width: `${job.progress.percent}%` }}
              />
            </div>
            <span>{job.progress.message}</span>
            <div className="stage-strip">
              {job.stages.map((stage) => (
                <div className="stage-chip" key={stage.key}>
                  <span className={`stage-chip__dot stage-chip__dot--${stage.status}`} />
                  <span>{stage.label}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {job.export.status === "failed" && job.export.error ? (
          <div className="status-banner status-banner--error">
            <strong>Image PDF export failed</strong>
            <span>{job.export.error}</span>
          </div>
        ) : null}

        {actionError ? (
          <div className="status-banner status-banner--error">
            <strong>Action failed</strong>
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
            Pages
          </button>
          <button
            className={`review-tab ${activeTab === "text" ? "review-tab--active" : ""}`}
            onClick={() => setActiveTab("text")}
            role="tab"
            aria-selected={activeTab === "text"}
            type="button"
          >
            Extracted text
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
              Removed ({deletedPages.length})
            </button>
          ) : null}
        </div>

        {activeTab === "pages" ? (
          <div className="review-tab-panel" role="tabpanel">
            {job.status === "ready" ? (
              <div className="reprocess-bar">
                <span className="reprocess-bar__hint">
                  Missing pages or seeing duplicates? Adjust detection and run again.
                </span>
                <div className="reprocess-bar__controls">
                  <select
                    aria-label="Page detection sensitivity"
                    className="select-input"
                    disabled={isMutating}
                    value={sensitivity}
                    onChange={(event) => setSensitivity(event.target.value as Sensitivity)}
                  >
                    <option value="fewer">Fewer pages</option>
                    <option value="balanced">Balanced</option>
                    <option value="more">More pages</option>
                  </select>
                  <button
                    className="secondary-button"
                    disabled={isMutating}
                    onClick={() => void handleReprocess()}
                    type="button"
                  >
                    <RefreshCw size={14} aria-hidden="true" />
                    Re-process
                  </button>
                </div>
              </div>
            ) : null}
            {job.status !== "ready" && visiblePages.length === 0 ? (
              <div className="page-grid-skeleton" aria-label="Processing pages">
                <span />
                <span />
                <span />
                <span />
              </div>
            ) : visiblePages.length === 0 ? (
              <div className="empty-state empty-state--large">
                <strong>No pages in this session</strong>
                <p>Restore removed pages or recover frames from the source video.</p>
              </div>
            ) : (
              <div className="page-grid">
                {visiblePages.map((page, index) => {
                  const thumbnailUrl = withCacheKey(
                    resolveArtifactUrl(page.thumbnailUrl),
                    job.updatedAt,
                  );

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
                        {thumbnailUrl ? (
                          <img
                            alt={`Page ${index + 1}`}
                            className="page-preview-image"
                            src={thumbnailUrl}
                          />
                        ) : (
                          <div className="page-placeholder">
                            <span>Page {index + 1}</span>
                          </div>
                        )}
                      </div>
                      <div className="page-card__footer">
                        <div className="page-card__label">
                          <GripVertical
                            className="page-card__grip"
                            size={13}
                            aria-hidden="true"
                          />
                          <strong>Page {index + 1}</strong>
                          {page.manual ? (
                            <span className="page-badge">Manual</span>
                          ) : null}
                          {hasEdits(page) ? (
                            <span className="page-badge">Edited</span>
                          ) : null}
                          {page.ocrStatus === "failed" ? (
                            <span className="page-badge page-badge--warn">OCR failed</span>
                          ) : null}
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
                          </button>
                          <button
                            className="icon-button"
                            disabled={isMutating || index === visiblePages.length - 1}
                            onClick={() => void handleShift(page.id, 1)}
                            title="Move down"
                            type="button"
                          >
                            <ArrowDown size={14} aria-hidden="true" />
                          </button>
                          <button
                            className="icon-button"
                            disabled={isMutating}
                            onClick={() => void handleRotate(page)}
                            title="Rotate 90° clockwise"
                            type="button"
                          >
                            <RotateCw size={14} aria-hidden="true" />
                          </button>
                          <button
                            className="icon-button"
                            disabled={isMutating}
                            onClick={() => setEditingPage(page)}
                            title="Edit page"
                            type="button"
                          >
                            <Pencil size={14} aria-hidden="true" />
                          </button>
                          <button
                            className="icon-button icon-button--danger"
                            disabled={isMutating}
                            onClick={() => void handleDelete(page.id, true)}
                            title="Remove page"
                            type="button"
                          >
                            <Trash2 size={14} aria-hidden="true" />
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        ) : null}

        {activeTab === "text" ? (
          <div className="review-tab-panel" role="tabpanel">
            {pagesWithText.length === 0 ? (
              <div className="empty-state">
                <FileText size={24} aria-hidden="true" />
                <strong>No extracted text yet</strong>
                <p>
                  {visiblePages.length === 0
                    ? "There are no pages to extract text from."
                    : "Text appears here after OCR runs. Pages edited recently are re-read during the next text export."}
                </p>
              </div>
            ) : (
              <div className="ocr-text-list">
                <div className="review-toolbar">
                  <button
                    className="secondary-button"
                    onClick={() => void handleCopyText()}
                    type="button"
                  >
                    <ClipboardCopy size={14} aria-hidden="true" />
                    Copy all
                  </button>
                  <button
                    className="secondary-button"
                    onClick={handleDownloadText}
                    type="button"
                  >
                    <Download size={14} aria-hidden="true" />
                    Download .txt
                  </button>
                </div>
                {visiblePages.map((page, index) => (
                  <article className="ocr-text-card" key={page.id}>
                    <header>
                      <strong>Page {index + 1}</strong>
                      {page.ocrStatus === "ready" && page.ocrText ? (
                        <span className="muted">{page.ocrText.length} characters</span>
                      ) : (
                        <span className="muted">
                          {page.ocrStatus === "empty"
                            ? "No text detected"
                            : page.ocrStatus === "failed"
                              ? "OCR failed"
                              : "Pending OCR"}
                        </span>
                      )}
                    </header>
                    {page.ocrStatus === "ready" && page.ocrText ? (
                      <p>{page.ocrText}</p>
                    ) : null}
                  </article>
                ))}
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
                        −1s
                      </button>
                      <button
                        className="secondary-button"
                        disabled={!isVideoReady}
                        onClick={() => seekVideo(videoCurrentTime - 0.2)}
                        type="button"
                      >
                        −0.2s
                      </button>
                      <button
                        className="secondary-button"
                        disabled={!isVideoReady}
                        onClick={() => seekVideo(videoCurrentTime + 0.2)}
                        type="button"
                      >
                        +0.2s
                      </button>
                      <button
                        className="secondary-button"
                        disabled={!isVideoReady}
                        onClick={() => seekVideo(videoCurrentTime + 1)}
                        type="button"
                      >
                        +1s
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="empty-state">
                  <strong>Source video unavailable</strong>
                  <p>This session does not expose a playable source video.</p>
                </div>
              )}
            </div>
          </div>
        ) : null}

        {activeTab === "deleted" && deletedPages.length > 0 ? (
          <div className="review-tab-panel" role="tabpanel">
            <div className="deleted-pages-panel">
              <div className="deleted-pages-panel__header">
                <p>These pages are excluded from export but can be restored.</p>
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
                      <strong>{page.previewLabel}</strong>
                      <span>
                        {page.manual ? "Manual · " : ""}from {page.sourceTimestamp.toFixed(1)}s
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
    (page.edits.filter ?? "none") !== "none" ||
    page.edits.strokes.length > 0 ||
    page.edits.texts.length > 0 ||
    page.edits.blurRegions.length > 0
  );
}
