"""Approval workflow schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DecisionValue = Literal["approved", "rejected", "correction_requested"]
DecisionFilter = Literal["pending", "decided", "all"]


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Any
    tenant_id: Any
    invoice_id: Any
    approver_id: Any | None = None
    decision: str
    comment: str | None = None
    decided_at: datetime | None = None
    created_at: Any | None = None
    updated_at: Any | None = None
    # Denormalised invoice context for the approval queue.
    invoice_number: str | None = None
    supplier_name: str | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    invoice_state: str | None = None


class ApprovalDecisionRequest(BaseModel):
    decision: DecisionValue
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _require_comment_on_reject(self) -> ApprovalDecisionRequest:
        needs_comment = self.decision in ("rejected", "correction_requested")
        if needs_comment and not (self.comment and self.comment.strip()):
            raise ValueError("A comment is required when rejecting an invoice")
        return self


class ApprovalListRead(BaseModel):
    items: list[ApprovalRead]
    total: int


__all__ = [
    "ApprovalDecisionRequest",
    "ApprovalListRead",
    "ApprovalRead",
    "DecisionFilter",
    "DecisionValue",
]
