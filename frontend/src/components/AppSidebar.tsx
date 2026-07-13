import { NavLink } from "react-router-dom";
import { LayoutDashboard, Settings } from "lucide-react";

export function AppSidebar() {
  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">
          V
        </div>
        <strong>Vid2PDF</strong>
      </div>
      <nav className="sidebar-nav" aria-label="Primary navigation">
        <NavLink className="nav-item" to="/" end>
          <LayoutDashboard size={17} aria-hidden="true" />
          <span className="nav-item__label">Sessions</span>
        </NavLink>
        <NavLink className="nav-item" to="/settings">
          <Settings size={17} aria-hidden="true" />
          <span className="nav-item__label">Settings</span>
        </NavLink>
      </nav>
    </aside>
  );
}
