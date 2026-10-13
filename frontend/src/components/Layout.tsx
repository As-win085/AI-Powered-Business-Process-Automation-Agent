import { Link, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import TenantSelect from "./TenantSelect";

export default function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/documents" className="brand">
          AI Business Automation
        </Link>
        <nav className="topbar-nav">
          <Link to="/documents">Documents</Link>
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