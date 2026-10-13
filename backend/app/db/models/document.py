import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

DOCUMENT_TYPES = ("invoice", "purchase_order", "receipt", "other")
DOCUMENT_STATUSES = (
    "uploaded",
    "queued",
    "processing",
    "needs_review",
    "ready_for_approval",
    "approved",
    "rejected",
    "failed",
)


class Document(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id"),
        # Exact-file duplicate detection is tenant-scoped.
        UniqueConstraint("tenant_id", "file_hash", name="uq_documents_tenant_hash"),
        CheckConstraint(
            "document_type in ('invoice', 'purchase_order', 'receipt', 'other')",
            name="ck_documents_type",
        ),
        CheckConstraint(
            "status in ('uploaded', 'queued', 'processing', 'needs_review', "
            "'ready_for_approval', 'approved', 'rejected', 'failed')",
            name="ck_documents_status",
        ),
    )

    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="invoice", server_default="invoice"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="uploaded", server_default="uploaded"
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
