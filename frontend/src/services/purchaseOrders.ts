import type {
  PurchaseOrder,
  PurchaseOrderImportResult,
  PurchaseOrderList,
  POStatus,
} from "../types/api";
import { apiFetch } from "./api";

export interface PurchaseOrderItemPayload {
  line_number?: number | null;
  description?: string | null;
  quantity?: string | null;
  unit_price?: string | null;
  line_total?: string | null;
}

export interface PurchaseOrderPayload {
  po_number: string;
  supplier_name?: string | null;
  supplier_tax_id?: string | null;
  currency: string;
  total_amount?: string | null;
  status?: POStatus;
  line_items?: PurchaseOrderItemPayload[];
}

export async function listPurchaseOrders(params: {
  status?: POStatus | null;
  query?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<PurchaseOrderList> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.query) query.set("q", params.query);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<PurchaseOrderList>(`/purchase-orders${suffix}`);
}

export async function createPurchaseOrder(
  payload: PurchaseOrderPayload
): Promise<PurchaseOrder> {
  return apiFetch<PurchaseOrder>("/purchase-orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deletePurchaseOrder(poId: string): Promise<void> {
  await apiFetch<void>(`/purchase-orders/${poId}`, { method: "DELETE" });
}

export async function importPurchaseOrders(
  file: File
): Promise<PurchaseOrderImportResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  return apiFetch<PurchaseOrderImportResult>("/purchase-orders/import", {
    method: "POST",
    body: form,
  });
}
