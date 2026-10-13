from tests.helpers import PDF_BYTES, auth_headers, file_upload, login


def _upload(client, token, tenant_id, *, data: bytes = PDF_BYTES):
    return client.post(
        "/api/documents",
        files=file_upload(data, "invoice.pdf", "application/pdf"),
        headers=auth_headers(token, tenant_id),
    )


def test_upload_writes_audit_entry(client, seeded):
    token = login(client, "admin@acme.com")
    document = _upload(client, token, seeded["tenant_a"]).json()

    auditor_token = login(client, "auditor@acme.com")
    response = client.get("/api/audit", headers=auth_headers(auditor_token, seeded["tenant_a"]))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    entry = body["items"][0]
    assert entry["action"] == "document.uploaded"
    assert entry["entity_type"] == "document"
    assert entry["entity_id"] == document["id"]
    assert entry["actor_id"] == str(seeded["admin_a"])


def test_audit_requires_permission(client, seeded):
    token = login(client, "finance@acme.com")
    response = client.get("/api/audit", headers=auth_headers(token, seeded["tenant_a"]))
    assert response.status_code == 403


def test_audit_is_tenant_scoped(client, seeded):
    token_a = login(client, "admin@acme.com")
    _upload(client, token_a, seeded["tenant_a"])

    token_b = login(client, "admin@globex.com")
    response = client.get("/api/audit", headers=auth_headers(token_b, seeded["tenant_b"]))
    assert response.status_code == 200
    assert response.json()["total"] == 0
