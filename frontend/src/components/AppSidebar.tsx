import { NavLink } from "react-router-dom";
import { LayoutDashboard, Settings } from "lucide-react";

export function AppSidebar() {
  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <div className="brand-mark">VP</div>
        <div>
          <strong>Vid2PDF</strong>
          <span>Document reconstruction</span>
        </div>
      </div>
      <nav className="sidebar-nav" aria-label="Primary navigation">
        <NavLink className="nav-item" to="/" end>
          <LayoutDashboard size={18} aria-hidden="true" />
          <span className="nav-item__label">Dashboard</span>
        </NavLink>
        <NavLink className="nav-item" to="/settings">
          <Settings size={18} aria-hidden="true" />
          <span className="nav-item__label">Settings</span>
        </NavLink>
      </nav>
      <div className="sidebar-status">
        <span className="live-dot" aria-hidden="true" />
        <div>
          <strong>Live processing</strong>
          <p>Sessions sync with the backend. Edits, reorder, and exports persist automatically.</p>
        </div>
      </div>
    </aside>
  );
}
