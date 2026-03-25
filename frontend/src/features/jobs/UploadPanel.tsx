import { useState } from "react";
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
      event.currentTarget.reset();
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
    <SectionCard eyebrow="Input" title="Upload a screen recording">
      <form className="upload-form" onSubmit={handleSubmit}>
        <label className="upload-dropzone">
          <span>Choose one document-viewing video</span>
          <input
            accept="video/*"
            name="file"
            type="file"
            onChange={(event) =>
              setSelectedFile(event.target.files?.[0] ?? null)
            }
          />
        </label>
        <p className="muted">
          Designed for recordings of digital pages, reports, ebooks, and slide
          decks viewed page by page.
        </p>
        {selectedFile ? (
          <p className="selected-file">Selected: {selectedFile.name}</p>
        ) : null}
        {error ? <p className="error-text">{error}</p> : null}
        <button className="primary-button" disabled={isSubmitting} type="submit">
          {isSubmitting ? "Processing..." : "Start reconstruction"}
        </button>
      </form>
    </SectionCard>
  );
}
