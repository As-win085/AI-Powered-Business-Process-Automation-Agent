"""Invoice API endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.core.tenant_context import TenantContext
from app.db.models.invoice import Invoice
from app.db.models.supplier import Supplier
from app.db.models.validation import ValidationResult
from app.db.session import get_db
from app.schemas.invoice import InvoiceCreate, InvoiceRead, InvoiceUpdate
from app.services import approval_service, audit_service, duplicate_service, workflow_service
from app.services.duplicate_detection import normalize_invoice_number, normalize_supplier_name

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _get_invoice_or_404(db: Session, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


def _resolve_supplier(
    db: Session, tenant_id: uuid.UUID, name: str | None, tax_id: str | None
) -> Supplier | None:
    if not name:
        return None
    normalized = normalize_supplier_name(name)
    supplier = db.scalars(
        select(Supplier).where(
            Supplier.tenant_id == tenant_id, Supplier.normalized_name == normalized
        )
    ).first()
    if supplier is None:
        supplier = Supplier(
            tenant_id=tenant_id,
            name=name.strip(),
            normalized_name=normalized,
            tax_identifier=tax_id,
        )
        db.add(supplier)
        db.flush()
    return supplier


@router.post("", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_CORRECT)),
):
    """Create an invoice (typically from a processed document) for review."""
    supplier = _resolve_supplier(
        db, context.tenant_id, payload.supplier_name, payload.supplier_tax_id
    )
    invoice = Invoice(
        tenant_id=context.tenant_id,
        document_id=payload.document_id,
        supplier_id=supplier.id if supplier else None,
        invoice_number=payload.invoice_number,
        normalized_invoice_number=(
            normalize_invoice_number(payload.invoice_number) if payload.invoice_number else None
        ),
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        currency=payload.currency,
        subtotal=payload.subtotal,
        tax_amount=payload.tax_amount,
        total_amount=payload.total_amount,
        state="needs_review",
    )
    db.add(invoice)
    db.flush()
    audit_service.log_audit(
        db,
        tenant_id=context.tenant_id,
        actor_id=context.user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="invoice.create",
        details={"state": invoice.state, "total_amount": str(invoice.total_amount or "")},
    )
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/validate", response_model=InvoiceRead)
def validate_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_CORRECT)),
):
    """Mark a reviewed invoice as validated, allowing it to be submitted."""
    invoice = _get_invoice_or_404(db, context.tenant_id, invoice_id)
    workflow_service.transition_invoice(
        db, invoice, "validated", actor_id=context.user.id
    )
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/submit-for-approval")
def submit_for_approval(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_CORRECT)),
):
    """Route the invoice to an approver and open an approval."""
    invoice = _get_invoice_or_404(db, context.tenant_id, invoice_id)
    approval = approval_service.submit_for_approval(
        db, context.tenant_id, invoice, actor_id=context.user.id
    )
    db.commit()
    return {
        "invoice_id": str(invoice.id),
        "approval_id": str(approval.id),
        "approver_id": str(approval.approver_id) if approval.approver_id else None,
        "invoice_state": invoice.state,
    }


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

    corrected = dict(invoice.corrected_json or {})
    if update_data:
        corrected.update({k: str(v) for k, v in update_data.items() if k != "line_items"})
    invoice.corrected_json = corrected
    invoice.state = "needs_review"

    db.add(invoice)
    audit_service.log_audit(
        db,
        tenant_id=context.tenant_id,
        actor_id=context.user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="invoice.correct",
        details={"old": old_state, "new": {k: str(v) for k, v in update_data.items()}},
    )
    db.commit()
    db.refresh(invoice)

    return invoice


@router.get("/{invoice_id}/duplicates")
def list_duplicate_warnings(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_READ)),
):
    """Return stored duplicate warnings for an invoice (review flags only)."""
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.tenant_id == context.tenant_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    rows = db.scalars(
        select(ValidationResult)
        .where(
            ValidationResult.tenant_id == context.tenant_id,
            ValidationResult.invoice_id == invoice.id,
            ValidationResult.rule_code.like("duplicate.%"),
        )
        .order_by(ValidationResult.id)
    ).all()
    return {
        "invoice_id": str(invoice.id),
        "warnings": [
            {
                "rule_code": row.rule_code,
                "severity": row.severity,
                "message": row.message,
                "details": row.details,
            }
            for row in rows
        ],
    }


@router.post("/{invoice_id}/check-duplicates")
def check_duplicates(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_READ)),
):
    """Run duplicate detection and persist the warnings for review."""
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.tenant_id == context.tenant_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    results = duplicate_service.run_duplicate_detection(
        db, tenant_id=context.tenant_id, invoice=invoice
    )
    db.commit()
    return {"invoice_id": str(invoice.id), "warnings": results}

