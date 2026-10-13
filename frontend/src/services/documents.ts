import type {
  Document,
  DocumentList,
  LoginResponse,
  MeResponse,
  PageText,
} from "../types/api";
import { apiBasePath, apiFetch, getAccessToken } from "./api";

export async function login(email: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function fetchMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/auth/me");
}

export async function listDocuments(params: {
  limit?: number;
  offset?: number;
  status?: string;
  document_type?: string;
}): Promise<DocumentList> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  if (params.status) query.set("status", params.status);
  if (params.document_type) query.set("document_type", params.document_type);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<DocumentList>(`/documents${suffix}`);
}

export async function uploadDocument(form: FormData): Promise<Document> {
  return apiFetch<Document>("/documents", {
    method: "POST",
    body: form,
  });
}

export async function getDocument(documentId: string): Promise<Document> {
  return apiFetch<Document>(`/documents/${documentId}`);
}

export async function processDocument(documentId: string): Promise<Document> {
  return apiFetch<Document>(`/documents/${documentId}/process`, {
    method: "POST",
  });
}

export async function fetchDocumentPages(documentId: string): Promise<PageText[]> {
  return apiFetch<PageText[]>(`/documents/${documentId}/text`);
}

export async function fetchDocumentBlob(documentId: string, inline = true): Promise<Blob> {
  const response = await fetch(
    `${apiBasePath()}/documents/${documentId}/download?inline=${inline ? 1 : 0}`,
    {
      headers: {
        Authorization: `Bearer ${getAccessToken() ?? ""}`,
        "X-Tenant-Id": localStorage.getItem("automation_tenant_id") ?? "",
      },
    }
  );
  if (!response.ok) {
    throw new Error(`Failed to load document (${response.status})`);
  }
  return response.blob();
}