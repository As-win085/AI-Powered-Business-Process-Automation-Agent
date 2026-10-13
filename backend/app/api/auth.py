import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import UnauthorizedError
from app.core.security import TokenError, decode_token
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.schemas.tenant import MeResponse
from app.schemas.user import UserRead
from app.services import auth_service, tenant_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        raise UnauthorizedError("Invalid email or password")
    return TokenResponse(**auth_service.issue_tokens(user))


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired refresh token") from exc

    if claims.get("type") != "refresh":
        raise UnauthorizedError("Invalid token type")

    subject = claims.get("sub")
    try:
        user_id = uuid.UUID(subject) if subject else None
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError("Invalid token subject") from exc

    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return TokenResponse(**auth_service.issue_tokens(user))


@router.get("/me", response_model=MeResponse)
def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    memberships = tenant_service.list_memberships_for_user(db, user.id)
    return MeResponse(
        user=UserRead.model_validate(user),
        memberships=[tenant_service.serialize_membership(m) for m in memberships],
    )
