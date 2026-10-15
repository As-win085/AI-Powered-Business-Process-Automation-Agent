"""Tenant-scoped anomaly scoring for invoices.

Scores an invoice against its supplier's own prior history using the persisted
Isolation Forest model, stores the score/version/reasons on the invoice and
exposes a review queue. Scores are advisory only: they never change the invoice
state or authorise any action.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Invoice, InvoiceLineItem, PurchaseOrder, Supplier, ValidationResult
from app.services.anomaly_features import explain, extract_features, to_vector
from app.services.anomaly_model_store import load_model


class AnomalyModelUnavailable(RuntimeError):
    """Raised when no trained anomaly model is available to score with."""


def _load_history(
    db: Session, *, tenant_id: uuid.UUID, invoice: Invoice
) -> list[dict[str, Any]]:
    """Return this supplier's prior invoices (oldest first) as feature inputs."""
    if not invoice.supplier_id:
        return []

    stmt = select(Invoice).where(
        Invoice.tenant_id == tenant_id,
        Invoice.supplier_id == invoice.supplier_id,
        Invoice.id != invoice.id,
    )
    if invoice.invoice_date is not None:
        stmt = stmt.where(
            Invoice.invoice_date.isnot(None), Invoice.invoice_date <= invoice.invoice_date
        )
    history_invoices = list(db.scalars(stmt.order_by(Invoice.invoice_date)).all())
    if not history_invoices:
        return []

    ids = [item.id for item in history_invoices]
    lines = db.scalars(
        select(InvoiceLineItem).where(
            InvoiceLineItem.tenant_id == tenant_id, InvoiceLineItem.invoice_id.in_(ids)
        )
    ).all()
    by_invoice: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for line in lines:
        by_invoice.setdefault(line.invoice_id, []).append(
            {"unit_price": line.unit_price, "line_total": line.line_total}
        )

    return [
        {
            "total_amount": item.total_amount,
            "invoice_date": item.invoice_date,
            "line_items": by_invoice.get(item.id, []),
        }
        for item in history_invoices
    ]


def _po_total(db: Session, *, tenant_id: uuid.UUID, invoice: Invoice) -> Decimal | None:
    if not invoice.purchase_order_id:
        return None
    return db.scalar(
        select(PurchaseOrder.total_amount).where(
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.id == invoice.purchase_order_id,
        )
    )


def _invoice_line_items(
    db: Session, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.tenant_id == tenant_id, InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_number)
    ).all()
    return [{"unit_price": row.unit_price, "line_total": row.line_total} for row in rows]


def score_invoice(
    db: Session, *, tenant_id: uuid.UUID, invoice: Invoice
) -> dict[str, Any]:
    """Compute (but do not persist) the anomaly score for ``invoice``."""
    model = load_model()
    if model is None:
        raise AnomalyModelUnavailable("no trained anomaly model is available")

    settings = get_settings()
    history = _load_history(db, tenant_id=tenant_id, invoice=invoice)
    features = extract_features(
        amount=invoice.total_amount,
        invoice_date=invoice.invoice_date,
        line_items=_invoice_line_items(db, tenant_id=tenant_id, invoice_id=invoice.id),
        history=history,
        po_total=_po_total(db, tenant_id=tenant_id, invoice=invoice),
        window_days=settings.anomaly_feature_window_days,
    )
    score, flagged = model.score_one(features)
    reasons = explain(features)
    if flagged:
        risk_level = "high"
    elif score >= model.threshold * 0.8:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "score": score,
        "flagged": flagged,
        "threshold": model.threshold,
        "version": model.version,
        "has_history": len(history) >= settings.anomaly_min_history,
        "risk_level": risk_level,
        "reasons": reasons,
        "features": features,
        "vector": to_vector(features),
    }


