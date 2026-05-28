import time

import pytest

from keys import load_or_generate
from tokens import TokenError, mint_session_token, verify_session_token


ISSUER = "http://localhost:8001"


@pytest.fixture
def material(tmp_path):
    return load_or_generate(str(tmp_path / "keys"))


def test_mint_then_verify_roundtrip(material):
    token, payload = mint_session_token(
        material,
        user_claims={
            "sub": "user-123",
            "email": "alice@example.com",
            "preferred_username": "alice",
            "name": "Alice Demo",
            "roles": ["analyst"],
        },
        issuer=ISSUER,
        ttl_seconds=60,
    )

    decoded = verify_session_token(material, token=token, issuer=ISSUER)

    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "alice@example.com"
    assert decoded["roles"] == ["analyst"]
    assert decoded["session_id"] == payload["session_id"]
    assert decoded["aud"] == "agent-broker:session"
    assert decoded["iss"] == ISSUER


def test_expired_token_is_rejected(material):
    token, _ = mint_session_token(
        material,
        user_claims={"sub": "user-123"},
        issuer=ISSUER,
        ttl_seconds=-1,
    )

    with pytest.raises(TokenError):
        verify_session_token(material, token=token, issuer=ISSUER)


def test_wrong_issuer_is_rejected(material):
    token, _ = mint_session_token(
        material,
        user_claims={"sub": "user-123"},
        issuer=ISSUER,
        ttl_seconds=60,
    )

    with pytest.raises(TokenError):
        verify_session_token(
            material, token=token, issuer="http://attacker.example.com"
        )


def test_tampered_token_is_rejected(material):
    token, _ = mint_session_token(
        material,
        user_claims={"sub": "user-123"},
        issuer=ISSUER,
        ttl_seconds=60,
    )

    # flip a byte in the signature
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{sig[:-2]}AA"

    with pytest.raises(TokenError):
        verify_session_token(material, token=tampered, issuer=ISSUER)
