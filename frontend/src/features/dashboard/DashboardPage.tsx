import { useState } from "react";
import { Download, Layers, Loader2 } from "lucide-react";
import { AppHeader } from "../../components/AppHeader";
import { SectionCard } from "../../components/SectionCard";
import { SessionsTable } from "../../components/SessionsTable";
import { useToast } from "../../components/Toast";
import { UploadPanel } from "../jobs/UploadPanel";
import { useJobs } from "../../hooks/useJobs";
import { exportMergedPdf, resolveArtifactUrl, type MergedExportResult } from "../../lib/api";
import type { ProcessingJob } from "../../types";

const RECORDING_TIPS = [
  {
    title: "Pause on every page",
    body: "Hold each page steady for at least a second so the pipeline can find a sharp frame.",
  },
  {
    title: "Scroll page by page",
    body: "Full page turns separate cleanly; slow continuous scrolling blurs the boundaries between pages.",
  },
  {
    title: "Record at full quality",
    body: "Higher resolution means sharper exports and far better OCR text. Avoid re-compressed videos.",
  },
  {
    title: "Recover missed pages",
    body: "Anything the pipeline skips can be pulled back from the Source video tab in review.",
  },
];

function MergeSessionsCard({ jobs }: { jobs: ProcessingJob[] }) {
  const { toast } = useToast();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isMerging, setIsMerging] = useState(false);
  const [result, setResult] = useState<MergedExportResult | null>(null);

  const mergeableJobs = jobs.filter(
    (job) => job.status === "ready" && job.pages.some((page) => !page.deleted),
  );
  if (mergeableJobs.length < 2) {
    return null;
  }

  function toggle(jobId: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
    setResult(null);
  }

  async function handleMerge() {
    // Keep dashboard order so the combined document reads top to bottom.
    const orderedIds = mergeableJobs
      .filter((job) => selectedIds.has(job.id))
      .map((job) => job.id);
    if (orderedIds.length < 2) {
      return;
    }
    setIsMerging(true);
    setResult(null);
    try {
      const merged = await exportMergedPdf(orderedIds);
      setResult(merged);
      toast(
        `Combined ${merged.jobCount} sessions into one ${merged.pageCount}-page PDF.`,
        "success",
      );
    } catch (error) {
      toast(error instanceof Error ? error.message : "Failed to build the combined PDF.", "error");
    } finally {
      setIsMerging(false);
    }
  }

  const downloadUrl = result ? resolveArtifactUrl(result.downloadUrl) : null;

  return (
    <SectionCard
      title="Combine sessions"
      subtitle="Pick two or more finished sessions and export them as a single PDF."
    >
      <div className="merge-card">
        <div className="merge-card__list">
          {mergeableJobs.map((job) => (
            <label className="merge-card__item" key={job.id}>
              <input
                checked={selectedIds.has(job.id)}
                disabled={isMerging}
                type="checkbox"
                onChange={() => toggle(job.id)}
              />
              <span className="merge-card__name" title={job.filename}>
                {job.filename}
              </span>
              <span className="muted">
                {job.pages.filter((page) => !page.deleted).length} pages
              </span>
            </label>
          ))}
        </div>
        <div className="review-toolbar">
          <button
            className="primary-button"
            disabled={isMerging || selectedIds.size < 2}
            onClick={() => void handleMerge()}
            type="button"
          >
            {isMerging ? (
              <Loader2 size={15} className="spin" aria-hidden="true" />
            ) : (
              <Layers size={15} aria-hidden="true" />
            )}
            Build combined PDF
          </button>
          {downloadUrl ? (
            <a className="secondary-button" href={downloadUrl} target="_blank" rel="noreferrer">
              <Download size={15} aria-hidden="true" />
              Download ({result?.pageCount} pages)
            </a>
          ) : null}
        </div>
      </div>
    </SectionCard>
  );
}

export function DashboardPage() {
  const {
    jobs,
    activeJob,
    isLoadingJobs,
    loadError,
    handleJobCreated,
    handleJobDeleted,
    handleSelectJob,
  } = useJobs();

  const pagesExtracted = jobs.reduce(
    (total, job) => total + job.pages.filter((page) => !page.deleted).length,
    0,
  );
  const pdfsExported = jobs.reduce(
    (total, job) =>
      total +
      (job.export.status === "ready" ? 1 : 0) +
      (job.textExport?.status === "ready" ? 1 : 0),
    0,
  );

  return (
    <main className="page-content">
      <AppHeader
        title="Sessions"
        subtitle="Upload a document-viewing video and export it as a clean PDF."
        stats={[
          { label: "Sessions", value: jobs.length },
          { label: "Pages extracted", value: pagesExtracted },
          { label: "PDFs exported", value: pdfsExported },
        ]}
      />

      {loadError ? (
        <div className="status-banner status-banner--error">
          <strong>Backend unavailable</strong>
          <span>{loadError}</span>
        </div>
      ) : null}

      <div className="dashboard-layout">
        <div className="dashboard-column">
          <UploadPanel onJobCreated={handleJobCreated} />
          <SectionCard
            title="Get the best results"
            subtitle="Small recording habits that make a big difference."
          >
            <dl className="tips-list">
              {RECORDING_TIPS.map((tip) => (
                <div className="tips-list__item" key={tip.title}>
                  <dt>{tip.title}</dt>
                  <dd>{tip.body}</dd>
                </div>
              ))}
            </dl>
          </SectionCard>
        </div>
        <div className="dashboard-column">
          <SectionCard
            title="Recent sessions"
            subtitle="Open a session to review pages and export."
          >
            <SessionsTable
              activeJobId={activeJob?.id}
              isLoading={isLoadingJobs}
              jobs={jobs}
              limit={8}
              showViewAll
              onSelectJob={handleSelectJob}
              onDeleteJob={handleJobDeleted}
            />
          </SectionCard>
          <MergeSessionsCard jobs={jobs} />
          <SectionCard
            title="What you get"
            subtitle="Every session can produce two artifacts."
          >
            <div className="artifact-cards">
              <div className="artifact-card">
                <strong>Image PDF</strong>
                <p>
                  Pixel-faithful pages exactly as reviewed — cropped, rotated, and
                  annotated.
                </p>
              </div>
              <div className="artifact-card">
                <strong>Text PDF + LaTeX</strong>
                <p>
                  OCR text typeset with Tectonic into a searchable document, with the
                  .tex source available too.
                </p>
              </div>
            </div>
          </SectionCard>
        </div>
      </div>
    </main>
  );
}
