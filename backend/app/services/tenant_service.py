import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError
from app.core.permissions import SYSTEM_ROLE_NAMES
from app.db.models import Role, TenantMembership
from app.schemas.tenant import MemberRead, TenantMembershipRead, TenantRead
from app.schemas.user import UserRead


def ensure_system_roles(db: Session) -> dict[str, Role]:
    """Create the global (tenant-independent) system roles if they do not exist."""
    roles: dict[str, Role] = {}
    for name in SYSTEM_ROLE_NAMES:
        role = db.scalars(select(Role).where(Role.name == name, Role.tenant_id.is_(None))).first()
        if role is None:
            role = Role(name=name, tenant_id=None, is_system=True)
            db.add(role)
            db.flush()
        roles[name] = role
    return roles


def list_memberships_for_user(db: Session, user_id: uuid.UUID) -> list[TenantMembership]:
    stmt = (
        select(TenantMembership)
        .where(
            TenantMembership.user_id == user_id,
            TenantMembership.status == "active",
        )
        .options(
            joinedload(TenantMembership.tenant),
            joinedload(TenantMembership.role),
        )
        .order_by(TenantMembership.created_at)
    )
    return list(db.scalars(stmt).unique().all())


def get_membership(
    db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> TenantMembership | None:
    stmt = (
        select(TenantMembership)
        .where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
        .options(
            joinedload(TenantMembership.tenant),
            joinedload(TenantMembership.role),
        )
    )
    return db.scalars(stmt).unique().first()


def require_membership(db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID) -> TenantMembership:
    """Return an active membership or raise NotFoundError.

    NotFoundError is intentional: it avoids leaking the existence of tenants the
    caller does not belong to.
    """
    membership = get_membership(db, user_id, tenant_id)
    if membership is None or membership.status != "active":
        raise NotFoundError("Tenant not found")
    return membership


def serialize_membership(membership: TenantMembership) -> TenantMembershipRead:
    return TenantMembershipRead(
        id=membership.id,
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        role_name=membership.role.name if membership.role else "",
        status=membership.status,
        tenant=TenantRead.model_validate(membership.tenant),
    )


def serialize_member(membership: TenantMembership) -> MemberRead:
    return MemberRead(
        id=membership.id,
        user_id=membership.user_id,
        role_name=membership.role.name if membership.role else "",
        status=membership.status,
        user=UserRead.model_validate(membership.user),
    )


def list_members(db: Session, tenant_id: uuid.UUID) -> list[TenantMembership]:
    stmt = (
        select(TenantMembership)
        .where(TenantMembership.tenant_id == tenant_id)
        .options(
            joinedload(TenantMembership.user),
            joinedload(TenantMembership.role),
        )
        .order_by(TenantMembership.created_at)
    )
    return list(db.scalars(stmt).unique().all())
