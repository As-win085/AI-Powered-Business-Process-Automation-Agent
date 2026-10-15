import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import RequireGuest from "./components/RequireGuest";
import Approvals from "./pages/Approvals";
import Anomalies from "./pages/Anomalies";
import DocumentViewer from "./pages/DocumentViewer";
import Documents from "./pages/Documents";
import Login from "./pages/Login";
import PurchaseOrders from "./pages/PurchaseOrders";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={
            <RequireGuest>
              <Login />
            </RequireGuest>
          }
        />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<Navigate to="/documents" replace />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/documents/:id" element={<DocumentViewer />} />
          <Route path="/purchase-orders" element={<PurchaseOrders />} />
          <Route path="/anomalies" element={<Anomalies />} />
          <Route path="/approvals" element={<Approvals />} />
        </Route>
        <Route path="*" element={<Navigate to="/documents" replace />} />
      </Routes>
    </BrowserRouter>
  );
}