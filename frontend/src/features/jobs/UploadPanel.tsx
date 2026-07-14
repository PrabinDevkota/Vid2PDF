import { useEffect, useRef, useState } from "react";
import { Link2, Loader2, Upload, X } from "lucide-react";
import type { ProcessingJob, ProcessingMode } from "../../types";
import { createJobFromUrl, fetchOcrLanguages, uploadVideo } from "../../lib/api";
import { SectionCard } from "../../components/SectionCard";
import { useToast } from "../../components/Toast";

const DEFAULT_MODE_KEY = "vid2pdf-default-mode";
const DEFAULT_LANGUAGE_KEY = "vid2pdf-ocr-language";

const LANGUAGE_NAMES: Record<string, string> = {
  eng: "English",
  nep: "Nepali",
  hin: "Hindi",
  deu: "German",
  fra: "French",
  spa: "Spanish",
  ita: "Italian",
  por: "Portuguese",
  nld: "Dutch",
  rus: "Russian",
  ara: "Arabic",
  jpn: "Japanese",
  kor: "Korean",
  chi_sim: "Chinese (Simplified)",
  chi_tra: "Chinese (Traditional)",
};

function languageLabel(code: string): string {
  return LANGUAGE_NAMES[code] ? `${LANGUAGE_NAMES[code]} (${code})` : code;
}

/** Parse "90", "1:30", or "1:02:30" into seconds; empty → null; invalid → NaN. */
function parseTimeInput(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  if (!/^\d+(:[0-5]?\d){0,2}(\.\d+)?$/.test(trimmed)) {
    return Number.NaN;
  }
  const parts = trimmed.split(":").map(Number);
  return parts.reduce((total, part) => total * 60 + part, 0);
}

type SourceKind = "file" | "url";

interface UploadPanelProps {
  onJobCreated: (job: ProcessingJob) => void;
  compact?: boolean;
}

const MAX_BATCH_FILES = 10;

