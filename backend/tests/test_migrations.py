"""Migration tests run against a throwaway database so they never touch dev data."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "tenants",
    "users",
    "roles",
    "permissions",
    "role_permissions",
    "tenant_memberships",
}


@pytest.fixture
def temp_database():
    base_url = make_url(settings.database_url)
    maintenance_url = base_url.set(database="postgres")
    db_name = f"migration_test_{uuid.uuid4().hex[:8]}"

    admin_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    temp_url = base_url.set(database=db_name)
    try:
        yield temp_url
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin_engine.dispose()


def _alembic_config(url) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    return config


def test_migrations_upgrade_and_downgrade(temp_database):
    config = _alembic_config(temp_database)

    command.upgrade(config, "head")
    engine = create_engine(temp_database)
    tables = set(inspect(engine).get_table_names())
    assert tables >= EXPECTED_TABLES

    command.downgrade(config, "base")
    remaining = set(inspect(engine).get_table_names())
    assert not (EXPECTED_TABLES & remaining)
    engine.dispose()


def test_membership_uniqueness_is_enforced(temp_database):
    config = _alembic_config(temp_database)
    command.upgrade(config, "head")
    engine = create_engine(temp_database)

    with engine.begin() as connection:
        tenant_id = connection.execute(
            text(
                "INSERT INTO tenants (id, name, slug, settings) "
                "VALUES (gen_random_uuid(), 'T', 't', '{}') RETURNING id"
            )
        ).scalar_one()
        user_id = connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash) "
                "VALUES (gen_random_uuid(), 'u@test', 'x') RETURNING id"
            )
        ).scalar_one()
        role_id = connection.execute(
            text(
                "INSERT INTO roles (id, name, tenant_id, is_system) "
                "VALUES (gen_random_uuid(), 'admin', NULL, true) RETURNING id"
            )
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO tenant_memberships (id, tenant_id, user_id, role_id) "
                "VALUES (gen_random_uuid(), :t, :u, :r)"
            ),
            {"t": tenant_id, "u": user_id, "r": role_id},
        )

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tenant_memberships (id, tenant_id, user_id, role_id) "
                "VALUES (gen_random_uuid(), :t, :u, :r)"
            ),
            {"t": tenant_id, "u": user_id, "r": role_id},
        )
    engine.dispose()
