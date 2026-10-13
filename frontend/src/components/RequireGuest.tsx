import { Navigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function RequireGuest({ children }: { children: JSX.Element }) {
  const { token, loading } = useAuth();
  if (loading) {
    return <div className="page-message">Checking session…</div>;
  }
  if (token) {
    return <Navigate to="/documents" replace />;
  }
  return children;
}