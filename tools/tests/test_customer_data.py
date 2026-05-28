from fastapi.testclient import TestClient

from customer_data import app


client = TestClient(app)


def test_health_is_public():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_customers_requires_token():
    resp = client.get("/customers")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing Bearer token"


def test_list_customers_with_valid_token(signer):
    token = signer.mint(audience="customer-data", scope="customer-data:read")
    resp = client.get(
        "/customers", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 5
    assert body["_caller"]["sub"] == "user-alice"
    assert body["_caller"]["jti"]


def test_token_with_wrong_audience_rejected(signer):
    token = signer.mint(audience="finance-data", scope="finance-data:read")
    resp = client.get(
        "/customers", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401
    assert "token rejected" in resp.json()["detail"]


def test_token_with_wrong_scope_rejected(signer):
    # right audience, wrong scope (write instead of read)
    token = signer.mint(audience="customer-data", scope="customer-data:write")
    resp = client.get(
        "/customers", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    assert "scope mismatch" in resp.json()["detail"]


def test_expired_token_rejected(signer):
    token = signer.mint(
        audience="customer-data", scope="customer-data:read", ttl_seconds=-10
    )
    resp = client.get(
        "/customers", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401
    assert "token rejected" in resp.json()["detail"]


def test_wrong_issuer_rejected(signer):
    token = signer.mint(
        audience="customer-data",
        scope="customer-data:read",
        issuer="http://attacker.example.com",
    )
    resp = client.get(
        "/customers", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


def test_get_single_customer(signer):
    token = signer.mint(audience="customer-data", scope="customer-data:read")
    resp = client.get(
        "/customers/C001", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Acme Corp"
