import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../services/api";
import {
  fetchDocumentBlob,
  fetchDocumentPages,
  getDocument,
  processDocument,
} from "../services/documents";
import type { Document, PageText } from "../types/api";

export default function DocumentViewer() {
  const { id } = useParams<{ id: string }>();
  const documentId = id ?? "";

  const [document, setDocument] = useState<Document | null>(null);
  const [pages, setPages] = useState<PageText[]>([]);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  const loadAll = useCallback(async () => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    try {
      const [doc, pageList, blob] = await Promise.all([
        getDocument(documentId),
        fetchDocumentPages(documentId),
        fetchDocumentBlob(documentId, true),
      ]);
      setDocument(doc);
      setPages(pageList);
      setPdfUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return URL.createObjectURL(blob);
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load document");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    void loadAll();
    return () => {
      setPdfUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return null;
      });
    };
  }, [loadAll]);

  const handleProcess = async () => {
    setProcessing(true);
    setError(null);
    try {
      await processDocument(documentId);
      await loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Processing failed");
    } finally {
      setProcessing(false);
    }
  };

  if (loading) {
    return <div className="page-message">Loading document…</div>;
  }
  if (!document) {
    return (
      <div>
        <p className="page-message">{error ?? "Document not found."}</p>
        <Link to="/documents">Back to documents</Link>
      </div>
    );
  }

  return (
    <div>
      <div className="viewer-header">
        <Link to="/documents">← Documents</Link>
        <h1>{document.original_filename}</h1>
        <span className={`badge badge-${document.status}`}>{document.status}</span>
        {(document.status === "uploaded" ||
          document.status === "queued" ||
          document.status === "failed") && (
          <button
            type="button"
            className="button button-small"
            disabled={processing}
            onClick={() => void handleProcess()}
          >
            {processing ? "Processing…" : "Process"}
          </button>
        )}
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      {document.error && (
        <div className="alert alert-error">
          <strong>Failure reason:</strong> {document.error}
        </div>
      )}
      <div className="viewer-split">
        <section className="viewer-pane">
          <h2>Original document</h2>
          {pdfUrl ? (
            <iframe title="Original document" src={pdfUrl} className="pdf-frame" />
          ) : (
            <div className="page-message">PDF unavailable.</div>
          )}
        </section>
        <section className="viewer-pane">
          <h2>Extracted text</h2>
          {pages.length === 0 ? (
            <div className="page-message">
              No extracted text yet.{" "}
              {document.status === "failed"
                ? "Processing failed."
                : "Press Process to extract text."}
            </div>
          ) : (
            <div className="pages">
              {pages.map((page) => (
                <article key={page.page_number} className="card page-text">
                  <header className="page-text-header">
                    Page {page.page_number}
                    <span className={`badge badge-source-${page.source}`}>
                      {page.source === "ocr" ? "OCR" : "digital text"}
                    </span>
                  </header>
                  <pre>{page.text}</pre>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}