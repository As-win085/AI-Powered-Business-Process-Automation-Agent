import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.core.tenant_context import TenantContext
from app.db.session import get_db
from app.integrations.storage import get_storage
from app.schemas.document import (
    DocumentListResponse,
    DocumentRead,
    PageTextRead,
)
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])

DocumentType = Literal["invoice", "purchase_order", "receipt", "other"]


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Query("invoice"),
    context: TenantContext = Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Upload a document into the active tenant.

    Content is validated by extension and magic bytes, hashed for duplicate
    detection, and stored privately. Requires the document:upload permission.
    """
    document = document_service.create_document(
        db, context=context, upload=file, document_type=document_type
    )
    document_service.enqueue_document_processing(document.id)
    return DocumentRead.model_validate(document)


@router.get("", response_model=DocumentListResponse)
def list_documents(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    document_type: DocumentType | None = Query(None),
    context: TenantContext = Depends(require_permission(Permission.DOCUMENT_READ)),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    """List documents in the active tenant with optional filters and pagination."""
    items, total = document_service.list_documents(
        db,
        tenant_id=context.tenant_id,
        limit=limit,
        offset=offset,
        status=status_filter,
        document_type=document_type,
    )
    return DocumentListResponse(
        items=[DocumentRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: uuid.UUID,
    context: TenantContext = Depends(require_permission(Permission.DOCUMENT_READ)),
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Fetch a single document; ids from other tenants resolve to 404."""
    document = document_service.get_document(
        db, tenant_id=context.tenant_id, document_id=document_id
    )
    return DocumentRead.model_validate(document)


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    inline: bool = Query(False),
    context: TenantContext = Depends(require_permission(Permission.DOCUMENT_READ)),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream the stored file. Files are never served without authorization.

    ``?inline=1`` renders in the browser (for the document viewer); otherwise the
    response is served as a download.
    """
    document = document_service.get_document(
        db, tenant_id=context.tenant_id, document_id=document_id
    )
    headers = {}
    if not inline:
        headers = {"Content-Disposition": f'attachment; filename="{document.original_filename}"'}
    storage = get_storage()
    return StreamingResponse(
        storage.open(document.storage_key),
        media_type=document.content_type,
        headers=headers,
    )


@router.post("/{document_id}/process", response_model=DocumentRead)
def process_document(
    document_id: uuid.UUID,
    context: TenantContext = Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Extract per-page text (with OCR fallback) synchronously and return the update."""
    document = document_service.process_document(
        db, tenant_id=context.tenant_id, document_id=document_id
    )
    return DocumentRead.model_validate(document)


@router.get("/{document_id}/text", response_model=list[PageTextRead])
def get_document_text(
    document_id: uuid.UUID,
    context: TenantContext = Depends(require_permission(Permission.DOCUMENT_READ)),
    db: Session = Depends(get_db),
) -> list[PageTextRead]:
    """Return extracted per-page text for the document viewer."""
    pages = document_service.list_page_text(
        db, tenant_id=context.tenant_id, document_id=document_id
    )
    return [PageTextRead.model_validate(page) for page in pages]
