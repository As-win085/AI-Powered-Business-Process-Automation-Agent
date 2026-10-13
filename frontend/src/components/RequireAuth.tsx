import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function RequireAuth({ children }: { children: JSX.Element }) {
  const { token, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="page-message">Checking session…</div>;
  }
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return children;
}