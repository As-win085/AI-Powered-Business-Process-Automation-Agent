import os
import tempfile

# Must be set before app.core.config is imported anywhere.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://automation:automation@localhost:5432/automation_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")
os.environ.setdefault("STORAGE_ROOT", tempfile.mkdtemp(prefix="automation-test-storage-"))
os.environ.setdefault("AUTO_PROCESS_DOCUMENTS", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import Tenant, TenantMembership, User  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.tenant_service import ensure_system_roles  # noqa: E402

TEST_PASSWORD = "Password123!"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    import app.db.models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_db():
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded(db):
    roles = ensure_system_roles(db)

    tenant_a = Tenant(name="Acme Corp", slug="acme")
    tenant_b = Tenant(name="Globex GmbH", slug="globex")
    db.add_all([tenant_a, tenant_b])
    db.flush()

    admin_a = User(
        email="admin@acme.com",
        password_hash=hash_password(TEST_PASSWORD),
        full_name="Acme Admin",
    )
    finance_a = User(
        email="finance@acme.com",
        password_hash=hash_password(TEST_PASSWORD),
        full_name="Acme Finance",
    )
    auditor_a = User(
        email="auditor@acme.com",
        password_hash=hash_password(TEST_PASSWORD),
        full_name="Acme Auditor",
    )
    admin_b = User(
        email="admin@globex.com",
        password_hash=hash_password(TEST_PASSWORD),
        full_name="Globex Admin",
    )
    db.add_all([admin_a, finance_a, auditor_a, admin_b])
    db.flush()

    db.add_all(
        [
            TenantMembership(tenant_id=tenant_a.id, user_id=admin_a.id, role_id=roles["admin"].id),
            TenantMembership(
                tenant_id=tenant_a.id, user_id=finance_a.id, role_id=roles["finance"].id
            ),
            TenantMembership(
                tenant_id=tenant_a.id, user_id=auditor_a.id, role_id=roles["auditor"].id
            ),
            TenantMembership(tenant_id=tenant_b.id, user_id=admin_b.id, role_id=roles["admin"].id),
        ]
    )
    db.commit()

    return {
        "tenant_a": tenant_a.id,
        "tenant_b": tenant_b.id,
        "admin_a": admin_a.id,
        "finance_a": finance_a.id,
        "auditor_a": auditor_a.id,
        "admin_b": admin_b.id,
    }
