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