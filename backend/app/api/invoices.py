"""Invoice API endpoints."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.core.tenant_context import TenantContext
from app.db.models.audit_log import AuditLog
from app.db.models.invoice import Invoice
from app.db.session import get_db
from app.schemas.invoice import InvoiceRead, InvoiceUpdate

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_READ)),
):
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.tenant_id == context.tenant_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdate,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_CORRECT)),
):
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.tenant_id == context.tenant_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    old_state = {
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "currency": invoice.currency,
        "subtotal": str(invoice.subtotal) if invoice.subtotal is not None else None,
        "tax_amount": str(invoice.tax_amount) if invoice.tax_amount is not None else None,
        "total_amount": str(invoice.total_amount) if invoice.total_amount is not None else None,
    }

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(invoice, field) and field not in ("line_items",):
            setattr(invoice, field, value)

    corrected = invoice.corrected_json or {}
    if update_data:
        corrected.update({k: v for k, v in update_data.items() if k != "line_items"})
    invoice.corrected_json = corrected

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    audit = AuditLog(
        tenant_id=context.tenant_id,
        actor_id=context.user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="correct",
        old_values=old_state,
        new_values=update_data,
    )
    db.add(audit)
    db.commit()

    return invoice

