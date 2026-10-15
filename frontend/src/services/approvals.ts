import type { Approval, ApprovalList } from "../types/api";
import { apiFetch } from "./api";

export type Decision = "approved" | "rejected" | "correction_requested";

export async function listApprovals(params: {
  scope?: "pending" | "decided" | "all";
  assignedToMe?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<ApprovalList> {
  const query = new URLSearchParams();
  if (params.scope) query.set("scope", params.scope);
  if (params.assignedToMe) query.set("assigned_to_me", "true");
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<ApprovalList>(`/approvals${suffix}`);
}

export async function submitDecision(
  approvalId: string,
  decision: Decision,
  comment?: string
): Promise<Approval> {
  return apiFetch<Approval>(`/approvals/${approvalId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, comment: comment?.trim() || null }),
  });
}
