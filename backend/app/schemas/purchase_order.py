"""Purchase order schemas for CRUD and CSV import."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

POStatus = Literal["open", "closed", "cancelled"]


class PurchaseOrderItemData(BaseModel):
    line_number: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


class PurchaseOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Any
    line_number: int
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


class PurchaseOrderCreate(BaseModel):
    po_number: str = Field(min_length=1, max_length=128)
    supplier_name: str | None = None
    supplier_tax_id: str | None = None
    currency: str = Field(min_length=3, max_length=3)
    total_amount: Decimal | None = None
    status: POStatus = "open"
    line_items: list[PurchaseOrderItemData] | None = None


class PurchaseOrderUpdate(BaseModel):
    po_number: str | None = Field(default=None, min_length=1, max_length=128)
    supplier_name: str | None = None
    supplier_tax_id: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    total_amount: Decimal | None = None
    status: POStatus | None = None
    line_items: list[PurchaseOrderItemData] | None = None


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Any
    tenant_id: Any
    supplier_id: Any | None = None
    po_number: str
    currency: str
    total_amount: Decimal | None = None
    status: str
    created_at: Any | None = None
    updated_at: Any | None = None
    line_items: list[PurchaseOrderItemRead] = Field(default_factory=list)


class PurchaseOrderListRead(BaseModel):
    total: int
    items: list[PurchaseOrderRead]


class PurchaseOrderImportError(BaseModel):
    row: int
    message: str


class PurchaseOrderImportResult(BaseModel):
    created: int
    skipped: list[str]
    errors: list[PurchaseOrderImportError]


__all__ = [
    "POStatus",
    "PurchaseOrderCreate",
    "PurchaseOrderImportError",
    "PurchaseOrderImportResult",
    "PurchaseOrderItemData",
    "PurchaseOrderItemRead",
    "PurchaseOrderListRead",
    "PurchaseOrderRead",
    "PurchaseOrderUpdate",
]
