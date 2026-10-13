from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from tests.helpers import auth_headers, login


def _expired_access_token(subject: str) -> str:
    payload = {
        "sub": subject,
        "type": "access",
        "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def test_login_success(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "admin@acme.com", "password": "Password123!"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


def test_login_is_case_insensitive_for_email(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "ADMIN@acme.com", "password": "Password123!"}
    )
    assert response.status_code == 200


def test_login_wrong_password_is_unauthorized(client, seeded):
    response = client.post("/api/auth/login", json={"email": "admin@acme.com", "password": "nope"})
    assert response.status_code == 401


def test_login_unknown_email_is_unauthorized(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@acme.com", "password": "whatever"}
    )
    assert response.status_code == 401


def test_missing_token_is_unauthorized(client):
    assert client.get("/api/auth/me").status_code == 401


def test_malformed_token_is_unauthorized(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_expired_token_is_unauthorized(client, seeded):
    token = _expired_access_token(str(seeded["admin_a"]))
    response = client.get("/api/auth/me", headers=auth_headers(token))
    assert response.status_code == 401


def test_refresh_token_cannot_be_used_as_access(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "admin@acme.com", "password": "Password123!"}
    )
    refresh_token = response.json()["refresh_token"]
    response = client.get("/api/auth/me", headers=auth_headers(refresh_token))
    assert response.status_code == 401


def test_refresh_issues_new_tokens(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "admin@acme.com", "password": "Password123!"}
    )
    refresh_token = response.json()["refresh_token"]
    response = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_me_returns_user_and_memberships(client, seeded):
    token = login(client, "admin@acme.com")
    response = client.get("/api/auth/me", headers=auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "admin@acme.com"
    assert [m["tenant"]["slug"] for m in body["memberships"]] == ["acme"]
