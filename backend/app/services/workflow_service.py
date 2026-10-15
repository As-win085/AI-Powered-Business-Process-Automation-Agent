"""Invoice workflow transitions and approver resolution.

All invoice state changes funnel through :func:`transition_invoice`, which
enforces the state machine in :mod:`app.core.workflow` and always writes an
audit entry. Approval routing delegates to :mod:`app.services.approval_policy`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.workflow import assert_transition
from app.db.models import Role, TenantMembership
from app.db.models.invoice import Invoice
from app.services import audit_service
from app.services.approval_policy import ApprovalPolicy, resolve_approver_role


def transition_invoice(
    db: Session,
    invoice: Invoice,
    to_state: str,
    *,
    actor_id: uuid.UUID | None,
    details: dict[str, Any] | None = None,
) -> Invoice:
    """Validate and apply an invoice state transition, then audit it."""
    from_state = invoice.state
    assert_transition(from_state, to_state)
    invoice.state = to_state
    db.add(invoice)
    audit_service.log_audit(
        db,
        tenant_id=invoice.tenant_id,
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="invoice.transition",
        details={
            "from_state": from_state,
            "to_state": to_state,
            **(details or {}),
        },
    )
    return invoice


def resolve_approver(
    db: Session,
    tenant_id: uuid.UUID,
    amount: Decimal | str | float | None,
    *,
    exclude_user_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID | None, str]:
    """Pick an approver for ``amount`` per policy.

    Returns ``(user_id, role_name)``. ``user_id`` is ``None`` when the tenant
    has no eligible member; the invoice still moves to ``pending_approval`` but
    nobody can act on it until one is added. The required role is tried first,
    then ``admin`` (a strict superset of authority) as a safe fallback.
    """
    policy = ApprovalPolicy.from_settings(settings)
    target_role = resolve_approver_role(amount, policy)
    for role_name in dict.fromkeys((target_role, policy.director_role)):
        stmt = (
            select(TenantMembership.user_id)
            .join(Role, Role.id == TenantMembership.role_id)
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == "active",
                Role.name == role_name,
            )
            .order_by(TenantMembership.created_at)
        )
        if exclude_user_id is not None:
            stmt = stmt.where(TenantMembership.user_id != exclude_user_id)
        user_id = db.scalars(stmt).first()
        if user_id is not None:
            return user_id, role_name
    return None, target_role
