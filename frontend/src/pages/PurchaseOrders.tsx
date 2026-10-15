import { useCallback, useEffect, useState } from "react";

import { useCurrentRole } from "../context/AuthContext";
import { ApiError } from "../services/api";
import {
  createPurchaseOrder,
  deletePurchaseOrder,
  importPurchaseOrders,
  listPurchaseOrders,
  type PurchaseOrderPayload,
} from "../services/purchaseOrders";
import type { PurchaseOrder, POStatus } from "../types/api";

function formatAmount(amount: string | null, currency: string | null): string {
  if (amount === null) return "—";
  return currency ? `${amount} ${currency}` : amount;
}

const EMPTY_FORM = {
  po_number: "",
  supplier_name: "",
  currency: "USD",
  total_amount: "",
  status: "open" as POStatus,
  description: "",
  quantity: "",
  unit_price: "",
};

export default function PurchaseOrders() {
  const role = useCurrentRole();
  const canWrite = role === "admin" || role === "finance";

  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<"" | POStatus>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listPurchaseOrders({
        status: statusFilter || null,
        limit: 200,
      });
      setOrders(result.items);
      setTotal(result.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load purchase orders");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setField = (key: keyof typeof EMPTY_FORM, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (form.po_number.trim() === "") return;
    setSaving(true);
    setError(null);
    setNotice(null);
    const payload: PurchaseOrderPayload = {
      po_number: form.po_number.trim(),
      supplier_name: form.supplier_name.trim() || null,
      currency: form.currency.trim().toUpperCase(),
      total_amount: form.total_amount.trim() || null,
      status: form.status,
    };
    const hasLine =
      form.description.trim() !== "" ||
      form.quantity.trim() !== "" ||
      form.unit_price.trim() !== "";
    if (hasLine) {
      payload.line_items = [
        {
          line_number: 1,
          description: form.description.trim() || null,
          quantity: form.quantity.trim() || null,
          unit_price: form.unit_price.trim() || null,
        },
      ];
    }
    try {
      await createPurchaseOrder(payload);
      setForm(EMPTY_FORM);
      setNotice(`Purchase order ${payload.po_number} created.`);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create purchase order");
    } finally {
      setSaving(false);
    }
  };

  const handleImport = async () => {
    if (!importFile) return;
    setImporting(true);
    setError(null);
    setNotice(null);
    try {
      const result = await importPurchaseOrders(importFile);
      setImportFile(null);
      const skipped =
        result.skipped.length > 0 ? ` Skipped existing: ${result.skipped.join(", ")}.` : "";
      const errorText =
        result.errors.length > 0
          ? ` ${result.errors.length} row(s) failed to import.`
          : "";
      setNotice(
        `Imported ${result.created} purchase order(s).${skipped}${errorText}`
      );
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  const handleDelete = async (po: PurchaseOrder) => {
    setError(null);
    setNotice(null);
    try {
      await deletePurchaseOrder(po.id);
      setNotice(`Deleted ${po.po_number}.`);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to delete purchase order");
    }
  };

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <h2>Purchase orders</h2>
          <select
            aria-label="Status filter"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as "" | POStatus)}
          >
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>

        {error && <div className="alert alert-error">{error}</div>}
        {notice && <div className="alert">{notice}</div>}
        {loading ? (
          <div className="page-message">Loading…</div>
        ) : orders.length === 0 ? (
          <div className="page-message">No purchase orders yet.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>PO number</th>
                <th>Lines</th>
                <th>Total</th>
                <th>Status</th>
                {canWrite && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id}>
                  <td>{order.po_number}</td>
                  <td>{order.line_items.length}</td>
                  <td>{formatAmount(order.total_amount, order.currency)}</td>
                  <td>
                    <span className={`badge badge-${order.status}`}>{order.status}</span>
                  </td>
                  {canWrite && (
                    <td className="actions">
                      <button
                        type="button"
                        className="button button-small button-ghost"
                        onClick={() => void handleDelete(order)}
                      >
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">{total} total</p>
      </div>

      {canWrite && (
        <div className="card">
          <div className="card-header">
            <h2>Add purchase order</h2>
          </div>
          <form onSubmit={(event) => void handleCreate(event)}>
            <div className="po-form-grid">
              <label>
                PO number
                <input
                  value={form.po_number}
                  onChange={(event) => setField("po_number", event.target.value)}
                  required
                />
              </label>
              <label>
                Supplier
                <input
                  value={form.supplier_name}
                  onChange={(event) => setField("supplier_name", event.target.value)}
                />
              </label>
              <label>
                Currency
                <input
                  value={form.currency}
                  onChange={(event) => setField("currency", event.target.value)}
                  maxLength={3}
                />
              </label>
              <label>
                Total amount
                <input
                  value={form.total_amount}
                  onChange={(event) => setField("total_amount", event.target.value)}
                  inputMode="decimal"
                />
              </label>
              <label>
                Status
                <select
                  value={form.status}
                  onChange={(event) => setField("status", event.target.value)}
                >
                  <option value="open">Open</option>
                  <option value="closed">Closed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </label>
              <label>
                Line description
                <input
                  value={form.description}
                  onChange={(event) => setField("description", event.target.value)}
                />
              </label>
              <label>
                Quantity
                <input
                  value={form.quantity}
                  onChange={(event) => setField("quantity", event.target.value)}
                  inputMode="decimal"
                />
              </label>
              <label>
                Unit price
                <input
                  value={form.unit_price}
                  onChange={(event) => setField("unit_price", event.target.value)}
                  inputMode="decimal"
                />
              </label>
            </div>
            <button type="submit" className="button" disabled={saving}>
              {saving ? "Saving…" : "Create purchase order"}
            </button>
          </form>
        </div>
      )}

      {canWrite && (
        <div className="card">
          <div className="card-header">
            <h2>Import from CSV</h2>
          </div>
          <p className="hint">
            One row per line item. Columns: po_number, supplier_name, currency,
            total_amount, status, line_number, description, quantity, unit_price,
            line_total. Rows sharing a po_number become one purchase order.
          </p>
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label="CSV file"
            onChange={(event) => setImportFile(event.target.files?.[0] ?? null)}
          />
          <div className="dialog-actions">
            <button
              type="button"
              className="button"
              disabled={!importFile || importing}
              onClick={() => void handleImport()}
            >
              {importing ? "Importing…" : "Import CSV"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
