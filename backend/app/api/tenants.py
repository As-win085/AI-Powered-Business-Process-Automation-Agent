import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_tenant_context
from app.core.permissions import Permission
from app.core.tenant_context import TenantContext, build_context
from app.db.models import User
from app.db.session import get_db
from app.schemas.tenant import MemberRead, TenantMembershipRead, TenantRead
from app.services import tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantMembershipRead])
def list_my_tenants(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TenantMembershipRead]:
    """Return only the tenants the caller has an active membership in."""
    memberships = tenant_service.list_memberships_for_user(db, user.id)
    return [tenant_service.serialize_membership(m) for m in memberships]


@router.get("/current", response_model=TenantRead)
def get_current_tenant(
    context: TenantContext = Depends(get_tenant_context),
) -> TenantRead:
    """Return the active tenant resolved from a validated membership.

    The optional X-Tenant-Id header is a hint validated against the caller's
    memberships; it can never grant access to a tenant the caller does not belong to.
    """
    return TenantRead.model_validate(context.tenant)


@router.get("/{tenant_id}", response_model=TenantRead)
def get_tenant(
    tenant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantRead:
    # require_membership raises 404 for tenants the caller does not belong to.
    membership = tenant_service.require_membership(db, user.id, tenant_id)
    return TenantRead.model_validate(membership.tenant)


@router.get("/{tenant_id}/members", response_model=list[MemberRead])
def list_tenant_members(
    tenant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MemberRead]:
    # 404 for non-members (cross-tenant isolation), 403 for members without permission.
    membership = tenant_service.require_membership(db, user.id, tenant_id)
    context = build_context(user, membership)
    context.require_permission(Permission.TENANT_MANAGE_MEMBERS)

    members = tenant_service.list_members(db, tenant_id)
    return [tenant_service.serialize_member(m) for m in members]
