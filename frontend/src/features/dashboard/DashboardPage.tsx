import { useRef } from "react";
import { ArrowRight, Layers, Upload } from "lucide-react";
import { AppHeader } from "../../components/AppHeader";
import { SectionCard } from "../../components/SectionCard";
import { SessionsTable } from "../../components/SessionsTable";
import { UploadPanel } from "../jobs/UploadPanel";
import { useJobs } from "../../hooks/useJobs";

export function DashboardPage() {
  const uploadRef = useRef<HTMLDivElement>(null);
  const {
    jobs,
    activeJob,
    isLoadingJobs,
    loadError,
    readyCount,
    handleJobCreated,
    handleSelectJob,
  } = useJobs();

  const activePageCount =
    activeJob?.pages.filter((page) => !page.deleted).length ?? 0;

  function scrollToUpload() {
    uploadRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <main className="page-content">
      <section className="dashboard-hero">
        <div className="dashboard-hero__copy">
          <p className="section-eyebrow">Vid2PDF</p>
          <h1>Turn screen recordings into clean PDFs</h1>
          <p>
            Upload a document-viewing video, let the pipeline extract stable pages,
            then review and export a polished PDF.
          </p>
          <button className="primary-button" onClick={scrollToUpload} type="button">
            <Upload size={16} aria-hidden="true" />
            Upload a video
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
        <div className="dashboard-hero__visual" aria-hidden="true">
          <div className="hero-card">
            <Layers size={28} />
            <span>Upload → Process → Review → Export</span>
          </div>
        </div>
      </section>

      <AppHeader
        title="Overview"
        subtitle="Monitor sessions and start new reconstructions."
        stats={[
          { label: "Sessions", value: jobs.length },
          { label: "Ready", value: readyCount },
          { label: "Active pages", value: activePageCount },
        ]}
      />

      {loadError ? (
        <div className="status-banner status-banner--error workspace-alert">
          <strong>Backend unavailable</strong>
          <span>{loadError}</span>
        </div>
      ) : null}

      <div className="dashboard-layout">
        <div ref={uploadRef}>
          <UploadPanel onJobCreated={handleJobCreated} />
        </div>
        <SectionCard
          eyebrow="Sessions"
          title="Recent sessions"
          subtitle="Click a session to open the review workspace."
        >
          <SessionsTable
            activeJobId={activeJob?.id}
            isLoading={isLoadingJobs}
            jobs={jobs}
            limit={5}
            showViewAll
            onSelectJob={handleSelectJob}
          />
        </SectionCard>
      </div>
    </main>
  );
}
