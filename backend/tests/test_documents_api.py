import hashlib

from app.core.config import settings
from tests.helpers import PDF_BYTES, PNG_BYTES, auth_headers, file_upload, login


def _upload(
    client,
    token,
    tenant_id,
    *,
    data: bytes = PDF_BYTES,
    filename: str = "invoice.pdf",
    content_type: str = "application/pdf",
    document_type: str = "invoice",
):
    return client.post(
        "/api/documents",
        params={"document_type": document_type},
        files=file_upload(data, filename, content_type),
        headers=auth_headers(token, tenant_id),
    )


def test_upload_requires_authentication(client):
    response = client.post(
        "/api/documents",
        files=file_upload(PDF_BYTES, "invoice.pdf", "application/pdf"),
    )
    assert response.status_code == 401


def test_upload_success_and_file_stored(client, seeded):
    token = login(client, "admin@acme.com")
    response = _upload(client, token, seeded["tenant_a"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_type"] == "invoice"
    assert body["status"] == "uploaded"
    assert body["size_bytes"] == len(PDF_BYTES)
    assert body["file_hash"] == hashlib.sha256(PDF_BYTES).hexdigest()
    assert body["uploaded_by"] == str(seeded["admin_a"])
    assert "storage_key" not in body  # internal storage location is never exposed

    stored_path = settings.storage_root / "documents" / str(seeded["tenant_a"])
    stored_files = list(stored_path.glob(f"{body['id']}*"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == PDF_BYTES


def test_auditor_role_cannot_upload(client, seeded):
    token = login(client, "auditor@acme.com")
    response = _upload(client, token, seeded["tenant_a"])
    assert response.status_code == 403


def test_upload_rejects_unsupported_extension(client, seeded):
    token = login(client, "admin@acme.com")
    response = _upload(client, token, seeded["tenant_a"], filename="malware.exe")
    assert response.status_code == 422


def test_upload_rejects_content_extension_mismatch(client, seeded):
    token = login(client, "admin@acme.com")
    response = _upload(
        client, token, seeded["tenant_a"], data=PNG_BYTES, content_type="application/pdf"
    )
    assert response.status_code == 422


def test_upload_rejects_declared_mime_mismatch(client, seeded):
    token = login(client, "admin@acme.com")
    response = _upload(client, token, seeded["tenant_a"], content_type="image/png")
    assert response.status_code == 422


def test_upload_rejects_oversized_file(client, seeded, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    token = login(client, "admin@acme.com")
    response = _upload(client, token, seeded["tenant_a"])
    assert response.status_code == 413


def test_duplicate_upload_conflicts(client, seeded):
    token = login(client, "admin@acme.com")
    first = _upload(client, token, seeded["tenant_a"])
    assert first.status_code == 201

    second = _upload(client, token, seeded["tenant_a"], filename="copy.pdf")
    assert second.status_code == 409


def test_list_documents_envelope_and_pagination(client, seeded):
    token = login(client, "admin@acme.com")
    for index in range(3):
        response = _upload(client, token, seeded["tenant_a"], data=PDF_BYTES + str(index).encode())
        assert response.status_code == 201

    page_one = client.get(
        "/api/documents",
        params={"limit": 2, "offset": 0},
        headers=auth_headers(token, seeded["tenant_a"]),
    )
    assert page_one.status_code == 200
    body = page_one.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2

    page_two = client.get(
        "/api/documents",
        params={"limit": 2, "offset": 2},
        headers=auth_headers(token, seeded["tenant_a"]),
    )
    assert len(page_two.json()["items"]) == 1


def test_list_documents_filters_by_type(client, seeded):
    token = login(client, "admin@acme.com")
    assert _upload(client, token, seeded["tenant_a"], document_type="invoice").status_code == 201
    assert (
        _upload(
            client,
            token,
            seeded["tenant_a"],
            data=PDF_BYTES + b"receipt",
            document_type="receipt",
        ).status_code
        == 201
    )

    response = client.get(
        "/api/documents",
        params={"document_type": "receipt"},
        headers=auth_headers(token, seeded["tenant_a"]),
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["document_type"] == "receipt"


def test_get_document_is_tenant_scoped(client, seeded):
    token_a = login(client, "admin@acme.com")
    created = _upload(client, token_a, seeded["tenant_a"]).json()

    token_b = login(client, "admin@globex.com")
    response = client.get(
        f"/api/documents/{created['id']}",
        headers=auth_headers(token_b, seeded["tenant_b"]),
    )
    assert response.status_code == 404


def test_download_streams_stored_file(client, seeded):
    token = login(client, "admin@acme.com")
    created = _upload(client, token, seeded["tenant_a"]).json()

    response = client.get(
        f"/api/documents/{created['id']}/download",
        headers=auth_headers(token, seeded["tenant_a"]),
    )
    assert response.status_code == 200
    assert response.content == PDF_BYTES
