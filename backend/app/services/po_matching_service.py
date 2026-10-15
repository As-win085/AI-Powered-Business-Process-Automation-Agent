"""Tenant-scoped purchase-order matching persistence.

Loads the tenant's purchase orders, runs the pure matcher from
:mod:`app.services.po_matching`, links a matched invoice to its PO and records
every finding as an append-only :class:`ValidationResult`. Findings are for
human review only; a mismatch never auto-rejects an invoice.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Invoice,
    InvoiceLineItem,
    PurchaseOrder,
    Supplier,
    ValidationResult,
)
from app.services.po_matching import (
    InvoiceForMatch,
    MatchTolerance,
    POCandidate,
    POLineCandidate,
    match_purchase_order,
)
from app.services.purchase_order_service import load_po_items


def _tolerance_from_settings() -> MatchTolerance:
    settings = get_settings()
    return MatchTolerance(
        amount_abs=Decimal(str(settings.po_match_amount_tolerance_abs)),
        amount_pct=Decimal(str(settings.po_match_amount_tolerance_pct)),
        price_pct=Decimal(str(settings.po_match_price_tolerance_pct)),
        quantity_pct=Decimal(str(settings.po_match_quantity_tolerance_pct)),
    )


def _invoice_po_number(invoice: Invoice) -> str | None:
    if invoice.po_number:
        return invoice.po_number
    for source in (invoice.corrected_json, invoice.extracted_json):
        if isinstance(source, dict):
            for key in ("po_number", "purchase_order_number", "po"):
                value = source.get(key)
                if value:
                    return str(value)
    return None


def _load_invoice_lines(
    db: Session, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(InvoiceLineItem)
        .where(
            InvoiceLineItem.tenant_id == tenant_id,
            InvoiceLineItem.invoice_id == invoice_id,
        )
        .order_by(InvoiceLineItem.line_number)
    ).all()
    return [
        {
            "line_number": item.line_number,
            "description": item.description,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_total": item.line_total,
        }
        for item in rows
    ]


def _supplier_name(db: Session, tenant_id: uuid.UUID, invoice: Invoice) -> str | None:
    if invoice.supplier_id:
        return db.scalar(
            select(Supplier.name).where(
                Supplier.tenant_id == tenant_id, Supplier.id == invoice.supplier_id
            )
        )
    for source in (invoice.corrected_json, invoice.extracted_json):
        if isinstance(source, dict) and source.get("supplier_name"):
            return str(source["supplier_name"])
    return None


def _load_candidates(db: Session, tenant_id: uuid.UUID) -> list[POCandidate]:
    pos = list(
        db.scalars(
            select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
        ).all()
    )
    if not pos:
        return []
    supplier_names = {
        s.id: s.name
        for s in db.scalars(
            select(Supplier).where(Supplier.tenant_id == tenant_id)
        ).all()
    }
    items = load_po_items(db, tenant_id, [po.id for po in pos])
    return [
        POCandidate(
            purchase_order_id=str(po.id),
            po_number=po.po_number,
            supplier_name=supplier_names.get(po.supplier_id) if po.supplier_id else None,
            currency=po.currency,
            total_amount=po.total_amount,
            line_items=[
                POLineCandidate(
                    line_number=item.line_number,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                )
                for item in items.get(po.id, [])
            ],
        )
        for po in pos
    ]


def detect_for_invoice(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    invoice: Invoice,
    candidates: list[POCandidate] | None = None,
) -> dict[str, Any]:
    """Return the matching outcome for ``invoice`` without persisting it."""
    if candidates is None:
        candidates = _load_candidates(db, tenant_id)

    incoming = InvoiceForMatch(
        invoice_id=str(invoice.id),
        po_number=_invoice_po_number(invoice),
        supplier_name=_supplier_name(db, tenant_id, invoice),
        currency=invoice.currency,
        total_amount=invoice.total_amount,
        line_items=_load_invoice_lines(db, tenant_id, invoice.id),
    )
    outcome = match_purchase_order(incoming, candidates, _tolerance_from_settings())
    return {
        "matched": outcome.matched,
        "purchase_order_id": outcome.purchase_order_id,
        "po_number": outcome.po_number,
        "method": outcome.method,
        "findings": outcome.findings,
    }


def persist_findings(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    invoice: Invoice,
    findings: list[dict[str, Any]],
) -> list[ValidationResult]:
    """Store PO-match findings as append-only validation results."""
    stored: list[ValidationResult] = []
    for finding in findings:
        entry = ValidationResult(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            rule_code=finding["rule_code"],
            severity=finding["severity"],
            message=finding["message"],
            details={**finding.get("details", {}), "warning": finding["severity"] != "error"},
        )
        db.add(entry)
        stored.append(entry)
    db.flush()
    return stored


def run_po_matching(
    db: Session, *, tenant_id: uuid.UUID, invoice: Invoice
) -> dict[str, Any]:
    """Match, persist findings and link the invoice to the matched PO."""
    outcome = detect_for_invoice(db, tenant_id=tenant_id, invoice=invoice)

    for existing in db.scalars(
        select(ValidationResult).where(
            ValidationResult.tenant_id == tenant_id,
            ValidationResult.invoice_id == invoice.id,
            ValidationResult.rule_code.like("po.%"),
        )
    ).all():
        db.delete(existing)
    db.flush()

    persist_findings(
        db, tenant_id=tenant_id, invoice=invoice, findings=outcome["findings"]
    )

    if outcome["matched"] and outcome["purchase_order_id"]:
        invoice.purchase_order_id = uuid.UUID(outcome["purchase_order_id"])
    else:
        invoice.purchase_order_id = None
    db.add(invoice)

    return outcome


def list_findings(
    db: Session, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> list[ValidationResult]:
    return list(
        db.scalars(
            select(ValidationResult)
            .where(
                ValidationResult.tenant_id == tenant_id,
                ValidationResult.invoice_id == invoice_id,
                ValidationResult.rule_code.like("po.%"),
            )
            .order_by(ValidationResult.id)
        ).all()
    )
