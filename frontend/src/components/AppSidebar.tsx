import { NavLink } from "react-router-dom";
import { LayoutDashboard, Settings } from "lucide-react";
import { ThemeToggle } from "./ThemeToggle";

export function AppSidebar() {
  return (
    <aside className="sidebar">
      <NavLink className="brand-lockup" to="/" title="Vid2PDF home">
        <div className="brand-mark" aria-hidden="true">
          V
        </div>
        <strong>Vid2PDF</strong>
      </NavLink>
      <nav className="sidebar-nav" aria-label="Primary navigation">
        <NavLink className="nav-item" to="/app" end>
          <LayoutDashboard size={17} aria-hidden="true" />
          <span className="nav-item__label">Sessions</span>
        </NavLink>
        <NavLink className="nav-item" to="/settings">
          <Settings size={17} aria-hidden="true" />
          <span className="nav-item__label">Settings</span>
        </NavLink>
      </nav>
      <div className="sidebar-footer">
        <ThemeToggle showLabel />
      </div>
    </aside>
  );
}
