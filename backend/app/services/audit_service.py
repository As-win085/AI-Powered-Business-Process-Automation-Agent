import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AuditLog


def log_audit(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    action: str,
    entity_type: str,
    actor_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an audit entry for a tenant-scoped action.

    The caller's transaction is used, so an audit entry is committed only when
    the surrounding operation succeeds.
    """
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        details=details or {},
    )
    db.add(entry)
    db.flush()
    return entry


def list_audit_logs(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[AuditLog], int]:
    base = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = base.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), total
