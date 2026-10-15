import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../services/api";
import { listAnomalies } from "../services/anomalies";
import type { AnomalyQueueItem } from "../types/api";

function formatAmount(amount: string | null, currency: string | null): string {
  if (amount === null) return "—";
  return currency ? `${amount} ${currency}` : amount;
}

function formatScore(score: number | null): string {
  return score === null ? "—" : score.toFixed(3);
}

export default function Anomalies() {
  const [items, setItems] = useState<AnomalyQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listAnomalies();
      setItems(result.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load anomalies");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <h2>Anomaly review queue</h2>
          <button
            type="button"
            className="button button-small button-ghost"
            onClick={() => void refresh()}
          >
            Refresh
          </button>
        </div>
        <p className="hint">
          Invoices flagged by the unsupervised model as unusual for their supplier.
          These are review recommendations only and never change an invoice's status.
        </p>

        {error && <div className="alert alert-error">{error}</div>}
        {loading ? (
          <div className="page-message">Loading…</div>
        ) : items.length === 0 ? (
          <div className="page-message">No flagged invoices.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Supplier</th>
                <th>Date</th>
                <th>Total</th>
                <th>Score</th>
                <th>Risk</th>
                <th>Reasons</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.invoice_id}>
                  <td>{item.invoice_number ?? item.invoice_id.slice(0, 8)}</td>
                  <td>{item.supplier_name ?? "—"}</td>
                  <td>{item.invoice_date ?? "—"}</td>
                  <td>{formatAmount(item.total_amount, item.currency)}</td>
                  <td>{formatScore(item.anomaly_score)}</td>
                  <td>
                    <span className={`badge badge-${item.risk_level ?? "low"}`}>
                      {item.risk_level ?? "low"}
                    </span>
                  </td>
                  <td>
                    <ul className="reason-list">
                      {item.reasons.map((reason) => (
                        <li key={reason.code}>{reason.message}</li>
                      ))}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">{items.length} flagged invoice(s)</p>
      </div>
    </div>
  );
}
