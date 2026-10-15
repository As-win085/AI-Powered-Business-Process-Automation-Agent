export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
}

export interface Membership {
  id: string;
  tenant_id: string;
  user_id: string;
  role_name: string;
  status: string;
  tenant: Tenant;
}

export interface MeResponse {
  user: User;
  memberships: Membership[];
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export type DocumentType = "invoice" | "purchase_order" | "receipt" | "other";
export type DocumentStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "needs_review"
  | "ready_for_approval"
  | "approved"
  | "rejected"
  | "failed";

export interface Document {
  id: string;
  tenant_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  file_hash: string;
  document_type: DocumentType;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  uploaded_by: string | null;
  created_at: string;
}

export interface DocumentList {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}

export type TextSource = "embedded" | "ocr";

export interface PageText {
  page_number: number;
  text: string;
  source: TextSource;
  engine: string;
}

export type ApprovalDecision =
  | "pending"
  | "approved"
  | "rejected"
  | "correction_requested";

export interface Approval {
  id: string;
  tenant_id: string;
  invoice_id: string;
  approver_id: string | null;
  decision: ApprovalDecision;
  comment: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
  invoice_number: string | null;
  supplier_name: string | null;
  total_amount: string | null;
  currency: string | null;
  invoice_state: string | null;
}

export interface ApprovalList {
  items: Approval[];
  total: number;
}

export type POStatus = "open" | "closed" | "cancelled";

export interface PurchaseOrderLineItem {
  id: string;
  line_number: number;
  description: string | null;
  quantity: string | null;
  unit_price: string | null;
  line_total: string | null;
}

export interface PurchaseOrder {
  id: string;
  tenant_id: string;
  supplier_id: string | null;
  po_number: string;
  currency: string;
  total_amount: string | null;
  status: POStatus;
  created_at: string | null;
  updated_at: string | null;
  line_items: PurchaseOrderLineItem[];
}

export interface PurchaseOrderList {
  total: number;
  items: PurchaseOrder[];
}

export interface PurchaseOrderImportResult {
  created: number;
  skipped: string[];
  errors: { row: number; message: string }[];
}

export interface AnomalyReason {
  code: string;
  message: string;
  detail: Record<string, number | string>;
}

export interface AnomalyQueueItem {
  invoice_id: string;
  invoice_number: string | null;
  supplier_name: string | null;
  invoice_date: string | null;
  currency: string | null;
  total_amount: string | null;
  state: string;
  anomaly_score: number | null;
  anomaly_model_version: string | null;
  risk_level: string | null;
  reasons: AnomalyReason[];
}

export interface AnomalyQueue {
  total: number;
  items: AnomalyQueueItem[];
}