import { useEffect, useRef, useState } from "react";
import { Loader2, Upload, X } from "lucide-react";
import type { ProcessingJob, ProcessingMode } from "../../types";
import { uploadVideo } from "../../lib/api";
import { SectionCard } from "../../components/SectionCard";
import { useToast } from "../../components/Toast";

const DEFAULT_MODE_KEY = "vid2pdf-default-mode";

interface UploadPanelProps {
  onJobCreated: (job: ProcessingJob) => void;
  compact?: boolean;
}

export function UploadPanel({ onJobCreated, compact }: UploadPanelProps) {
  const { toast } = useToast();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [processingMode, setProcessingMode] = useState<ProcessingMode>("screen");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(DEFAULT_MODE_KEY);
    if (stored === "screen" || stored === "camera") {
      setProcessingMode(stored);
    }
  }, []);

  function chooseFile(file: File | null) {
    setSelectedFile(file);
    if (file) {
      setError(null);
    }
  }

  function openFilePicker() {
    inputRef.current?.click();
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setError("Choose a screen recording to start processing.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const job = await uploadVideo(selectedFile, processingMode);
      onJobCreated(job);
      toast("Session created — processing started.", "success");
      chooseFile(null);
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

  return (
    <SectionCard
      eyebrow="Input"
      title={compact ? "New session" : "Create a reconstruction session"}
      subtitle={
        compact
          ? "Upload a recording to start a new session."
          : "Upload one recording, choose the source type, and let the pipeline prepare reviewable pages."
      }
    >
      <form className="upload-form" onSubmit={handleSubmit}>
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
            Camera / physical pages
          </button>
        </div>

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
          <Upload size={28} className="upload-dropzone__lucide" aria-hidden="true" />
          <span className="upload-dropzone__eyebrow">Video input</span>
          <strong>Drop a video here or click to browse</strong>
          <p>
            {processingMode === "camera"
              ? "Best for physical pages with perspective correction."
              : "Best for clean digital page recordings."}
          </p>
          <span className="upload-dropzone__hint">MP4, MOV, WebM · One source per session</span>
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

        {error ? (
          <div className="status-banner status-banner--error">
            <strong>Upload could not start.</strong>
            <span>{error}</span>
          </div>
        ) : null}

        <div className="upload-actions">
          <button
            className="primary-button"
            disabled={isSubmitting || !selectedFile}
            type="submit"
          >
            {isSubmitting ? (
              <>
                <Loader2 size={16} className="spin" aria-hidden="true" />
                Creating session…
              </>
            ) : (
              "Start reconstruction"
            )}
          </button>
          {!compact ? (
            <span className="upload-actions__hint">
              {processingMode === "camera"
                ? "Camera mode handles handheld recordings with page boundaries."
                : "Screen mode is optimized for page-by-page digital recordings."}
            </span>
          ) : null}
        </div>
      </form>
    </SectionCard>
  );
}
