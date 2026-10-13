import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentText(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """Per-page extracted text with provenance (embedded vs. OCR).

    A page row is (re)written by each successful extraction run, so the most
    recent run always reflects the current document contents.
    """

    __tablename__ = "document_text"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_document_text_document",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "document_id", "page_number", name="uq_document_text_page"),
        CheckConstraint("source in ('embedded', 'ocr')", name="ck_document_text_source"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    engine: Mapped[str] = mapped_column(String(64), nullable=False)