def persist_score(
    db: Session, *, tenant_id: uuid.UUID, invoice: Invoice, result: dict[str, Any]
) -> Invoice:
    """Store the score/version/flag/reasons on the invoice and audit findings."""
    invoice.anomaly_score = Decimal(str(result["score"]))
    invoice.anomaly_model_version = result["version"]
    invoice.anomaly_flagged = bool(result["flagged"])
    invoice.anomaly_reasons = result["reasons"]
    invoice.risk_level = result["risk_level"]
    db.add(invoice)

    for existing in db.scalars(
        select(ValidationResult).where(
            ValidationResult.tenant_id == tenant_id,
            ValidationResult.invoice_id == invoice.id,
            ValidationResult.rule_code.like("anomaly.%"),
        )
    ).all():
        db.delete(existing)
    db.flush()

    for reason in result["reasons"]:
        db.add(
            ValidationResult(
                tenant_id=tenant_id,
                invoice_id=invoice.id,
                rule_code=f"anomaly.{reason['code']}",
                severity="warning",
                message=reason["message"],
                details=dict(reason.get("detail", {})),
            )
        )
    db.flush()
    return invoice


def run_anomaly_detection(
    db: Session, *, tenant_id: uuid.UUID, invoice: Invoice
) -> dict[str, Any]:
    """Score an invoice and persist the result (idempotent)."""
    result = score_invoice(db, tenant_id=tenant_id, invoice=invoice)
    persist_score(db, tenant_id=tenant_id, invoice=invoice, result=result)
    return result


def read_anomaly(invoice: Invoice) -> dict[str, Any]:
    """Return the stored anomaly result for an invoice without re-scoring."""
    return {
        "score": float(invoice.anomaly_score) if invoice.anomaly_score is not None else None,
        "flagged": bool(invoice.anomaly_flagged),
        "version": invoice.anomaly_model_version,
        "risk_level": invoice.risk_level,
        "reasons": invoice.anomaly_reasons or [],
        "features": None,
        "has_history": invoice.anomaly_score is not None,
        "threshold": None,
    }


def list_flagged(
    db: Session, *, tenant_id: uuid.UUID, limit: int = 100
) -> list[dict[str, Any]]:
    """Return flagged invoices (highest score first) for the review queue."""
    invoices = list(
        db.scalars(
            select(Invoice)
            .where(Invoice.tenant_id == tenant_id, Invoice.anomaly_flagged.is_(True))
            .order_by(Invoice.anomaly_score.desc())
            .limit(limit)
        ).all()
    )
    if not invoices:
        return []

    supplier_ids = {item.supplier_id for item in invoices if item.supplier_id}
    suppliers = (
        {
            supplier.id: supplier.name
            for supplier in db.scalars(
                select(Supplier).where(
                    Supplier.tenant_id == tenant_id, Supplier.id.in_(supplier_ids)
                )
            ).all()
        }
        if supplier_ids
        else {}
    )

    items = []
    for invoice in invoices:
        supplier_name = suppliers.get(invoice.supplier_id) if invoice.supplier_id else None
        if supplier_name is None:
            supplier_name = _fallback_supplier_name(invoice)
        items.append(
            {
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "supplier_name": supplier_name,
                "invoice_date": invoice.invoice_date,
                "currency": invoice.currency,
                "total_amount": invoice.total_amount,
                "state": invoice.state,
                "anomaly_score": (
                    float(invoice.anomaly_score) if invoice.anomaly_score is not None else None
                ),
                "anomaly_model_version": invoice.anomaly_model_version,
                "risk_level": invoice.risk_level,
                "reasons": invoice.anomaly_reasons or [],
            }
        )
    return items


def _fallback_supplier_name(invoice: Invoice) -> str | None:
    for source in (invoice.corrected_json, invoice.extracted_json):
        if isinstance(source, dict) and source.get("supplier_name"):
            return str(source["supplier_name"])
    return None


__all__ = [
    "AnomalyModelUnavailable",
    "list_flagged",
    "read_anomaly",
    "run_anomaly_detection",
    "score_invoice",
]
