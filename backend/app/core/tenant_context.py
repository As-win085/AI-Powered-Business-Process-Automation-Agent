import uuid
from dataclasses import dataclass

from app.core.exceptions import ForbiddenError
from app.core.permissions import Permission, permissions_for_role
from app.db.models import Tenant, TenantMembership, User


@dataclass(frozen=True)
class TenantContext:
    """The resolved tenant scope for a request. Every service operation requires this."""

    tenant: Tenant
    membership: TenantMembership
    user: User
    role_name: str
    permissions: frozenset[Permission]

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.tenant.id

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require_permission(self, permission: Permission) -> None:
        if not self.has_permission(permission):
            raise ForbiddenError(f"Missing permission: {permission.value}")


def build_context(user: User, membership: TenantMembership) -> TenantContext:
    role_name = membership.role.name if membership.role is not None else ""
    return TenantContext(
        tenant=membership.tenant,
        membership=membership,
        user=user,
        role_name=role_name,
        permissions=frozenset(permissions_for_role(role_name)),
    )
