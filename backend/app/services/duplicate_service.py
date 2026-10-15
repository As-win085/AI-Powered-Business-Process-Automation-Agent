"""Tenant-scoped duplicate detection persistence.

Runs the pure detector in :mod:`app.services.duplicate_detection` against the
other invoices in the same tenant and records every finding as a
``warning`` :class:`ValidationResult`. Duplicates are never used to auto-reject
an invoice; they only surface for human review.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, Invoice, InvoiceLineItem, Supplier, ValidationResult
from app.services.duplicate_detection import (
    DuplicateCandidate,
    detect_duplicates,
)

RULE_CODES = {
    "exact": "duplicate.exact_file",
    "business": "duplicate.business",
    "near": "duplicate.near",
}


def _candidate_from_invoice(
    invoice: Invoice,
    *,
    supplier_name: str | None,
    line_items: list[InvoiceLineItem],
) -> DuplicateCandidate:
    return DuplicateCandidate(
        invoice_id=str(invoice.id),
        supplier_name=supplier_name,
        invoice_number=invoice.invoice_number,
        total_amount=invoice.total_amount,
        invoice_date=invoice.invoice_date,
        line_items=[
            {
                "description": item.description,
                "line_total": item.line_total,
            }
            for item in line_items
        ],
    )


def _load_line_items(db: Session, tenant_id: uuid.UUID, invoice_ids: list[uuid.UUID]):
    if not invoice_ids:
        return {}
    rows = db.scalars(
        select(InvoiceLineItem).where(
            InvoiceLineItem.tenant_id == tenant_id,
            InvoiceLineItem.invoice_id.in_(invoice_ids),
        )
    ).all()
    grouped: dict[uuid.UUID, list[InvoiceLineItem]] = {}
    for item in rows:
        grouped.setdefault(item.invoice_id, []).append(item)
    return grouped


def detect_for_invoice(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    invoice: Invoice,
    other_invoices: list[Invoice] | None = None,
) -> list[dict[str, Any]]:
    """Return duplicate warnings for ``invoice`` against other tenant invoices."""
    if other_invoices is None:
        other_invoices = list(
            db.scalars(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.id != invoice.id,
                )
            ).all()
        )

    if not other_invoices:
        return []

    supplier_ids = {inv.supplier_id for inv in [invoice, *other_invoices] if inv.supplier_id}
    suppliers = {
        s.id: s.name
        for s in db.scalars(
            select(Supplier).where(
                Supplier.tenant_id == tenant_id,
                Supplier.id.in_(supplier_ids),
            )
        ).all()
    }

    line_items = _load_line_items(
        db, tenant_id, [invoice.id, *(inv.id for inv in other_invoices)]
    )

    incoming = _candidate_from_invoice(
        invoice,
        supplier_name=suppliers.get(invoice.supplier_id),
        line_items=line_items.get(invoice.id, []),
    )
    candidates = [
        _candidate_from_invoice(
            inv,
            supplier_name=suppliers.get(inv.supplier_id),
            line_items=line_items.get(inv.id, []),
        )
        for inv in other_invoices
    ]

    file_hash = None
    if invoice.document_id:
        file_hash = db.scalar(
            select(Document.file_hash).where(
                Document.tenant_id == tenant_id,
                Document.id == invoice.document_id,
            )
        )

    candidate_hashes: dict[str, str] = {}
    doc_ids = [inv.document_id for inv in other_invoices if inv.document_id]
    if doc_ids:
        for inv in other_invoices:
            if not inv.document_id:
                continue
            hash_value = db.scalar(
                select(Document.file_hash).where(
                    Document.tenant_id == tenant_id,
                    Document.id == inv.document_id,
                )
            )
            if hash_value:
                candidate_hashes[str(inv.id)] = hash_value

    return detect_duplicates(
        incoming,
        candidates,
        file_hash=file_hash,
        candidate_hashes=candidate_hashes,
    )


def persist_duplicate_results(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    invoice: Invoice,
    results: list[dict[str, Any]],
) -> list[ValidationResult]:
    """Store duplicate findings as append-only warning validation results."""
    stored: list[ValidationResult] = []
    for result in results:
        entry = ValidationResult(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            rule_code=RULE_CODES.get(result["kind"], f"duplicate.{result['kind']}"),
            severity="warning",
            message=(
                f"Possible {result['kind']} duplicate of invoice "
                f"{result['matched_invoice_id']} (score {result['score']})"
            ),
            details={
                "kind": result["kind"],
                "score": result["score"],
                "matched_invoice_id": result["matched_invoice_id"],
                "warning": True,
                **result.get("details", {}),
            },
        )
        db.add(entry)
        stored.append(entry)
    db.flush()
    return stored


def run_duplicate_detection(
    db: Session, *, tenant_id: uuid.UUID, invoice: Invoice
) -> list[dict[str, Any]]:
    """Detect, persist and return duplicate warnings for one invoice."""
    results = detect_for_invoice(db, tenant_id=tenant_id, invoice=invoice)
    if results:
        persist_duplicate_results(
            db, tenant_id=tenant_id, invoice=invoice, results=results
        )
    return results
