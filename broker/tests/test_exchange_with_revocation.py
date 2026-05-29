"""Integration: revocation and kill switch as seen by /token/exchange."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")

    import config
    import app as app_module

    importlib.reload(config)
    importlib.reload(app_module)

    return TestClient(app_module.app), app_module


def _session_token(app_module, *, sub: str = "user-alice", session_id: str | None = None):
    from tokens import mint_session_token

    token, payload = mint_session_token(
        app_module.material,
        user_claims={
            "sub": sub,
            "preferred_username": sub,
            "name": sub,
            "email": f"{sub}@x.com",
            "roles": ["analyst"],
        },
        issuer=app_module.settings.broker_public_url,
        ttl_seconds=300,
        session_id=session_id,
    )
    return token, payload


def _exchange(tc, token, *, audience="customer-data", scope="customer-data:read"):
    return tc.post(
        "/token/exchange",
        json={"subject_token": token, "audience": audience, "scope": scope},
    )


def test_revoked_session_cannot_exchange(client):
    tc, app_module = client
    token, payload = _session_token(app_module)

    assert _exchange(tc, token).status_code == 200

    # operator revokes
    r = tc.post(f"/sessions/{payload['session_id']}/revoke")
    assert r.status_code == 200

    resp = _exchange(tc, token)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "session has been revoked"


def test_unrevoke_restores_access(client):
    tc, app_module = client
    token, payload = _session_token(app_module)

    tc.post(f"/sessions/{payload['session_id']}/revoke")
    assert _exchange(tc, token).status_code == 403

    tc.post(f"/sessions/{payload['session_id']}/unrevoke")
    assert _exchange(tc, token).status_code == 200


def test_kill_switch_blocks_all_exchanges(client):
    tc, app_module = client
    token_a, _ = _session_token(app_module, sub="user-a", session_id="sess-a")
    token_b, _ = _session_token(app_module, sub="user-b", session_id="sess-b")

    assert _exchange(tc, token_a).status_code == 200
    assert _exchange(tc, token_b).status_code == 200

    tc.post("/kill-switch")

    r1 = _exchange(tc, token_a)
    r2 = _exchange(tc, token_b)
    assert r1.status_code == 503
    assert r2.status_code == 503
    assert "kill switch" in r1.json()["detail"]

    tc.delete("/kill-switch")
    assert _exchange(tc, token_a).status_code == 200


def test_session_status_endpoint(client):
    tc, app_module = client
    _, payload = _session_token(app_module)

    r = tc.get(f"/sessions/{payload['session_id']}")
    assert r.json() == {"session_id": payload["session_id"], "revoked": False}

    tc.post(f"/sessions/{payload['session_id']}/revoke")
    r = tc.get(f"/sessions/{payload['session_id']}")
    assert r.json()["revoked"] is True
