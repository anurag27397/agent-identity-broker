"""Shared test helpers. Generates a test RSA keypair, fabricates a JWKS
matching it, and stubs out tool_lib's HTTP fetch so tests run offline.
"""

import base64
import hashlib
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


BROKER_PUBLIC_URL = "http://localhost:8001"


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class TestSigner:
    def __init__(self):
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.private_key.public_key()
        pub_der = self.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.kid = hashlib.sha256(pub_der).hexdigest()[:16]
        self.private_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def jwks(self) -> dict:
        numbers = self.public_key.public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": self.kid,
                    "n": _b64url_uint(numbers.n),
                    "e": _b64url_uint(numbers.e),
                }
            ]
        }

    def mint(
        self,
        *,
        audience: str,
        scope: str,
        sub: str = "user-alice",
        ttl_seconds: int = 60,
        issuer: str = BROKER_PUBLIC_URL,
        extra: dict | None = None,
    ) -> str:
        now = int(time.time())
        payload = {
            "iss": issuer,
            "aud": audience,
            "sub": sub,
            "session_id": "sess-test",
            "scope": scope,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + ttl_seconds,
        }
        if extra:
            payload.update(extra)
        return jwt.encode(
            payload,
            self.private_pem,
            algorithm="RS256",
            headers={"kid": self.kid, "typ": "JWT"},
        )


@pytest.fixture
def signer():
    return TestSigner()


@pytest.fixture(autouse=True)
def stub_jwks(monkeypatch, signer):
    """Replace tool_lib's JWKS fetch with the test signer's JWKS."""
    import tool_lib

    def fake_get_jwks(self):
        return signer.jwks()

    monkeypatch.setattr(tool_lib.ToolConfig, "get_jwks", fake_get_jwks)
