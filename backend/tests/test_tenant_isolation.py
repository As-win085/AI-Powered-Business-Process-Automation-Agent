"""Cross-tenant isolation tests.

These are the Milestone 1 acceptance gate: a user in Tenant A must never be able
to read or modify Tenant B's records.
"""

from tests.helpers import auth_headers, login


def test_list_tenants_returns_only_own(client, seeded):
    token = login(client, "admin@acme.com")
    response = client.get("/api/tenants", headers=auth_headers(token))
    assert response.status_code == 200
    assert [m["tenant"]["slug"] for m in response.json()] == ["acme"]


def test_cannot_read_other_tenant(client, seeded):
    token = login(client, "admin@acme.com")
    response = client.get(f"/api/tenants/{seeded['tenant_b']}", headers=auth_headers(token))
    assert response.status_code == 404


def test_cannot_list_other_tenant_members(client, seeded):
    token = login(client, "admin@acme.com")
    response = client.get(f"/api/tenants/{seeded['tenant_b']}/members", headers=auth_headers(token))
    assert response.status_code == 404


def test_forged_tenant_header_cannot_switch_tenant(client, seeded):
    token = login(client, "admin@acme.com")
    response = client.get(
        "/api/tenants/current",
        headers=auth_headers(token, tenant_id=seeded["tenant_b"]),
    )
    # The header is only a hint; membership in Tenant B does not exist -> 404.
    assert response.status_code == 404


def test_tenant_context_defaults_to_first_membership(client, seeded):
    token = login(client, "admin@acme.com")
    response = client.get("/api/tenants/current", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.json()["slug"] == "acme"


def test_tenant_context_accepts_valid_membership_header(client, seeded):
    token = login(client, "admin@acme.com")
    response = client.get(
        "/api/tenants/current", headers=auth_headers(token, tenant_id=seeded["tenant_a"])
    )
    assert response.status_code == 200
    assert response.json()["slug"] == "acme"


def test_member_without_permission_is_forbidden(client, seeded):
    token = login(client, "finance@acme.com")
    response = client.get(f"/api/tenants/{seeded['tenant_a']}/members", headers=auth_headers(token))
    assert response.status_code == 403


def test_admin_can_list_own_tenant_members(client, seeded):
    token = login(client, "admin@acme.com")
    response = client.get(f"/api/tenants/{seeded['tenant_a']}/members", headers=auth_headers(token))
    assert response.status_code == 200
    emails = {member["user"]["email"] for member in response.json()}
    assert emails == {"admin@acme.com", "finance@acme.com", "auditor@acme.com"}


def test_unauthenticated_tenant_access_is_rejected(client, seeded):
    assert client.get("/api/tenants").status_code == 401
    assert client.get(f"/api/tenants/{seeded['tenant_a']}").status_code == 401
