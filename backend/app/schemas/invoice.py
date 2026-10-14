"""Invoice schemas for structured extraction and corrections."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvoiceLineItemData(BaseModel):
    line_number: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax_amount: Decimal | None = None
    line_total: Decimal | None = None


class InvoiceData(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    supplier_name: str | None = None
    supplier_tax_id: str | None = None
    customer_name: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    notes: str | None = None
    line_items: list[InvoiceLineItemData] | None = None


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Any
    tenant_id: Any
    document_id: Any | None = None
    supplier_id: Any | None = None
    purchase_order_id: Any | None = None
    invoice_number: str | None = None
    normalized_invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    state: str
    risk_level: str | None = None
    extracted_json: dict[str, Any] | None = None
    corrected_json: dict[str, Any] | None = None
    created_at: Any | None = None
    updated_at: Any | None = None


class InvoiceLineItemUpdate(BaseModel):
    line_number: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax_amount: Decimal | None = None
    line_total: Decimal | None = None


class InvoiceUpdate(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    supplier_name: str | None = None
    supplier_tax_id: str | None = None
    customer_name: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    notes: str | None = None
    line_items: list[InvoiceLineItemUpdate] | None = None


__all__ = [
    "InvoiceData",
    "InvoiceLineItemData",
    "InvoiceRead",
    "InvoiceUpdate",
    "InvoiceLineItemUpdate",
]

