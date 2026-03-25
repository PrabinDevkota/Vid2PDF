import { useRef, useState } from "react";
import type { ProcessingJob } from "../../types";
import { uploadVideo } from "../../lib/api";
import { SectionCard } from "../../components/SectionCard";

interface UploadPanelProps {
  onJobCreated: (job: ProcessingJob) => void;
}

export function UploadPanel({ onJobCreated }: UploadPanelProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
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
      const job = await uploadVideo(selectedFile);
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
      title="Upload a source recording"
      subtitle="Start with one screen recording of a document, report, ebook, or slide deck."
    >
      <form className="upload-form" onSubmit={handleSubmit}>
        <label className="upload-dropzone">
          <span className="upload-dropzone__eyebrow">Drag in a file or browse</span>
          <strong>Choose one document-viewing video</strong>
          <p>
            Best for full-screen page viewing with clear pauses between page
            changes.
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
          <span>One video in</span>
          <span>Stable pages detected</span>
          <span>Final PDF out</span>
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
            The backend now creates a real job record, tracks pipeline progress, and exposes extracted pages for review.
          </span>
        </div>
      </form>
    </SectionCard>
  );
}
