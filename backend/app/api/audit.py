from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.core.tenant_context import TenantContext
from app.db.session import get_db
from app.schemas.audit import AuditLogListResponse, AuditLogRead
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    context: TenantContext = Depends(require_permission(Permission.AUDIT_READ)),
    db: Session = Depends(get_db),
) -> AuditLogListResponse:
    """List audit entries for the active tenant, newest first."""
    entries, total = audit_service.list_audit_logs(
        db, context.tenant_id, limit=limit, offset=offset
    )
    return AuditLogListResponse(
        items=[AuditLogRead.model_validate(entry) for entry in entries],
        total=total,
        limit=limit,
        offset=offset,
    )
