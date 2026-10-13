from tests.helpers import auth_headers, file_upload, login
from tests.pdf_fixtures import make_corrupt_pdf, make_digital_pdf, make_password_protected_pdf


def _upload(client, token, tenant_id, *, data: bytes, filename: str = "invoice.pdf"):
    response = client.post(
        "/api/documents",
        files=file_upload(data, filename, "application/pdf"),
        headers=auth_headers(token, tenant_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_process_extracts_and_stores_page_text(client, seeded):
    token = login(client, "admin@acme.com")
    document = _upload(client, token, seeded["tenant_a"], data=make_digital_pdf())

    processed = client.post(
        f"/api/documents/{document['id']}/process",
        headers=auth_headers(token, seeded["tenant_a"]),
    )
    assert processed.status_code == 200, processed.text
    body = processed.json()
    assert body["status"] == "needs_review"
    assert body["error"] is None
    assert body["page_count"] == 2

    text = client.get(
        f"/api/documents/{document['id']}/text",
        headers=auth_headers(token, seeded["tenant_a"]),
    )
    assert text.status_code == 200
    pages = text.json()
    assert len(pages) == 2
    assert all(page["source"] == "embedded" for page in pages)
    assert pages[0]["engine"] == "pymupdf"
    assert pages[0]["page_number"] == 1
    assert "INVOICE 1" in pages[0]["text"]


def test_reprocessing_replaces_pages_not_duplicates(client, seeded):
    token = login(client, "admin@acme.com")
    document = _upload(client, token, seeded["tenant_a"], data=make_digital_pdf())

    for _ in range(2):
        response = client.post(
            f"/api/documents/{document['id']}/process",
            headers=auth_headers(token, seeded["tenant_a"]),
        )
        assert response.status_code == 200

    text = client.get(
        f"/api/documents/{document['id']}/text",
        headers=auth_headers(token, seeded["tenant_a"]),
    )
    assert len(text.json()) == 2


def test_password_protected_pdf_marks_document_failed(client, seeded):
    token = login(client, "admin@acme.com")
    document = _upload(client, token, seeded["tenant_a"], data=make_password_protected_pdf())

    response = client.post(
        f"/api/documents/{document['id']}/process",
        headers=auth_headers(token, seeded["tenant_a"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] is not None
    assert "password" in body["error"].lower()


def test_corrupt_pdf_marks_document_failed(client, seeded):
    token = login(client, "admin@acme.com")
    document = _upload(client, token, seeded["tenant_a"], data=make_corrupt_pdf())

    response = client.post(
        f"/api/documents/{document['id']}/process",
        headers=auth_headers(token, seeded["tenant_a"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] is not None


def test_text_and_process_are_tenant_scoped(client, seeded):
    token_a = login(client, "admin@acme.com")
    document = _upload(client, token_a, seeded["tenant_a"], data=make_digital_pdf())
    client.post(
        f"/api/documents/{document['id']}/process",
        headers=auth_headers(token_a, seeded["tenant_a"]),
    )

    token_b = login(client, "admin@globex.com")
    headers_b = auth_headers(token_b, seeded["tenant_b"])

    text = client.get(f"/api/documents/{document['id']}/text", headers=headers_b)
    assert text.status_code == 404

    process = client.post(f"/api/documents/{document['id']}/process", headers=headers_b)
    assert process.status_code == 404


def test_process_requires_upload_permission(client, seeded):
    admin_token = login(client, "admin@acme.com")
    document = _upload(client, admin_token, seeded["tenant_a"], data=make_digital_pdf())
    auditor_token = login(client, "auditor@acme.com")
    response = client.post(
        f"/api/documents/{document['id']}/process",
        headers=auth_headers(auditor_token, seeded["tenant_a"]),
    )
    assert response.status_code == 403


def test_unauthenticated_text_access_is_rejected(client, seeded):
    response = client.get(f"/api/documents/{'0' * 32}/text")
    assert response.status_code == 401
