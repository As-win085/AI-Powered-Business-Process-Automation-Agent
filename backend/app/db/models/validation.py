import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, UUIDPrimaryKeyMixin

SEVERITIES = ("info", "warning", "error")


class ValidationResult(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    __tablename__ = "validation_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_validation_results_invoice",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "severity in ('info', 'warning', 'error')",
            name="ck_validation_results_severity",
        ),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="info", server_default="info"
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
