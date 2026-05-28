from fastapi.testclient import TestClient

from email_send import app


client = TestClient(app)


def _payload():
    return {"to": "ops@example.com", "subject": "hi", "body": "test"}


def test_send_requires_token():
    resp = client.post("/send", json=_payload())
    assert resp.status_code == 401


def test_send_with_email_send_scope_admin_path(signer):
    # email-send is the scope an "admin" role would have; we just mint it.
    token = signer.mint(audience="email-send", scope="email-send")
    resp = client.post(
        "/send", json=_payload(), headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["to"] == "ops@example.com"


def test_send_with_customer_data_scope_rejected_by_aud(signer):
    # analyst would have customer-data:read but not email-send. A scoped
    # token intended for the customer-data tool must not be accepted here.
    token = signer.mint(audience="customer-data", scope="customer-data:read")
    resp = client.post(
        "/send", json=_payload(), headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401  # audience mismatch
