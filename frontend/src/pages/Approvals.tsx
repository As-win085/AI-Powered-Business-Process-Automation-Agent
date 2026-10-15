import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../services/api";
import { listApprovals, submitDecision, type Decision } from "../services/approvals";
import type { Approval } from "../types/api";

type Scope = "pending" | "decided" | "all";

function formatAmount(amount: string | null, currency: string | null): string {
  if (amount === null) return "—";
  return currency ? `${amount} ${currency}` : amount;
}

export default function Approvals() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [total, setTotal] = useState(0);
  const [scope, setScope] = useState<Scope>("pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [active, setActive] = useState<Approval | null>(null);
  const [decision, setDecision] = useState<Decision>("approved");
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listApprovals({ scope, limit: 100 });
      setApprovals(result.items);
      setTotal(result.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openDialog = (approval: Approval) => {
    setActive(approval);
    setDecision("approved");
    setComment("");
    setDialogError(null);
  };

  const closeDialog = () => {
    setActive(null);
    setDialogError(null);
  };

  const requiresComment = decision === "rejected" || decision === "correction_requested";

  const handleSubmit = async () => {
    if (!active) return;
    if (requiresComment && comment.trim() === "") {
      setDialogError("A comment is required when rejecting or requesting a correction.");
      return;
    }
    setSubmitting(true);
    setDialogError(null);
    try {
      await submitDecision(active.id, decision, comment);
      closeDialog();
      await refresh();
    } catch (err) {
      setDialogError(err instanceof ApiError ? err.detail : "Failed to submit decision");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <h2>Approvals</h2>
          <select
            aria-label="Approval scope"
            value={scope}
            onChange={(event) => setScope(event.target.value as Scope)}
          >
            <option value="pending">Pending</option>
            <option value="decided">Decided</option>
            <option value="all">All</option>
          </select>
        </div>

        {error && <div className="alert alert-error">{error}</div>}
        {loading ? (
          <div className="page-message">Loading…</div>
        ) : approvals.length === 0 ? (
          <div className="page-message">Nothing in the queue.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Supplier</th>
                <th>Amount</th>
                <th>State</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((approval) => (
                <tr key={approval.id}>
                  <td>{approval.invoice_number ?? approval.invoice_id.slice(0, 8)}</td>
                  <td>{approval.supplier_name ?? "—"}</td>
                  <td>{formatAmount(approval.total_amount, approval.currency)}</td>
                  <td>{approval.invoice_state ?? "—"}</td>
                  <td>
                    <span className={`badge badge-${approval.decision}`}>
                      {approval.decision}
                    </span>
                  </td>
                  <td className="actions">
                    {approval.decision === "pending" ? (
                      <button
                        type="button"
                        className="button button-small"
                        onClick={() => openDialog(approval)}
                      >
                        Decide
                      </button>
                    ) : (
                      <span className="hint">{approval.comment ?? "—"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">{total} total</p>
      </div>

      {active && (
        <div className="dialog-backdrop" role="presentation" onClick={closeDialog}>
          <div
            className="dialog card"
            role="dialog"
            aria-modal="true"
            aria-label="Approval decision"
            onClick={(event) => event.stopPropagation()}
          >
            <h3>Decision for {active.invoice_number ?? active.invoice_id.slice(0, 8)}</h3>
            {active.supplier_name && (
              <p className="hint">
                {active.supplier_name} — {formatAmount(active.total_amount, active.currency)}
              </p>
            )}
            <label>
              Decision
              <select
                value={decision}
                onChange={(event) => setDecision(event.target.value as Decision)}
              >
                <option value="approved">Approve</option>
                <option value="rejected">Reject</option>
                <option value="correction_requested">Request correction</option>
              </select>
            </label>
            <label>
              Comment {requiresComment && <span className="required">*</span>}
              <textarea
                rows={4}
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                placeholder={requiresComment ? "Explain the reason…" : "Optional note"}
              />
            </label>
            {dialogError && <div className="alert alert-error">{dialogError}</div>}
            <div className="dialog-actions">
              <button type="button" className="button button-ghost" onClick={closeDialog}>
                Cancel
              </button>
              <button
                type="button"
                className="button"
                onClick={() => void handleSubmit()}
                disabled={submitting || (requiresComment && comment.trim() === "")}
              >
                {submitting ? "Submitting…" : "Submit decision"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
