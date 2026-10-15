import { Link, Outlet } from "react-router-dom";

import { useAuth, useCurrentRole } from "../context/AuthContext";
import TenantSelect from "./TenantSelect";

export default function Layout() {
  const { user, logout } = useAuth();
  const role = useCurrentRole();
  const canApprove = role === "admin" || role === "approver";

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/documents" className="brand">
          AI Business Automation
        </Link>
        <nav className="topbar-nav">
          <Link to="/documents">Documents</Link>
          {canApprove && <Link to="/approvals">Approvals</Link>}
        </nav>
        <div className="topbar-right">
          <TenantSelect />
          {user && <span className="user-chip">{user.email}</span>}
          <button type="button" className="button button-ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}