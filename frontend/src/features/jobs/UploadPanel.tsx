import { useRef, useState } from "react";
import type { ProcessingJob, ProcessingMode } from "../../types";
import { uploadVideo } from "../../lib/api";
import { SectionCard } from "../../components/SectionCard";

interface UploadPanelProps {
  onJobCreated: (job: ProcessingJob) => void;
}

export function UploadPanel({ onJobCreated }: UploadPanelProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [processingMode, setProcessingMode] = useState<ProcessingMode>("screen");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  function chooseFile(file: File | null) {
    setSelectedFile(file);
    if (file) {
      setError(null);
    }
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
      chooseFile(null);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Upload failed.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <SectionCard
      eyebrow="Input"
      title="Create a reconstruction session"
      subtitle="Upload one recording, choose the source type, and let the pipeline prepare reviewable pages."
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
        <label
          className={`upload-dropzone ${isDragging ? "upload-dropzone--dragging" : ""}`}
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
        >
          <span className="upload-dropzone__icon" aria-hidden="true" />
          <span className="upload-dropzone__eyebrow">Video input</span>
          <strong>Drop a video here or browse</strong>
          <p>
            {processingMode === "camera"
              ? "Best for physical pages with perspective correction."
              : "Best for clean digital page recordings."}
          </p>
          <input
            accept="video/*"
            name="file"
            ref={inputRef}
            type="file"
            onChange={(event) =>
              chooseFile(event.target.files?.[0] ?? null)
            }
          />
        </label>
        <div className="upload-notes">
          <span>Accepts video files</span>
          <span>One source per session</span>
          <span>Backend artifacts preserved</span>
        </div>
        {selectedFile ? (
          <div className="selected-file">
            <span className="selected-file__label">Selected file</span>
            <strong title={selectedFile.name}>{selectedFile.name}</strong>
            <span>{(selectedFile.size / 1024 / 1024).toFixed(1)} MB</span>
          </div>
        ) : null}
        {error ? (
          <div className="status-banner status-banner--error">
            <strong>Upload could not start.</strong>
            <span>{error}</span>
          </div>
        ) : null}
        <div className="upload-actions">
          <button className="primary-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Preparing session..." : "Start reconstruction"}
          </button>
          <span className="upload-actions__hint">
            {processingMode === "camera"
              ? "Camera mode is tuned for handheld recordings with page boundaries and occlusion handling."
              : "Screen mode keeps the faster extraction path for page-by-page screen recordings."}
          </span>
        </div>
      </form>
    </SectionCard>
  );
}
