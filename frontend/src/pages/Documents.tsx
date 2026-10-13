import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../services/api";
import {
  listDocuments,
  processDocument,
  uploadDocument,
} from "../services/documents";
import type { Document, DocumentType } from "../types/api";

const DOCUMENT_TYPES: DocumentType[] = ["invoice", "purchase_order", "receipt", "other"];

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Documents() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>("invoice");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [processingId, setProcessingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listDocuments({ limit: 100 });
      setDocuments(result.items);
      setTotal(result.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("document_type", documentType);
      await uploadDocument(form);
      setFile(null);
      await refresh();
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.detail : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleProcess = async (documentId: string) => {
    setProcessingId(documentId);
    try {
      await processDocument(documentId);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Processing failed");
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div>
      <div className="card upload-card">
        <h2>Upload a document</h2>
        <div className="upload-row">
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <select
            aria-label="Document type"
            value={documentType}
            onChange={(event) => setDocumentType(event.target.value as DocumentType)}
          >
            {DOCUMENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.replace("_", " ")}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="button"
            onClick={() => void handleUpload()}
            disabled={!file || uploading}
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
        {uploadError && <div className="alert alert-error">{uploadError}</div>}
      </div>

      <div className="card">
        <h2>Documents</h2>
        {error && <div className="alert alert-error">{error}</div>}
        {loading ? (
          <div className="page-message">Loading…</div>
        ) : documents.length === 0 ? (
          <div className="page-message">No documents yet. Upload one above.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Type</th>
                <th>Status</th>
                <th>Size</th>
                <th>Uploaded</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.id}>
                  <td>{document.original_filename}</td>
                  <td>{document.document_type}</td>
                  <td>
                    <span className={`badge badge-${document.status}`}>
                      {document.status}
                    </span>
                    {document.error && (
                      <div className="doc-error" title={document.error}>
                        {document.error}
                      </div>
                    )}
                  </td>
                  <td>{formatBytes(document.size_bytes)}</td>
                  <td>{new Date(document.created_at).toLocaleString()}</td>
                  <td className="actions">
                    <Link className="button button-small" to={`/documents/${document.id}`}>
                      View
                    </Link>
                    {(document.status === "uploaded" ||
                      document.status === "queued" ||
                      document.status === "failed") && (
                      <button
                        type="button"
                        className="button button-small"
                        disabled={processingId === document.id}
                        onClick={() => void handleProcess(document.id)}
                      >
                        {processingId === document.id ? "Processing…" : "Process"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">{total} total</p>
      </div>
    </div>
  );
}