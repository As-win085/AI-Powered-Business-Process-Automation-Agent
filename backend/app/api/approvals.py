"""Approval queue and decision endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.core.tenant_context import TenantContext
from app.db.models import Approval, Invoice
from app.db.session import get_db
from app.schemas.approval import (
    ApprovalDecisionRequest,
    ApprovalListRead,
    ApprovalRead,
    DecisionFilter,
)
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _to_read(approval: Approval, invoice: Invoice, supplier_name: str | None) -> ApprovalRead:
    read = ApprovalRead.model_validate(approval)
    read.invoice_number = invoice.invoice_number
    read.total_amount = invoice.total_amount
    read.currency = invoice.currency
    read.invoice_state = invoice.state
    read.supplier_name = supplier_name
    return read


@router.get("", response_model=ApprovalListRead)
def list_approval_queue(
    scope: DecisionFilter = Query(default="pending"),
    assigned_to_me: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.APPROVAL_DECIDE)),
):
    """List approvals for the tenant, defaulting to the open queue."""
    rows, total = approval_service.list_approvals(
        db,
        context.tenant_id,
        scope=scope,
        assigned_to=context.user.id if assigned_to_me else None,
        limit=limit,
        offset=offset,
    )
    items = [
        _to_read(approval, invoice, supplier_name)
        for approval, invoice, supplier_name in rows
    ]
    return ApprovalListRead(items=items, total=total)


@router.get("/{approval_id}", response_model=ApprovalRead)
def get_approval(
    approval_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.APPROVAL_DECIDE)),
):
    row = approval_service.get_approval_context(db, context.tenant_id, approval_id)
    if row is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Approval not found")
    return _to_read(*row)


@router.post("/{approval_id}/decision", response_model=ApprovalRead)
def submit_decision(
    approval_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_permission(Permission.APPROVAL_DECIDE)),
):
    """Approve, reject, or request a correction. The server enforces all guards."""
    approval_service.decide_approval(
        db,
        context.tenant_id,
        approval_id,
        actor_id=context.user.id,
        decision=payload.decision,
        comment=payload.comment,
    )
    db.commit()

    row = approval_service.get_approval_context(db, context.tenant_id, approval_id)
    assert row is not None  # just decided in this transaction
    return _to_read(*row)
