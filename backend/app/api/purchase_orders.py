"""Purchase order API endpoints (CRUD + CSV import)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.core.tenant_context import TenantContext
from app.db.session import get_db
from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderImportResult,
    PurchaseOrderListRead,
    PurchaseOrderRead,
    PurchaseOrderUpdate,
)
from app.services import audit_service, purchase_order_service
from app.services.purchase_order_service import PurchaseOrderError

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


def _get_or_404(db: Session, tenant_id: uuid.UUID, po_id: uuid.UUID):
    po = purchase_order_service.get_purchase_order(db, tenant_id, po_id)
    if po is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found"
        )
    return po


@router.post("", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.PURCHASE_ORDER_WRITE)),
):
    """Create a purchase order with optional line items."""
    try:
        po = purchase_order_service.create_purchase_order(db, context.tenant_id, payload)
    except PurchaseOrderError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    audit_service.log_audit(
        db,
        tenant_id=context.tenant_id,
        actor_id=context.user.id,
        entity_type="purchase_order",
        entity_id=po.id,
        action="purchase_order.create",
        details={"po_number": po.po_number, "status": po.status},
    )
    db.commit()
    db.refresh(po)
    return po


@router.get("", response_model=PurchaseOrderListRead)
def list_purchase_orders(
    status_filter: str | None = Query(None, alias="status"),
    supplier_id: uuid.UUID | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.PURCHASE_ORDER_READ)),
):
    total, rows = purchase_order_service.list_purchase_orders(
        db,
        context.tenant_id,
        status=status_filter,
        supplier_id=supplier_id,
        query=q,
        limit=limit,
        offset=offset,
    )
    return PurchaseOrderListRead(total=total, items=rows)


@router.post("/import", response_model=PurchaseOrderImportResult)
async def import_purchase_orders(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.PURCHASE_ORDER_WRITE)),
):
    """Import purchase orders from a CSV (one row per PO line item)."""
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty CSV file"
        )
    try:
        result = purchase_order_service.import_purchase_orders_csv(
            db, context.tenant_id, content
        )
    except PurchaseOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    audit_service.log_audit(
        db,
        tenant_id=context.tenant_id,
        actor_id=context.user.id,
        entity_type="purchase_order",
        entity_id=None,
        action="purchase_order.import",
        details={
            "created": result.created,
            "skipped": result.skipped,
            "errors": [e.model_dump() for e in result.errors],
        },
    )
    db.commit()
    return result


@router.get("/{po_id}", response_model=PurchaseOrderRead)
def get_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.PURCHASE_ORDER_READ)),
):
    return _get_or_404(db, context.tenant_id, po_id)


@router.patch("/{po_id}", response_model=PurchaseOrderRead)
def update_purchase_order(
    po_id: uuid.UUID,
    payload: PurchaseOrderUpdate,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.PURCHASE_ORDER_WRITE)),
):
    po = _get_or_404(db, context.tenant_id, po_id)
    try:
        purchase_order_service.update_purchase_order(
            db, context.tenant_id, po, payload.model_dump(exclude_unset=True)
        )
    except PurchaseOrderError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    audit_service.log_audit(
        db,
        tenant_id=context.tenant_id,
        actor_id=context.user.id,
        entity_type="purchase_order",
        entity_id=po.id,
        action="purchase_order.update",
        details={"po_number": po.po_number, "status": po.status},
    )
    db.commit()
    db.refresh(po)
    return po


@router.delete("/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.PURCHASE_ORDER_WRITE)),
):
    po = _get_or_404(db, context.tenant_id, po_id)
    audit_service.log_audit(
        db,
        tenant_id=context.tenant_id,
        actor_id=context.user.id,
        entity_type="purchase_order",
        entity_id=po.id,
        action="purchase_order.delete",
        details={"po_number": po.po_number},
    )
    purchase_order_service.delete_purchase_order(db, context.tenant_id, po)
    db.commit()
    return None
