"""API tests for purchase order CRUD/import and invoice PO matching."""
import uuid

from app.core.security import hash_password
from app.db.models import Role, TenantMembership, User
from tests.helpers import auth_headers, file_upload, login

PASSWORD = "Password123!"


def _add_member(db, tenant_id: uuid.UUID, email: str, role_name: str) -> uuid.UUID:
    role = db.query(Role).filter(Role.name == role_name, Role.tenant_id.is_(None)).one()
    user = User(email=email, password_hash=hash_password(PASSWORD), full_name=email)
    db.add(user)
    db.flush()
    db.add(TenantMembership(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.commit()
    return user.id


def _create_po(
    client,
    token,
    tenant_id,
    *,
    po_number="PO-1001",
    supplier="Acme Supplies Ltd",
    items=None,
):
    return client.post(
        "/api/purchase-orders",
        json={
            "po_number": po_number,
            "supplier_name": supplier,
            "currency": "USD",
            "total_amount": "500.00",
            "line_items": items
            or [
                {
                    "line_number": 1,
                    "description": "Widget",
                    "quantity": "10",
                    "unit_price": "50.00",
                    "line_total": "500.00",
                }
            ],
        },
        headers=auth_headers(token, tenant_id),
    )


def _create_invoice(
    client, token, tenant_id, *, number="INV-100", po_number=None, total="500.00", items=None
):
    payload = {
        "supplier_name": "Acme Supplies Ltd",
        "invoice_number": number,
        "currency": "USD",
        "subtotal": total,
        "total_amount": total,
    }
    if po_number is not None:
        payload["po_number"] = po_number
    if items is not None:
        payload["line_items"] = items
    return client.post(
        "/api/invoices", json=payload, headers=auth_headers(token, tenant_id)
    )


def test_create_list_and_get_purchase_order(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")

    response = _create_po(client, token, tenant_a)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["po_number"] == "PO-1001"
    assert body["status"] == "open"
    assert len(body["line_items"]) == 1
    po_id = body["id"]

    listing = client.get("/api/purchase-orders", headers=auth_headers(token, tenant_a))
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1

    fetched = client.get(
        f"/api/purchase-orders/{po_id}", headers=auth_headers(token, tenant_a)
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == po_id


def test_duplicate_po_number_conflicts(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")
    assert _create_po(client, token, tenant_a).status_code == 201
    response = _create_po(client, token, tenant_a)
    assert response.status_code == 409


def test_update_and_delete_purchase_order(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")
    po_id = _create_po(client, token, tenant_a).json()["id"]

    updated = client.patch(
        f"/api/purchase-orders/{po_id}",
        json={"status": "closed", "total_amount": "600.00"},
        headers=auth_headers(token, tenant_a),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "closed"
    assert updated.json()["total_amount"] == "600.00"

    deleted = client.delete(
        f"/api/purchase-orders/{po_id}", headers=auth_headers(token, tenant_a)
    )
    assert deleted.status_code == 204
    missing = client.get(
        f"/api/purchase-orders/{po_id}", headers=auth_headers(token, tenant_a)
    )
    assert missing.status_code == 404


def test_csv_import_groups_lines_and_skips_duplicates(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")

    csv_content = (
        "po_number,supplier_name,currency,total_amount,status,line_number,"
        "description,quantity,unit_price,line_total\n"
        "PO-2001,Acme Supplies Ltd,USD,300.00,open,1,Bolt,10,20.00,200.00\n"
        "PO-2001,Acme Supplies Ltd,USD,300.00,open,2,Nut,20,5.00,100.00\n"
        "PO-2002,Globex GmbH,EUR,150.00,open,1,Gear,3,50.00,150.00\n"
    )
    response = client.post(
        "/api/purchase-orders/import",
        files=file_upload(csv_content.encode(), "pos.csv", "text/csv"),
        headers=auth_headers(token, tenant_a),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created"] == 2
    assert result["skipped"] == []

    listing = client.get("/api/purchase-orders", headers=auth_headers(token, tenant_a))
    assert listing.json()["total"] == 2

    # Re-importing the same file skips existing PO numbers.
    again = client.post(
        "/api/purchase-orders/import",
        files=file_upload(csv_content.encode(), "pos.csv", "text/csv"),
        headers=auth_headers(token, tenant_a),
    )
    assert again.json()["created"] == 0
    assert set(again.json()["skipped"]) == {"PO-2001", "PO-2002"}

    detail = client.get(
        f"/api/purchase-orders/{listing.json()['items'][0]['id']}",
        headers=auth_headers(token, tenant_a),
    )
    assert detail.status_code == 200


def test_po_is_tenant_isolated(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    tenant_b = seeded["tenant_b"]
    token_a = login(client, "finance@acme.com")
    token_b = login(client, "admin@globex.com")

    po_id = _create_po(client, token_a, tenant_a).json()["id"]
    response = client.get(
        f"/api/purchase-orders/{po_id}", headers=auth_headers(token_b, tenant_b)
    )
    assert response.status_code == 404


def test_write_requires_purchase_order_write_permission(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    _add_member(db, tenant_a, "approver@acme.com", "approver")
    approver_token = login(client, "approver@acme.com")

    response = _create_po(client, approver_token, tenant_a)
    assert response.status_code == 403


def test_match_invoice_to_po_by_number(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")

    po_id = _create_po(client, token, tenant_a).json()["id"]
    invoice = _create_invoice(
        client,
        token,
        tenant_a,
        po_number="PO-1001",
        items=[
            {
                "line_number": 1,
                "description": "Widget",
                "quantity": "10",
                "unit_price": "50.00",
                "line_total": "500.00",
            }
        ],
    ).json()
    invoice_id = invoice["id"]

    match = client.post(
        f"/api/invoices/{invoice_id}/match-po", headers=auth_headers(token, tenant_a)
    )
    assert match.status_code == 200, match.text
    outcome = match.json()
    assert outcome["matched"] is True
    assert outcome["method"] == "po_number"
    assert outcome["purchase_order_id"] == po_id

    fetched = client.get(
        f"/api/invoices/{invoice_id}", headers=auth_headers(token, tenant_a)
    )
    assert fetched.json()["purchase_order_id"] == po_id

    findings = client.get(
        f"/api/invoices/{invoice_id}/po-match", headers=auth_headers(token, tenant_a)
    )
    assert findings.status_code == 200
    rules = {f["rule_code"] for f in findings.json()["findings"]}
    assert rules == {"po.matched"}


def test_match_reports_discrepancy_as_finding(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")

    _create_po(client, token, tenant_a)
    invoice = _create_invoice(
        client, token, tenant_a, po_number="PO-1001", total="600.00"
    ).json()

    match = client.post(
        f"/api/invoices/{invoice['id']}/match-po",
        headers=auth_headers(token, tenant_a),
    )
    assert match.status_code == 200, match.text
    rules = {f["rule_code"] for f in match.json()["findings"]}
    assert "po.total_mismatch" in rules

    # A mismatch never changes the invoice state.
    fetched = client.get(
        f"/api/invoices/{invoice['id']}", headers=auth_headers(token, tenant_a)
    )
    assert fetched.json()["state"] == "needs_review"


def test_match_without_po_reports_not_found(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")
    invoice = _create_invoice(client, token, tenant_a, po_number="PO-9999").json()

    match = client.post(
        f"/api/invoices/{invoice['id']}/match-po",
        headers=auth_headers(token, tenant_a),
    )
    assert match.status_code == 200
    assert match.json()["matched"] is False
    assert match.json()["findings"][0]["rule_code"] == "po.not_found"
