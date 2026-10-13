"""Seed demo data for local development.

Usage (from the backend/ directory, with the virtualenv activated):

    python -m scripts.seed

Creates two tenants and three users. Idempotent: existing records are left as-is.
"""

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import Tenant, TenantMembership, User
from app.db.session import SessionLocal
from app.services.tenant_service import ensure_system_roles

DEMO_PASSWORD = "Password123!"


def get_or_create_tenant(db, name: str, slug: str) -> Tenant:
    tenant = db.scalars(select(Tenant).where(Tenant.slug == slug)).first()
    if tenant is None:
        tenant = Tenant(name=name, slug=slug)
        db.add(tenant)
        db.flush()
    return tenant


def get_or_create_user(db, email: str, full_name: str) -> User:
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(DEMO_PASSWORD),
            full_name=full_name,
        )
        db.add(user)
        db.flush()
    return user


def ensure_membership(db, tenant: Tenant, user: User, role_id) -> None:
    existing = db.scalars(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == user.id,
        )
    ).first()
    if existing is None:
        db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role_id=role_id))


def main() -> None:
    db = SessionLocal()
    try:
        roles = ensure_system_roles(db)

        acme = get_or_create_tenant(db, "Acme Corp", "acme")
        globex = get_or_create_tenant(db, "Globex GmbH", "globex")

        admin_a = get_or_create_user(db, "admin@acme.com", "Acme Admin")
        finance_a = get_or_create_user(db, "finance@acme.com", "Acme Finance")
        admin_b = get_or_create_user(db, "admin@globex.com", "Globex Admin")

        ensure_membership(db, acme, admin_a, roles["admin"].id)
        ensure_membership(db, acme, finance_a, roles["finance"].id)
        ensure_membership(db, globex, admin_b, roles["admin"].id)

        db.commit()
        print("Demo data ready.")
        print(f"  admin@acme.com / {DEMO_PASSWORD}   (Acme admin)")
        print(f"  finance@acme.com / {DEMO_PASSWORD} (Acme finance)")
        print(f"  admin@globex.com / {DEMO_PASSWORD} (Globex admin)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
