import contextlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.files import read_upload, sha256_hex, validate_upload
from app.core.tenant_context import TenantContext
from app.db.models import Document, DocumentText, ProcessingJob
from app.integrations.storage import get_storage
from app.services import audit_service, extraction_service

MAX_PAGE_LIMIT = 100
DEFAULT_PAGE_LIMIT = 50


def create_document(
    db: Session,
    *,
    context: TenantContext,
    upload: UploadFile,
    document_type: str = "invoice",
) -> Document:
    """Validate, store and register an uploaded document.

    The file is content-validated (extension + magic bytes), hashed and written
    to private storage under a tenant-scoped key. Exact duplicates within the
    same tenant are rejected with a 409.
    """
    data = read_upload(upload)
    content_type = validate_upload(upload.filename or "", upload.content_type, data)
    file_hash = sha256_hex(data)

    duplicate = db.scalars(
        select(Document).where(
            Document.tenant_id == context.tenant_id,
            Document.file_hash == file_hash,
        )
    ).first()
    if duplicate is not None:
        raise ConflictError("This file has already been uploaded to this workspace")

    document_id = uuid.uuid4()
    filename = upload.filename or "upload"
    extension = Path(filename).suffix.lower()
    storage_key = f"documents/{context.tenant_id}/{document_id}{extension}"

    document = Document(
        id=document_id,
        tenant_id=context.tenant_id,
        storage_key=storage_key,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        file_hash=file_hash,
        document_type=document_type,
        status="uploaded",
        uploaded_by=context.user.id,
    )

    storage = get_storage()
    storage.save(storage_key, data)
    db.add(document)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        storage.delete(storage_key)
        raise ConflictError("This file has already been uploaded to this workspace") from exc

    audit_service.log_audit(
        db,
        tenant_id=context.tenant_id,
        actor_id=context.user.id,
        action="document.uploaded",
        entity_type="document",
        entity_id=document.id,
        details={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(data),
            "file_hash": file_hash,
        },
    )
    db.commit()
    return document


def list_documents(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
    status: str | None = None,
    document_type: str | None = None,
) -> tuple[list[Document], int]:
    limit = max(1, min(limit, MAX_PAGE_LIMIT))
    offset = max(0, offset)

    filters = [Document.tenant_id == tenant_id]
    if status:
        filters.append(Document.status == status)
    if document_type:
        filters.append(Document.document_type == document_type)

    base = select(Document).where(*filters)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = base.order_by(Document.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), total


def get_document(db: Session, *, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    """Fetch a document scoped to the tenant; other tenants' ids yield 404."""
    document = db.scalars(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.id == document_id,
        )
    ).first()
    if document is None:
        raise NotFoundError("Document not found")
    return document


def process_document(db: Session, *, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    """Extract per-page text (with OCR fallback) and update document status.

    On success the extracted pages replace any previous run and the document moves
    to ``needs_review``. Failures (corrupt, password-protected, no text) mark the
    document as ``failed`` with a human-readable reason.
    """
    document = get_document(db, tenant_id=tenant_id, document_id=document_id)

    if document.status in ("needs_review", "ready_for_approval", "approved"):
        return document

    job = _start_job(db, tenant_id, document_id)
    now = datetime.now(UTC)

    storage = get_storage()
    content = storage.open(document.storage_key).read()

    try:
        pages = extraction_service.extract_pdf_text(content)
    except extraction_service.ExtractionError as exc:
        reason = str(exc)
        if document.status not in ("failed",):  # only log first meaningful failure; avoid duplicates
            document.status = "failed"
            document.error = reason
        job.status = "failed"
        job.error = reason
        job.finished_at = now
        try:
            audit_service.log_audit(
                db,
                tenant_id=tenant_id,
                action="document.processing_failed",
                entity_type="document",
                entity_id=document.id,
                details={"reason": reason},
            )
        except Exception:
            pass
        db.commit()
        return document

    db.execute(
        delete(DocumentText).where(
            DocumentText.tenant_id == tenant_id,
            DocumentText.document_id == document.id,
        )
    )
    db.flush()

    for page in pages:
        db.add(
            DocumentText(
                tenant_id=tenant_id,
                document_id=document.id,
                page_number=page.page_number,
                text=page.text,
                source=page.source,
                engine=page.engine,
            )
        )

    document.status = "needs_review"
    document.error = None
    document.page_count = len(pages)
    job.status = "succeeded"
    job.finished_at = now
    job.error = None

    try:
        audit_service.log_audit(
            db,
            tenant_id=tenant_id,
            action="document.processed",
            entity_type="document",
            entity_id=document.id,
            details={
                "pages": len(pages),
                "ocr_pages": sum(1 for page in pages if page.source == "ocr"),
                "embedded_pages": sum(1 for page in pages if page.source == "embedded"),
            },
        )
    except Exception:
        pass
    db.commit()
    return document


def list_page_text(
    db: Session, *, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> list[DocumentText]:
    """Return extracted per-page text; documents from other tenants yield 404."""
    document = get_document(db, tenant_id=tenant_id, document_id=document_id)
    stmt = (
        select(DocumentText)
        .where(
            DocumentText.tenant_id == tenant_id,
            DocumentText.document_id == document.id,
        )
        .order_by(DocumentText.page_number)
    )
    return list(db.scalars(stmt).all())


def enqueue_document_processing(
    document_id: uuid.UUID,
    *,
    db: Session | None = None,
    tenant_id: uuid.UUID | None = None,
) -> None:
    """Submit the document to Celery for asynchronous processing when enabled."""
    if not settings.auto_process_documents:
        return

    if db is not None and tenant_id is not None:
        with contextlib.suppress(Exception):
            document = get_document(db, tenant_id=tenant_id, document_id=document_id)
            if document.status in ("processing", "needs_review", "ready_for_approval"):
                return
            document.status = "queued"
            _start_job(db, tenant_id, document_id)
            db.commit()

    from app.workers.tasks import process_document_task

    with contextlib.suppress(Exception):  # broker may be down during local development
        process_document_task.delay(str(document_id))


def _start_job(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID) -> ProcessingJob:
    latest = db.scalars(
        select(ProcessingJob)
        .where(
            ProcessingJob.tenant_id == tenant_id,
            ProcessingJob.document_id == document_id,
        )
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    ).first()
    if latest is None or latest.status in ("succeeded", "failed"):
        latest = ProcessingJob(
            tenant_id=tenant_id,
            document_id=document_id,
            job_type="text_extraction",
            idempotency_key=f"{document_id}:{uuid.uuid4()}",
        )
        db.add(latest)
    if latest.status != "running":
        latest.status = "running"
        latest.attempts = (latest.attempts or 0) + 1
        latest.error = None
        latest.started_at = datetime.now(UTC)
    db.flush()
    return latest
