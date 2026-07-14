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

type SourceKind = "file" | "url";

interface UploadPanelProps {
  onJobCreated: (job: ProcessingJob) => void;
  compact?: boolean;
}

export function UploadPanel({ onJobCreated, compact }: UploadPanelProps) {
  const { toast } = useToast();
  const [sourceKind, setSourceKind] = useState<SourceKind>("file");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState("");
  const [processingMode, setProcessingMode] = useState<ProcessingMode>("screen");
  const [ocrLanguage, setOcrLanguage] = useState("eng");
  const [languages, setLanguages] = useState<string[]>(["eng"]);
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

  function chooseFile(file: File | null) {
    setSelectedFile(file);
    if (file) {
      setError(null);
    }
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
    if (sourceKind === "file" && !selectedFile) {
      setError("Choose a video file to start processing.");
      return;
    }
    if (sourceKind === "url" && !/^https?:\/\/\S+$/i.test(videoUrl.trim())) {
      setError("Enter a valid http(s) video URL.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const job =
        sourceKind === "file"
          ? await uploadVideo(selectedFile!, processingMode, ocrLanguage)
          : await createJobFromUrl(videoUrl.trim(), processingMode, ocrLanguage);
      onJobCreated(job);
      toast(
        sourceKind === "file"
          ? "Session created — processing started."
          : "Session created — downloading the video.",
        "success",
      );
      chooseFile(null);
      setVideoUrl("");
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    } catch (submissionError) {
      const message =
        submissionError instanceof Error
          ? submissionError.message
          : "Upload failed.";
      setError(message);
      toast(message, "error");
    } finally {
      setIsSubmitting(false);
    }
  }

  const canSubmit =
    !isSubmitting && (sourceKind === "file" ? selectedFile !== null : videoUrl.trim().length > 0);

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
              name="file"
              ref={inputRef}
              type="file"
              onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
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
                chooseFile(event.dataTransfer.files[0] ?? null);
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
              <strong>Drop a video or click to browse</strong>
              <span className="upload-dropzone__hint">MP4, MOV, WebM</span>
            </div>

            {selectedFile ? (
              <div className="file-chip">
                <span className="file-chip__name" title={selectedFile.name}>
                  {selectedFile.name}
                </span>
                <span className="file-chip__size">
                  {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                </span>
                <button
                  className="file-chip__remove"
                  onClick={() => chooseFile(null)}
                  type="button"
                  aria-label="Remove file"
                >
                  <X size={14} />
                </button>
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
                Creating session…
              </>
            ) : (
              "Start reconstruction"
            )}
          </button>
        </div>
      </form>
    </SectionCard>
  );
}
