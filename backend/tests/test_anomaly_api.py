"""API tests for invoice anomaly scoring, retrieval and the review queue."""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.anomaly_detection import AnomalyModel
from app.services.anomaly_model_store import clear_model, save_model
from app.services.anomaly_training import build_feature_rows
from tests.helpers import auth_headers, login

GENERATOR = Path(__file__).resolve().parents[1] / "scripts" / "generate_history.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_history", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def trained_model():
    payload = _load_generator().generate_records(suppliers=8, months=8, seed=7)
    rows = build_feature_rows(payload["records"])
    model = AnomalyModel.train([row.vector for row in rows])
    save_model(model)
    yield model
    clear_model()


def _create_invoice(client, token, tenant_id, *, number, total, date, supplier="Acme Supplies Ltd"):
    response = client.post(
        "/api/invoices",
        json={
            "supplier_name": supplier,
            "invoice_number": number,
            "currency": "USD",
            "subtotal": total,
            "total_amount": total,
            "invoice_date": date,
        },
        headers=auth_headers(token, tenant_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_history(client, token, tenant_id, *, supplier="Acme Supplies Ltd"):
    for index in range(6):
        _create_invoice(
            client,
            token,
            tenant_id,
            number=f"INV-HIST-{index}",
            total="1000.00",
            date=f"2024-0{index + 1}-05",
            supplier=supplier,
        )


def test_score_and_read_invoice_anomaly(client, db, seeded, trained_model):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")
    _seed_history(client, token, tenant_a)

    spike = _create_invoice(
        client, token, tenant_a, number="INV-SPIKE", total="120000.00", date="2024-08-05"
    )

    scored = client.post(
        f"/api/invoices/{spike['id']}/score-anomaly", headers=auth_headers(token, tenant_a)
    )
    assert scored.status_code == 200, scored.text
    body = scored.json()
    assert body["model_version"] == trained_model.version
    assert body["flagged"] is True
    assert body["risk_level"] == "high"
    codes = {reason["code"] for reason in body["reasons"]}
    assert "amount_vs_median" in codes

    fetched = client.get(
        f"/api/invoices/{spike['id']}/anomaly", headers=auth_headers(token, tenant_a)
    )
    assert fetched.status_code == 200
    assert fetched.json()["flagged"] is True

    queue = client.get("/api/anomalies", headers=auth_headers(token, tenant_a))
    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["invoice_id"] == spike["id"]


def test_normal_invoice_is_not_flagged(client, db, seeded, trained_model):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")
    _seed_history(client, token, tenant_a)

    normal = _create_invoice(
        client, token, tenant_a, number="INV-NORMAL", total="1050.00", date="2024-08-05"
    )
    scored = client.post(
        f"/api/invoices/{normal['id']}/score-anomaly", headers=auth_headers(token, tenant_a)
    )
    assert scored.status_code == 200
    assert scored.json()["flagged"] is False


def test_scoring_is_idempotent(client, db, seeded, trained_model):
    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")
    _seed_history(client, token, tenant_a)
    spike = _create_invoice(
        client, token, tenant_a, number="INV-SPIKE", total="120000.00", date="2024-08-05"
    )

    first = client.post(
        f"/api/invoices/{spike['id']}/score-anomaly", headers=auth_headers(token, tenant_a)
    ).json()
    second = client.post(
        f"/api/invoices/{spike['id']}/score-anomaly", headers=auth_headers(token, tenant_a)
    ).json()
    assert first["score"] == second["score"]

    from app.db.models import ValidationResult

    findings = (
        db.query(ValidationResult)
        .filter(ValidationResult.invoice_id == uuid.UUID(spike["id"]))
        .all()
    )
    codes = [row.rule_code for row in findings]
    assert len(codes) == len(set(codes))


def test_anomaly_is_tenant_scoped(client, db, seeded, trained_model):
    tenant_a = seeded["tenant_a"]
    tenant_b = seeded["tenant_b"]
    finance = login(client, "finance@acme.com")
    _seed_history(client, finance, tenant_a)
    spike = _create_invoice(
        client, finance, tenant_a, number="INV-SPIKE", total="120000.00", date="2024-08-05"
    )

    admin_b = login(client, "admin@globex.com")
    response = client.post(
        f"/api/invoices/{spike['id']}/score-anomaly", headers=auth_headers(admin_b, tenant_b)
    )
    assert response.status_code == 404

    queue = client.get("/api/anomalies", headers=auth_headers(admin_b, tenant_b))
    assert queue.json()["total"] == 0


def test_auditor_can_read_anomaly_queue(client, db, seeded, trained_model):
    tenant_a = seeded["tenant_a"]
    finance = login(client, "finance@acme.com")
    _seed_history(client, finance, tenant_a)
    invoice = _create_invoice(
        client, finance, tenant_a, number="INV-1", total="1000.00", date="2024-08-05"
    )
    client.post(
        f"/api/invoices/{invoice['id']}/score-anomaly", headers=auth_headers(finance, tenant_a)
    )

    auditor = login(client, "auditor@acme.com")
    read = client.get(
        f"/api/invoices/{invoice['id']}/anomaly", headers=auth_headers(auditor, tenant_a)
    )
    assert read.status_code == 200

    queue = client.get("/api/anomalies", headers=auth_headers(auditor, tenant_a))
    assert queue.status_code == 200


def test_model_info_reports_loaded_model(client, seeded, trained_model):
    token = login(client, "finance@acme.com")
    response = client.get("/api/anomaly/model", headers=auth_headers(token, seeded["tenant_a"]))
    assert response.status_code == 200
    body = response.json()
    assert body["trained"] is True
    assert body["version"] == trained_model.version
    assert body["feature_names"]


def test_scoring_without_model_returns_503(client, db, seeded):
    clear_model()
    settings = get_settings()
    assert settings.anomaly_model_dir.exists() is False or not any(
        settings.anomaly_model_dir.glob("*.joblib")
    )

    tenant_a = seeded["tenant_a"]
    token = login(client, "finance@acme.com")
    invoice = _create_invoice(
        client, token, tenant_a, number="INV-1", total="1000.00", date="2024-08-05"
    )
    response = client.post(
        f"/api/invoices/{invoice['id']}/score-anomaly", headers=auth_headers(token, tenant_a)
    )
    assert response.status_code == 503
