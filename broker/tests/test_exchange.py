"""Integration tests for /token/exchange via FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    # isolate keys and audit DB to a temp dir before importing the app module
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    # force a fresh import so settings picks up the env
    import importlib
    import config
    import app as app_module

    importlib.reload(config)
    importlib.reload(app_module)

    return TestClient(app_module.app), app_module


def _mint_test_session_token(app_module, *, roles: list[str], sub: str = "user-alice"):
    from tokens import mint_session_token

    token, payload = mint_session_token(
        app_module.material,
        user_claims={
            "sub": sub,
            "email": f"{sub}@example.com",
            "preferred_username": sub,
            "name": sub,
            "roles": roles,
        },
        issuer=app_module.settings.broker_public_url,
        ttl_seconds=300,
    )
    return token, payload


def test_exchange_happy_path_for_analyst(client):
    tc, app_module = client
    session_token, _ = _mint_test_session_token(app_module, roles=["analyst"])

    resp = tc.post(
        "/token/exchange",
        json={
            "subject_token": session_token,
            "audience": "customer-data",
            "scope": "customer-data:read",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 60
    assert body["scope"] == "customer-data:read"
    assert body["audience"] == "customer-data"
    assert body["issued_token_type"] == "urn:ietf:params:oauth:token-type:access_token"
    assert body["access_token"]


def test_exchange_denied_for_disallowed_scope(client):
    tc, app_module = client
    session_token, _ = _mint_test_session_token(app_module, roles=["analyst"])

    resp = tc.post(
        "/token/exchange",
        json={
            "subject_token": session_token,
            "audience": "email-send",
            "scope": "email-send",
        },
    )
    assert resp.status_code == 403, resp.text
    assert "not granted" in resp.json()["detail"]


def test_exchange_rejects_unknown_audience(client):
    tc, app_module = client
    session_token, _ = _mint_test_session_token(app_module, roles=["admin"])

    resp = tc.post(
        "/token/exchange",
        json={
            "subject_token": session_token,
            "audience": "unknown-tool",
            "scope": "unknown-tool:do",
        },
    )
    assert resp.status_code == 403
    assert "unknown audience" in resp.json()["detail"]


def test_exchange_rejects_invalid_subject_token(client):
    tc, _ = client
    resp = tc.post(
        "/token/exchange",
        json={
            "subject_token": "not.a.real.jwt",
            "audience": "customer-data",
            "scope": "customer-data:read",
        },
    )
    assert resp.status_code == 401
    assert "invalid subject_token" in resp.json()["detail"]


def test_scoped_token_audience_and_scope_in_payload(client):
    tc, app_module = client
    session_token, session_payload = _mint_test_session_token(
        app_module, roles=["analyst"]
    )

    resp = tc.post(
        "/token/exchange",
        json={
            "subject_token": session_token,
            "audience": "customer-data",
            "scope": "customer-data:read",
        },
    )
    assert resp.status_code == 200
    scoped = resp.json()["access_token"]

    from tokens import verify_scoped_token

    decoded = verify_scoped_token(
        app_module.material,
        token=scoped,
        issuer=app_module.settings.broker_public_url,
        audience="customer-data",
    )
    assert decoded["aud"] == "customer-data"
    assert decoded["scope"] == "customer-data:read"
    assert decoded["session_id"] == session_payload["session_id"]
    assert decoded["sub"] == session_payload["sub"]
    assert "jti" in decoded
    assert decoded["exp"] - decoded["iat"] == 60
