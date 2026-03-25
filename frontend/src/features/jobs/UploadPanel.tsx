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
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

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
      setSelectedFile(null);
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
        <div className="mode-selector">
          <button
            className={`mode-pill ${processingMode === "screen" ? "active" : ""}`}
            onClick={() => setProcessingMode("screen")}
            type="button"
          >
            Screen recording
          </button>
          <button
            className={`mode-pill ${processingMode === "camera" ? "active" : ""}`}
            onClick={() => setProcessingMode("camera")}
            type="button"
          >
            Camera / physical pages
          </button>
        </div>
        <label className="upload-dropzone">
          <span className="upload-dropzone__eyebrow">Video input</span>
          <strong>Choose one document-viewing recording</strong>
          <p>
            {processingMode === "camera"
              ? "Best for handheld recordings of books, reports, or worksheets with clear pauses after each page turn."
              : "Best for full-screen page viewing with clear pauses between page changes."}
          </p>
          <input
            accept="video/*"
            name="file"
            ref={inputRef}
            type="file"
            onChange={(event) =>
              setSelectedFile(event.target.files?.[0] ?? null)
            }
          />
        </label>
        <div className="upload-notes">
          <span>One source video</span>
          <span>Page segments detected</span>
          <span>PDF export ready</span>
        </div>
        {selectedFile ? (
          <div className="selected-file">
            <span className="selected-file__label">Selected file</span>
            <strong>{selectedFile.name}</strong>
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
              ? "Camera mode adds document-boundary detection, perspective correction, transition rejection, and occlusion penalties."
              : "Screen mode keeps the faster digital-document extraction path for page-by-page screen recordings."}
          </span>
        </div>
      </form>
    </SectionCard>
  );
}
