import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.document import DOCUMENT_STATUSES, DOCUMENT_TYPES


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    file_hash: str
    document_type: str
    status: str
    error: str | None = None
    page_count: int | None = None
    uploaded_by: uuid.UUID | None = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int


class PageTextRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_number: int
    text: str
    source: str
    engine: str


__all__ = [
    "DOCUMENT_STATUSES",
    "DOCUMENT_TYPES",
    "DocumentListResponse",
    "DocumentRead",
    "PageTextRead",
]
