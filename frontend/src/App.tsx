import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import { UploadPanel } from './features/jobs/UploadPanel';
import { JobOverview } from './features/jobs/JobOverview';
import { PageReviewBoard } from './features/pages/PageReviewBoard';
import { fetchJob, fetchJobs } from './lib/api';
import type { ProcessingJob } from './types';

function Dashboard() {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchJobs().then(setJobs).finally(() => setLoading(false));
  }, []);

  return (
    <div className="page">
      <h1>Dashboard</h1>
      <p className="subtitle">Welcome to Vid2PDF • Modern document reconstruction studio</p>
      <div className="stats-grid">
        <div className="stat-card"><strong>{jobs.length}</strong><span>Sessions</span></div>
        <div className="stat-card"><strong>{jobs.filter(j => j.status === 'ready').length}</strong><span>Ready for Export</span></div>
      </div>
      <div className="quick-actions">
        <NavLink to="/upload" className="btn-primary">Start New Upload</NavLink>
        <NavLink to="/sessions" className="btn-secondary">View All Sessions</NavLink>
      </div>
    </div>
  );
}

function Sessions() {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const navigate = useNavigate();

  useEffect(() => { fetchJobs().then(setJobs); }, []);

  return (
    <div className="page">
      <h1>Sessions</h1>
      <div className="session-list">
        {jobs.length === 0 && <p>No sessions yet. Upload a video to begin.</p>}
        {jobs.map(job => (
          <div key={job.id} className="session-card" onClick={() => navigate(`/review/${job.id}`)}>
            <div>{job.filename}</div>
            <div className={`status ${job.status}`}>{job.status}</div>
            <div>{job.pages.length} pages</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function UploadPage() {
  return (
    <div className="page">
      <h1>Upload Video</h1>
      <UploadPanel />
    </div>
  );
}

function ReviewPage() {
  return (
    <div className="page">
      <PageReviewBoard />
    </div>
  );
}

function AppShell() {
  return (
    <div className="app-shell modern">
      <aside className="sidebar sleek">
        <div className="brand">Vid2PDF</div>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/upload">Upload</NavLink>
          <NavLink to="/sessions">Sessions</NavLink>
          <NavLink to="/review">Review</NavLink>
        </nav>
        <div className="footer">Modern • Sleek • Functional</div>
      </aside>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/review/:jobId" element={<ReviewPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}
