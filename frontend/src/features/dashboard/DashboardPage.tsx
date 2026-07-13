import { AppHeader } from "../../components/AppHeader";
import { SectionCard } from "../../components/SectionCard";
import { SessionsTable } from "../../components/SessionsTable";
import { UploadPanel } from "../jobs/UploadPanel";
import { useJobs } from "../../hooks/useJobs";

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
