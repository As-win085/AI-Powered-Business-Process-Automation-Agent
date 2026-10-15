"""Anomaly detection schemas (review flags, never automatic decisions)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class AnomalyReason(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class InvoiceAnomalyRead(BaseModel):
    invoice_id: Any
    score: float | None = None
    flagged: bool
    model_version: str | None = None
    risk_level: str | None = None
    has_history: bool = False
    threshold: float | None = None
    reasons: list[AnomalyReason] = Field(default_factory=list)
    features: dict[str, float] | None = None


class AnomalyQueueItem(BaseModel):
    invoice_id: Any
    invoice_number: str | None = None
    supplier_name: str | None = None
    invoice_date: Any | None = None
    currency: str | None = None
    total_amount: Decimal | None = None
    state: str
    anomaly_score: float | None = None
    anomaly_model_version: str | None = None
    risk_level: str | None = None
    reasons: list[AnomalyReason] = Field(default_factory=list)


class AnomalyQueueRead(BaseModel):
    total: int
    items: list[AnomalyQueueItem]


class AnomalyModelInfo(BaseModel):
    trained: bool
    version: str | None = None
    threshold: float | None = None
    feature_names: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AnomalyModelInfo",
    "AnomalyQueueItem",
    "AnomalyQueueRead",
    "AnomalyReason",
    "InvoiceAnomalyRead",
]