export function UploadPanel({ onJobCreated, compact }: UploadPanelProps) {
  const { toast } = useToast();
  const [sourceKind, setSourceKind] = useState<SourceKind>("file");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null);
  const [failedIndexes, setFailedIndexes] = useState<Set<number>>(new Set());
  const [videoUrl, setVideoUrl] = useState("");
  const [processingMode, setProcessingMode] = useState<ProcessingMode>("screen");
  const [ocrLanguage, setOcrLanguage] = useState("eng");
  const [languages, setLanguages] = useState<string[]>(["eng"]);
  const [trimStartText, setTrimStartText] = useState("");
  const [trimEndText, setTrimEndText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const storedMode = localStorage.getItem(DEFAULT_MODE_KEY);
    if (storedMode === "screen" || storedMode === "camera") {
      setProcessingMode(storedMode);
    }
    const storedLanguage = localStorage.getItem(DEFAULT_LANGUAGE_KEY);
    if (storedLanguage) {
      setOcrLanguage(storedLanguage);
    }
    fetchOcrLanguages()
      .then((result) => {
        setLanguages(result.languages);
        if (storedLanguage && !result.languages.includes(storedLanguage)) {
          setOcrLanguage(result.default);
        }
      })
      .catch(() => {
        // Backend unreachable; keep the default list.
      });
  }, []);

  function addFiles(files: FileList | File[] | null) {
    if (!files || files.length === 0) {
      return;
    }
    setSelectedFiles((current) => {
      const merged = [...current];
      for (const file of Array.from(files)) {
        const isDuplicate = merged.some(
          (item) => item.name === file.name && item.size === file.size,
        );
        if (!isDuplicate) {
          merged.push(file);
        }
      }
      if (merged.length > MAX_BATCH_FILES) {
        toast(`Up to ${MAX_BATCH_FILES} videos per batch.`, "error");
      }
      return merged.slice(0, MAX_BATCH_FILES);
    });
    setFailedIndexes(new Set());
    setError(null);
  }

  function removeFile(index: number) {
    setSelectedFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setFailedIndexes(new Set());
  }

  function chooseLanguage(code: string) {
    setOcrLanguage(code);
    localStorage.setItem(DEFAULT_LANGUAGE_KEY, code);
  }

  function openFilePicker() {
    inputRef.current?.click();
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sourceKind === "file" && selectedFiles.length === 0) {
      setError("Choose one or more video files to start processing.");
      return;
    }
    if (sourceKind === "url" && !/^https?:\/\/\S+$/i.test(videoUrl.trim())) {
      setError("Enter a valid http(s) video URL.");
      return;
    }

    const trimStart = parseTimeInput(trimStartText);
    const trimEnd = parseTimeInput(trimEndText);
    if (Number.isNaN(trimStart) || Number.isNaN(trimEnd)) {
      setError("Time range must be seconds or mm:ss (for example 90 or 1:30).");
      return;
    }
    if (trimStart != null && trimEnd != null && trimEnd <= trimStart) {
      setError("The end of the time range must be after the start.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    const trim = { trimStart, trimEnd };

    if (sourceKind === "url") {
      try {
        const job = await createJobFromUrl(videoUrl.trim(), processingMode, ocrLanguage, trim);
        onJobCreated(job);
        toast("Session created — downloading the video.", "success");
        setVideoUrl("");
        setTrimStartText("");
        setTrimEndText("");
      } catch (submissionError) {
        const message =
          submissionError instanceof Error ? submissionError.message : "Upload failed.";
        setError(message);
        toast(message, "error");
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Upload files one at a time; each becomes an independent session.
    const failed = new Set<number>();
    let firstJob: ProcessingJob | null = null;
    let firstError: string | null = null;
    for (let index = 0; index < selectedFiles.length; index += 1) {
      setUploadingIndex(index);
      try {
        const job = await uploadVideo(selectedFiles[index], processingMode, ocrLanguage, trim);
        if (!firstJob) {
          firstJob = job;
        }
      } catch (submissionError) {
        failed.add(index);
        firstError =
          firstError ??
          (submissionError instanceof Error ? submissionError.message : "Upload failed.");
      }
    }
    setUploadingIndex(null);
    setIsSubmitting(false);

    const succeeded = selectedFiles.length - failed.size;
    if (succeeded > 0) {
      toast(
        succeeded === 1
          ? "Session created — processing started."
          : `${succeeded} sessions created — processing started.`,
        "success",
      );
    }
    if (failed.size > 0) {
      // Keep only the failed files so resubmitting retries them without
      // duplicating the sessions that already succeeded.
      const failedFiles = selectedFiles.filter((_, index) => failed.has(index));
      setSelectedFiles(failedFiles);
      setFailedIndexes(new Set(failedFiles.map((_, index) => index)));
      setError(
        `${failed.size} of ${selectedFiles.length} upload(s) failed` +
          (firstError ? `: ${firstError}` : ".") +
          " Submit again to retry the remaining files.",
      );
    } else {
      setSelectedFiles([]);
      setFailedIndexes(new Set());
      setTrimStartText("");
      setTrimEndText("");
    }
    if (inputRef.current) {
      inputRef.current.value = "";
    }
    if (firstJob) {
      onJobCreated(firstJob);
    }
  }

  const canSubmit =
    !isSubmitting &&
    (sourceKind === "file" ? selectedFiles.length > 0 : videoUrl.trim().length > 0);

  return (
    <SectionCard
      title="New session"
      subtitle={
        compact
          ? "Upload a recording to start a new session."
          : "Upload a recording or paste a video link."
      }
    >
      <form className="upload-form" onSubmit={handleSubmit}>
        <div className="mode-selector" role="tablist" aria-label="Video source">
          <button
            className={`mode-pill ${sourceKind === "file" ? "active" : ""}`}
            onClick={() => setSourceKind("file")}
            role="tab"
            aria-selected={sourceKind === "file"}
            type="button"
          >
            <Upload size={14} aria-hidden="true" />
            Upload file
          </button>
          <button
            className={`mode-pill ${sourceKind === "url" ? "active" : ""}`}
            onClick={() => setSourceKind("url")}
            role="tab"
            aria-selected={sourceKind === "url"}
            type="button"
          >
            <Link2 size={14} aria-hidden="true" />
            From URL
          </button>
        </div>

        {sourceKind === "file" ? (
          <>
            <input
              accept="video/*"
              className="upload-input-hidden"
              multiple
              name="file"
              ref={inputRef}
              type="file"
              onChange={(event) => addFiles(event.target.files)}
            />

            <div
              className={`upload-dropzone ${isDragging ? "upload-dropzone--dragging" : ""} ${isSubmitting ? "upload-dropzone--loading" : ""}`}
              onDragEnter={(event) => {
                event.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={(event) => {
                event.preventDefault();
                setIsDragging(false);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                setIsDragging(false);
                addFiles(event.dataTransfer.files);
              }}
              onClick={openFilePicker}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  openFilePicker();
                }
              }}
              role="button"
              tabIndex={0}
            >
              {isSubmitting ? (
                <div className="upload-dropzone__overlay">
                  <Loader2 size={28} className="spin" aria-hidden="true" />
                  <strong>Creating session…</strong>
                </div>
              ) : null}
              <Upload size={24} className="upload-dropzone__lucide" aria-hidden="true" />
              <strong>Drop videos or click to browse</strong>
              <span className="upload-dropzone__hint">
                MP4, MOV, WebM — up to {MAX_BATCH_FILES} at once
              </span>
            </div>

            {selectedFiles.length > 0 ? (
              <div className="file-chip-list">
                {selectedFiles.map((file, index) => (
                  <div
                    className={`file-chip ${
                      failedIndexes.has(index) ? "file-chip--failed" : ""
                    }`}
                    key={`${file.name}-${file.size}`}
                  >
                    {uploadingIndex === index ? (
                      <Loader2 size={13} className="spin" aria-hidden="true" />
                    ) : null}
                    <span className="file-chip__name" title={file.name}>
                      {file.name}
                    </span>
                    <span className="file-chip__size">
                      {(file.size / 1024 / 1024).toFixed(1)} MB
                    </span>
                    {failedIndexes.has(index) ? (
                      <span className="file-chip__status">failed</span>
                    ) : null}
                    <button
                      className="file-chip__remove"
                      disabled={isSubmitting}
                      onClick={() => removeFile(index)}
                      type="button"
                      aria-label={`Remove ${file.name}`}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <label className="upload-url-field">
            <span>Video link</span>
            <input
              placeholder="https://www.youtube.com/watch?v=…"
              type="url"
              value={videoUrl}
              onChange={(event) => {
                setVideoUrl(event.target.value);
                setError(null);
              }}
            />
            <span className="upload-dropzone__hint">
              YouTube, most video sites, or a direct video file link.
            </span>
          </label>
        )}

        <div className="upload-options">
          <label className="upload-option">
            <span>Source type</span>
            <div className="mode-selector" role="tablist" aria-label="Processing mode">
              <button
                className={`mode-pill ${processingMode === "screen" ? "active" : ""}`}
                onClick={() => setProcessingMode("screen")}
                role="tab"
                aria-selected={processingMode === "screen"}
                type="button"
              >
                Screen recording
              </button>
              <button
                className={`mode-pill ${processingMode === "camera" ? "active" : ""}`}
                onClick={() => setProcessingMode("camera")}
                role="tab"
                aria-selected={processingMode === "camera"}
                type="button"
              >
                Camera
              </button>
            </div>
          </label>
          <label className="upload-option">
            <span>Document language</span>
            <select
              className="select-input"
              value={ocrLanguage}
              onChange={(event) => chooseLanguage(event.target.value)}
            >
              {languages.map((code) => (
                <option key={code} value={code}>
                  {languageLabel(code)}
                </option>
              ))}
            </select>
          </label>
          <label className="upload-option">
            <span>Time range (optional)</span>
            <div className="trim-inputs">
              <input
                aria-label="Start time"
                className="trim-inputs__field"
                inputMode="numeric"
                placeholder="0:00"
                type="text"
                value={trimStartText}
                onChange={(event) => {
                  setTrimStartText(event.target.value);
                  setError(null);
                }}
              />
              <span className="trim-inputs__separator">–</span>
              <input
                aria-label="End time"
                className="trim-inputs__field"
                inputMode="numeric"
                placeholder="end"
                type="text"
                value={trimEndText}
                onChange={(event) => {
                  setTrimEndText(event.target.value);
                  setError(null);
                }}
              />
            </div>
          </label>
        </div>

        {error ? (
          <div className="status-banner status-banner--error">
            <strong>Could not start</strong>
            <span>{error}</span>
          </div>
        ) : null}

        <div className="upload-actions">
          <button className="primary-button" disabled={!canSubmit} type="submit">
            {isSubmitting ? (
              <>
                <Loader2 size={16} className="spin" aria-hidden="true" />
                {sourceKind === "file" && selectedFiles.length > 1 && uploadingIndex !== null
                  ? `Uploading ${uploadingIndex + 1} of ${selectedFiles.length}…`
                  : "Creating session…"}
              </>
            ) : sourceKind === "file" && selectedFiles.length > 1 ? (
              `Start ${selectedFiles.length} reconstructions`
            ) : (
              "Start reconstruction"
            )}
          </button>
        </div>
      </form>
    </SectionCard>
  );
}
