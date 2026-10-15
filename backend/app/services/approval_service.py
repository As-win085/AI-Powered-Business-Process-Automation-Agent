"""Approval queue and decision handling.

Server-side enforcement (the client is never trusted):

* only the assigned approver may decide;
* the invoice must currently be in ``pending_approval``;
* a decision cannot be submitted twice - the approval row is locked with
  ``SELECT ... FOR UPDATE`` and a partial unique index stops a second *open*
  approval from being created for the same invoice;
* the user who uploaded the invoice's document cannot approve it;
* a comment is required to reject (enforced here and in the schema).
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.workflow import InvoiceState
from app.db.models import Approval, ApprovalHistory, Document, Invoice, Supplier
from app.services import audit_service
from app.services.workflow_service import resolve_approver, transition_invoice

_PENDING = "pending"
_DECISION_TO_STATE = {
    "approved": InvoiceState.APPROVED.value,
    "rejected": InvoiceState.REJECTED.value,
    "correction_requested": InvoiceState.CORRECTION_REQUESTED.value,
}


def _get_invoice(db: Session, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
    invoice = db.scalars(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
    ).first()
    if invoice is None:
        raise NotFoundError("Invoice not found")
    return invoice


def get_submitter_id(db: Session, tenant_id: uuid.UUID, invoice: Invoice) -> uuid.UUID | None:
    """Return the user who uploaded the document behind an invoice, if any."""
    if invoice.document_id is None:
        return None
    return db.scalar(
        select(Document.uploaded_by).where(
            Document.id == invoice.document_id, Document.tenant_id == tenant_id
        )
    )


def submit_for_approval(
    db: Session,
    tenant_id: uuid.UUID,
    invoice: Invoice,
    *,
    actor_id: uuid.UUID,
) -> Approval:
    """Move a validated/reviewed invoice into ``pending_approval`` and route it."""
    if invoice.tenant_id != tenant_id:
        raise NotFoundError("Invoice not found")

    existing = db.scalars(
        select(Approval).where(
            Approval.tenant_id == tenant_id,
            Approval.invoice_id == invoice.id,
            Approval.decision == _PENDING,
        )
    ).first()
    if existing is not None:
        raise ConflictError("Invoice already has an open approval")

    submitter_id = get_submitter_id(db, tenant_id, invoice)
    approver_id, role_name = resolve_approver(
        db, tenant_id, invoice.total_amount, exclude_user_id=submitter_id
    )

    from_state = invoice.state
    transition_invoice(
        db,
        invoice,
        InvoiceState.PENDING_APPROVAL.value,
        actor_id=actor_id,
        details={"approver_id": str(approver_id) if approver_id else None, "role": role_name},
    )

    approval = Approval(
        tenant_id=tenant_id,
        invoice_id=invoice.id,
        approver_id=approver_id,
        decision=_PENDING,
        comment=None,
        metadata_json={
            "routed_role": role_name,
            "amount": str(invoice.total_amount) if invoice.total_amount is not None else None,
        },
    )
    db.add(approval)
    db.flush()

    db.add(
        ApprovalHistory(
            tenant_id=tenant_id,
            approval_id=approval.id,
            actor_id=actor_id,
            from_state=from_state,
            to_state=InvoiceState.PENDING_APPROVAL.value,
            comment=None,
        )
    )
    return approval


def list_approvals(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    scope: str = "pending",
    assigned_to: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[Approval, Invoice, str | None]], int]:
    """Return ``(approval, invoice, supplier_name)`` rows for the queue."""
    conditions = [Approval.tenant_id == tenant_id]
    if scope == "pending":
        conditions.append(Approval.decision == _PENDING)
    elif scope == "decided":
        conditions.append(Approval.decision != _PENDING)
    if assigned_to is not None:
        conditions.append(Approval.approver_id == assigned_to)

    base = (
        select(Approval, Invoice, Supplier.name)
        .join(
            Invoice,
            and_(Invoice.id == Approval.invoice_id, Invoice.tenant_id == Approval.tenant_id),
        )
        .outerjoin(
            Supplier,
            and_(Supplier.id == Invoice.supplier_id, Supplier.tenant_id == Invoice.tenant_id),
        )
        .where(*conditions)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(Approval.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return [(row[0], row[1], row[2]) for row in rows], total


def get_approval_context(
    db: Session, tenant_id: uuid.UUID, approval_id: uuid.UUID
) -> tuple[Approval, Invoice, str | None] | None:
    """Load ``(approval, invoice, supplier_name)`` for response rendering."""
    row = db.execute(
        select(Approval, Invoice, Supplier.name)
        .join(
            Invoice,
            and_(Invoice.id == Approval.invoice_id, Invoice.tenant_id == Approval.tenant_id),
        )
        .outerjoin(
            Supplier,
            and_(Supplier.id == Invoice.supplier_id, Supplier.tenant_id == Invoice.tenant_id),
        )
        .where(Approval.id == approval_id, Approval.tenant_id == tenant_id)
    ).first()
    return (row[0], row[1], row[2]) if row is not None else None


def decide_approval(
    db: Session,
    tenant_id: uuid.UUID,
    approval_id: uuid.UUID,
    *,
    actor_id: uuid.UUID,
    decision: str,
    comment: str | None = None,
) -> Approval:
    """Record a decision, enforcing every server-side guard."""
    if decision not in _DECISION_TO_STATE:
        raise ValidationError(f"Invalid decision: {decision}")
    if decision in ("rejected", "correction_requested") and not (comment and comment.strip()):
        raise ValidationError("A comment is required when rejecting an invoice")

    # Lock the row so two concurrent decisions cannot both win.
    approval = db.scalars(
        select(Approval)
        .where(Approval.id == approval_id, Approval.tenant_id == tenant_id)
        .with_for_update()
    ).first()
    if approval is None:
        raise NotFoundError("Approval not found")

    invoice = _get_invoice(db, tenant_id, approval.invoice_id)

    if approval.decision != _PENDING:
        raise ConflictError("This approval has already been decided")
    if invoice.state != InvoiceState.PENDING_APPROVAL.value:
        raise ConflictError("Invoice is not pending approval")
    if approval.approver_id is None or approval.approver_id != actor_id:
        raise ForbiddenError("You are not the assigned approver for this invoice")

    submitter_id = get_submitter_id(db, tenant_id, invoice)
    if submitter_id is not None and submitter_id == actor_id:
        raise ForbiddenError("You cannot approve an invoice you uploaded")

    target_state = _DECISION_TO_STATE[decision]
    from_state = invoice.state
    transition_invoice(
        db,
        invoice,
        target_state,
        actor_id=actor_id,
        details={"approval_id": str(approval.id), "decision": decision},
    )

    approval.decision = decision
    approval.comment = comment
    approval.decided_at = func.now()
    db.add(approval)

    db.add(
        ApprovalHistory(
            tenant_id=tenant_id,
            approval_id=approval.id,
            actor_id=actor_id,
            from_state=from_state,
            to_state=target_state,
            comment=comment,
        )
    )
    audit_service.log_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type="approval",
        entity_id=approval.id,
        action=f"approval.{decision}",
        details={"invoice_id": str(invoice.id), "comment": comment},
    )
    db.flush()
    return approval


__all__ = [
    "decide_approval",
    "get_approval_context",
    "get_submitter_id",
    "list_approvals",
    "submit_for_approval",
]
