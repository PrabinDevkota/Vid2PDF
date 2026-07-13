import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AppSidebar } from "./components/AppSidebar";
import { ToastProvider } from "./components/Toast";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { LandingPage } from "./features/landing/LandingPage";
import { ReviewPage } from "./features/review/ReviewPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { JobsProvider } from "./hooks/useJobs";

function AppLayout() {
  return (
    <div className="app-shell">
      <AppSidebar />
      <div className="app-main">
        <Outlet />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <JobsProvider>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route element={<AppLayout />}>
              <Route path="/app" element={<DashboardPage />} />
              <Route path="/review/:jobId" element={<ReviewPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
            <Route path="/review" element={<Navigate to="/app" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </JobsProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
