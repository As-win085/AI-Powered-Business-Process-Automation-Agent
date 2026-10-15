"""End-to-end tests for the approval workflow.

Covers the full MVP path: upload/extract -> review -> validate -> submit ->
pending_approval -> approved, plus every server-side guard.
"""
import uuid
from decimal import Decimal

from app.core.security import hash_password
from app.db.models import Approval, Document, Invoice, Role, TenantMembership, User
from tests.helpers import auth_headers, login

PASSWORD = "Password123!"


def _add_member(db, tenant_id: uuid.UUID, email: str, role_name: str) -> uuid.UUID:
    role = db.query(Role).filter(Role.name == role_name, Role.tenant_id.is_(None)).one()
    user = User(email=email, password_hash=hash_password(PASSWORD), full_name=email)
    db.add(user)
    db.flush()
    db.add(TenantMembership(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.commit()
    return user.id


def _create_invoice(client, token, tenant_id, *, total="500.00", number="INV-100"):
    response = client.post(
        "/api/invoices",
        json={
            "supplier_name": "Acme Supplies Ltd",
            "invoice_number": number,
            "currency": "USD",
            "subtotal": total,
            "total_amount": total,
        },
        headers=auth_headers(token, tenant_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_full_approval_path_with_audit_trail(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    approver_a = _add_member(db, tenant_a, "approver@acme.com", "approver")

    finance_token = login(client, "finance@acme.com")
    approver_token = login(client, "approver@acme.com")
    auditor_token = login(client, "auditor@acme.com")

    invoice = _create_invoice(client, finance_token, tenant_a)
    invoice_id = invoice["id"]
    assert invoice["state"] == "needs_review"

    # finance validates then submits.
    response = client.post(
        f"/api/invoices/{invoice_id}/validate",
        headers=auth_headers(finance_token, tenant_a),
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "validated"

    response = client.post(
        f"/api/invoices/{invoice_id}/submit-for-approval",
        headers=auth_headers(finance_token, tenant_a),
    )
    assert response.status_code == 200, response.text
    submitted = response.json()
    assert submitted["invoice_state"] == "pending_approval"
    assert submitted["approver_id"] == str(approver_a)
    approval_id = submitted["approval_id"]

    # The assigned approver sees it in their queue.
    queue = client.get(
        "/api/approvals?scope=pending&assigned_to_me=true",
        headers=auth_headers(approver_token, tenant_a),
    )
    assert queue.status_code == 200, queue.text
    assert any(item["id"] == approval_id for item in queue.json()["items"])

    # Approve it.
    decision = client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"decision": "approved", "comment": "Looks good"},
        headers=auth_headers(approver_token, tenant_a),
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["decision"] == "approved"

    final = client.get(
        f"/api/invoices/{invoice_id}", headers=auth_headers(finance_token, tenant_a)
    )
    assert final.json()["state"] == "approved"

    # A complete audit trail exists for the transitions.
    audit = client.get("/api/audit?limit=100", headers=auth_headers(auditor_token, tenant_a))
    assert audit.status_code == 200, audit.text
    actions = [entry["action"] for entry in audit.json()["items"]]
    assert "invoice.create" in actions
    assert actions.count("invoice.transition") >= 3
    assert "approval.approved" in actions


def test_only_assigned_approver_can_decide(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    _add_member(db, tenant_a, "approver@acme.com", "approver")

    finance_token = login(client, "finance@acme.com")
    approver_token = login(client, "approver@acme.com")

    invoice = _create_invoice(client, finance_token, tenant_a, number="INV-200")
    invoice_id = invoice["id"]
    client.post(
        f"/api/invoices/{invoice_id}/validate",
        headers=auth_headers(finance_token, tenant_a),
    )
    submitted = client.post(
        f"/api/invoices/{invoice_id}/submit-for-approval",
        headers=auth_headers(finance_token, tenant_a),
    ).json()

    # admin_a is not the assigned approver.
    admin_token = login(client, "admin@acme.com")
    denied = client.post(
        f"/api/approvals/{submitted['approval_id']}/decision",
        json={"decision": "approved"},
        headers=auth_headers(admin_token, tenant_a),
    )
    assert denied.status_code == 403

    # The assigned approver can.
    allowed = client.post(
        f"/api/approvals/{submitted['approval_id']}/decision",
        json={"decision": "approved"},
        headers=auth_headers(approver_token, tenant_a),
    )
    assert allowed.status_code == 200


def test_decision_cannot_be_submitted_twice(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    _add_member(db, tenant_a, "approver@acme.com", "approver")

    finance_token = login(client, "finance@acme.com")
    approver_token = login(client, "approver@acme.com")

    invoice = _create_invoice(client, finance_token, tenant_a, number="INV-300")
    invoice_id = invoice["id"]
    client.post(
        f"/api/invoices/{invoice_id}/validate",
        headers=auth_headers(finance_token, tenant_a),
    )
    submitted = client.post(
        f"/api/invoices/{invoice_id}/submit-for-approval",
        headers=auth_headers(finance_token, tenant_a),
    ).json()

    first = client.post(
        f"/api/approvals/{submitted['approval_id']}/decision",
        json={"decision": "approved"},
        headers=auth_headers(approver_token, tenant_a),
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/approvals/{submitted['approval_id']}/decision",
        json={"decision": "rejected", "comment": "changed my mind"},
        headers=auth_headers(approver_token, tenant_a),
    )
    assert second.status_code == 409


def test_reject_requires_comment(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    _add_member(db, tenant_a, "approver@acme.com", "approver")

    finance_token = login(client, "finance@acme.com")
    approver_token = login(client, "approver@acme.com")

    invoice = _create_invoice(client, finance_token, tenant_a, number="INV-400")
    invoice_id = invoice["id"]
    client.post(
        f"/api/invoices/{invoice_id}/validate",
        headers=auth_headers(finance_token, tenant_a),
    )
    submitted = client.post(
        f"/api/invoices/{invoice_id}/submit-for-approval",
        headers=auth_headers(finance_token, tenant_a),
    ).json()

    missing = client.post(
        f"/api/approvals/{submitted['approval_id']}/decision",
        json={"decision": "rejected"},
        headers=auth_headers(approver_token, tenant_a),
    )
    assert missing.status_code == 422

    with_comment = client.post(
        f"/api/approvals/{submitted['approval_id']}/decision",
        json={"decision": "rejected", "comment": "Totals do not add up"},
        headers=auth_headers(approver_token, tenant_a),
    )
    assert with_comment.status_code == 200
    assert with_comment.json()["decision"] == "rejected"


def test_cannot_approve_own_upload(client, db, seeded):
    """Defense-in-depth: even a directly assigned uploader is blocked."""
    tenant_a = seeded["tenant_a"]
    uploader = _add_member(db, tenant_a, "approver@acme.com", "approver")

    document = Document(
        tenant_id=tenant_a,
        storage_key="k",
        original_filename="inv.pdf",
        content_type="application/pdf",
        size_bytes=1,
        file_hash="deadbeef" * 8,
        uploaded_by=uploader,
    )
    db.add(document)
    db.flush()

    invoice = Invoice(
        tenant_id=tenant_a,
        document_id=document.id,
        invoice_number="INV-500",
        normalized_invoice_number="inv500",
        total_amount=Decimal("500.00"),
        state="pending_approval",
    )
    db.add(invoice)
    db.flush()

    approval = Approval(
        tenant_id=tenant_a,
        invoice_id=invoice.id,
        approver_id=uploader,
        decision="pending",
        metadata_json={},
    )
    db.add(approval)
    db.commit()

    import pytest

    from app.core.exceptions import ForbiddenError
    from app.services.approval_service import decide_approval

    with pytest.raises(ForbiddenError):
        decide_approval(
            db,
            tenant_a,
            approval.id,
            actor_id=uploader,
            decision="approved",
        )


def test_tenant_isolation_hides_foreign_approval(client, db, seeded):
    tenant_a = seeded["tenant_a"]
    _add_member(db, tenant_a, "approver@acme.com", "approver")

    finance_token = login(client, "finance@acme.com")
    invoice = _create_invoice(client, finance_token, tenant_a, number="INV-600")
    invoice_id = invoice["id"]
    client.post(
        f"/api/invoices/{invoice_id}/validate",
        headers=auth_headers(finance_token, tenant_a),
    )
    submitted = client.post(
        f"/api/invoices/{invoice_id}/submit-for-approval",
        headers=auth_headers(finance_token, tenant_a),
    ).json()

    # Globex admin cannot see or act on Acme's approval.
    globex_token = login(client, "admin@globex.com")
    seen = client.get(
        f"/api/approvals/{submitted['approval_id']}",
        headers=auth_headers(globex_token, seeded["tenant_b"]),
    )
    assert seen.status_code == 404
