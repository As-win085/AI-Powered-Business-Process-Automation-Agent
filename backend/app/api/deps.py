import uuid
from collections.abc import Callable

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.permissions import Permission
from app.core.security import TokenError, decode_token
from app.core.tenant_context import TenantContext, build_context
from app.db.models import User
from app.db.session import get_db
from app.services import tenant_service

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    subject = payload.get("sub")
    try:
        user_id = uuid.UUID(subject) if subject else None
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError("Invalid token subject") from exc

    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


def get_tenant_context(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Resolve the active tenant from a validated membership.

    The X-Tenant-Id header is treated as a *hint* only: the tenant is always
    derived from (and validated against) the caller's active membership.
    """
    if x_tenant_id:
        try:
            tenant_id = uuid.UUID(x_tenant_id)
        except ValueError as exc:
            raise ForbiddenError("Invalid tenant context") from exc
        membership = tenant_service.require_membership(db, user.id, tenant_id)
        return build_context(user, membership)

    memberships = tenant_service.list_memberships_for_user(db, user.id)
    if not memberships:
        raise ForbiddenError("User has no active tenant membership")
    return build_context(user, memberships[0])


def require_permission(permission: Permission) -> Callable[..., TenantContext]:
    def dependency(context: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        context.require_permission(permission)
        return context

    return dependency


def require_role(*role_names: str) -> Callable[..., TenantContext]:
    """Guard a route to callers whose active membership has one of ``role_names``."""
    allowed = set(role_names)

    def dependency(context: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if context.role_name not in allowed:
            raise ForbiddenError(f"Requires one of the roles: {', '.join(sorted(allowed))}")
        return context

    return dependency
