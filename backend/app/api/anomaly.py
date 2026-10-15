"""Anomaly detection API: score an invoice, read its score, review the queue."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.invoices import _get_invoice_or_404
from app.core.permissions import Permission
from app.core.tenant_context import TenantContext
from app.db.session import get_db
from app.schemas.anomaly import (
    AnomalyModelInfo,
    AnomalyQueueRead,
    InvoiceAnomalyRead,
)
from app.services import anomaly_service, audit_service
from app.services.anomaly_model_store import load_model

router = APIRouter(tags=["anomaly"])


def _response(invoice: object, result: dict) -> InvoiceAnomalyRead:
    return InvoiceAnomalyRead(
        invoice_id=result.get("invoice_id", getattr(invoice, "id", None)),
        score=result.get("score"),
        flagged=result.get("flagged", False),
        model_version=result.get("version"),
        risk_level=result.get("risk_level"),
        has_history=result.get("has_history", False),
        threshold=result.get("threshold"),
        reasons=result.get("reasons", []),
        features=result.get("features"),
    )


@router.post("/invoices/{invoice_id}/score-anomaly", response_model=InvoiceAnomalyRead)
def score_invoice_anomaly(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_READ)),
):
    """Score an invoice against its supplier history (review flag only)."""
    invoice = _get_invoice_or_404(db, context.tenant_id, invoice_id)
    try:
        result = anomaly_service.run_anomaly_detection(
            db, tenant_id=context.tenant_id, invoice=invoice
        )
    except anomaly_service.AnomalyModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    audit_service.log_audit(
        db,
        tenant_id=context.tenant_id,
        actor_id=context.user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="invoice.score_anomaly",
        details={
            "score": result["score"],
            "flagged": result["flagged"],
            "version": result["version"],
        },
    )
    db.commit()
    db.refresh(invoice)
    return _response(invoice, {**result, "invoice_id": invoice.id})


@router.get("/invoices/{invoice_id}/anomaly", response_model=InvoiceAnomalyRead)
def get_invoice_anomaly(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_READ)),
):
    """Return the stored anomaly result for an invoice."""
    invoice = _get_invoice_or_404(db, context.tenant_id, invoice_id)
    result = anomaly_service.read_anomaly(invoice)
    return _response(invoice, {**result, "invoice_id": invoice.id})


@router.get("/anomalies", response_model=AnomalyQueueRead)
def list_anomalies(
    limit: int = 100,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.INVOICE_READ)),
):
    """Review queue of flagged invoices, highest anomaly score first."""
    items = anomaly_service.list_flagged(db, tenant_id=context.tenant_id, limit=limit)
    return {"total": len(items), "items": items}


@router.get("/anomaly/model", response_model=AnomalyModelInfo)
def anomaly_model_info(
    context: TenantContext = Depends(require_permission(Permission.INVOICE_READ)),
):
    """Describe the currently loaded anomaly model, if any."""
    model = load_model()
    if model is None:
        return {"trained": False, "feature_names": []}
    return {
        "trained": True,
        "version": model.version,
        "threshold": model.threshold,
        "feature_names": list(model.feature_names),
        "metadata": model.metadata,
    }
