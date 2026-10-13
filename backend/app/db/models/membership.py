import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Links a user to a tenant with a role. This is the source of tenant authority."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
        CheckConstraint("status in ('active', 'invited', 'disabled')", name="ck_membership_status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )

    tenant: Mapped["Tenant"] = relationship(lazy="joined")  # noqa: F821
    user: Mapped["User"] = relationship(back_populates="memberships", lazy="joined")  # noqa: F821
    role: Mapped["Role"] = relationship(lazy="joined")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<TenantMembership tenant={self.tenant_id} user={self.user_id}>"
