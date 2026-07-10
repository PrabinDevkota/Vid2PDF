import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppSidebar } from "./components/AppSidebar";
import { ToastProvider } from "./components/Toast";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { ReviewPage } from "./features/review/ReviewPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { JobsProvider } from "./hooks/useJobs";

function AppRoutes() {
  return (
    <JobsProvider>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/review/:jobId" element={<ReviewPage />} />
        <Route path="/review" element={<Navigate to="/" replace />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </JobsProvider>
  );
}

function AppShell() {
  return (
    <div className="app-shell">
      <AppSidebar />
      <div className="app-main">
        <AppRoutes />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppShell />
      </ToastProvider>
    </BrowserRouter>
  );
}
