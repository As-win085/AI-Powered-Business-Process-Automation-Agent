import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserRead


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime


class TenantMembershipRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role_name: str
    status: str
    tenant: TenantRead


class MemberRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role_name: str
    status: str
    user: UserRead


class MeResponse(BaseModel):
    user: UserRead
    memberships: list[TenantMembershipRead]
