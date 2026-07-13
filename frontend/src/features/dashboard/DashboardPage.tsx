import { AppHeader } from "../../components/AppHeader";
import { SectionCard } from "../../components/SectionCard";
import { SessionsTable } from "../../components/SessionsTable";
import { UploadPanel } from "../jobs/UploadPanel";
import { useJobs } from "../../hooks/useJobs";

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

  return (
    <main className="page-content">
      <AppHeader
        title="Sessions"
        subtitle="Upload a document-viewing video and export it as a clean PDF."
      />

      {loadError ? (
        <div className="status-banner status-banner--error">
          <strong>Backend unavailable</strong>
          <span>{loadError}</span>
        </div>
      ) : null}

      <div className="dashboard-layout">
        <UploadPanel onJobCreated={handleJobCreated} />
        <SectionCard
          title="Recent sessions"
          subtitle="Open a session to review pages and export."
        >
          <SessionsTable
            activeJobId={activeJob?.id}
            isLoading={isLoadingJobs}
            jobs={jobs}
            limit={6}
            showViewAll
            onSelectJob={handleSelectJob}
            onDeleteJob={handleJobDeleted}
          />
        </SectionCard>
      </div>
    </main>
  );
}
