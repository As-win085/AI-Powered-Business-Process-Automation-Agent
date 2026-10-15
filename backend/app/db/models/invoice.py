import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

INVOICE_STATES = (
    "uploaded",
    "queued",
    "processing",
    "needs_review",
    "validated",
    "pending_approval",
    "ready_for_approval",
    "approved",
    "rejected",
    "correction_requested",
    "failed",
)


class Invoice(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_invoices_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "supplier_id",
            "normalized_invoice_number",
            name="uq_invoices_supplier_number",
        ),
        CheckConstraint(
            "state in ('uploaded', 'queued', 'processing', 'needs_review', "
            "'validated', 'pending_approval', 'ready_for_approval', 'approved', "
            "'rejected', 'correction_requested', 'failed')",
            name="ck_invoices_state",
        ),
        Index("ix_invoices_tenant_anomaly", "tenant_id", "anomaly_flagged"),
    )

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True
    )
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    normalized_invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    po_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    normalized_po_number: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="uploaded", server_default="uploaded"
    )
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    anomaly_score: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    anomaly_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    anomaly_flagged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    anomaly_reasons: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    extracted_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    corrected_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class InvoiceLineItem(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_invoice_line_items_invoice",
            ondelete="CASCADE",
        ),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)



