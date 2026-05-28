import time
import uuid

import jwt

from keys import KeyMaterial


SESSION_AUDIENCE = "agent-broker:session"


class TokenError(Exception):
    pass


def mint_session_token(
    material: KeyMaterial,
    *,
    user_claims: dict,
    issuer: str,
    ttl_seconds: int,
    session_id: str | None = None,
) -> tuple[str, dict]:
    now = int(time.time())
    session_id = session_id or str(uuid.uuid4())

    payload = {
        "iss": issuer,
        "aud": SESSION_AUDIENCE,
        "sub": user_claims["sub"],
        "session_id": session_id,
        "iat": now,
        "nbf": now,
        "exp": now + ttl_seconds,
        "email": user_claims.get("email"),
        "preferred_username": user_claims.get("preferred_username"),
        "name": user_claims.get("name"),
        "roles": user_claims.get("roles", []),
    }

    token = jwt.encode(
        payload,
        material.private_pem,
        algorithm="RS256",
        headers={"kid": material.kid, "typ": "JWT"},
    )
    return token, payload


def verify_session_token(
    material: KeyMaterial,
    *,
    token: str,
    issuer: str,
) -> dict:
    try:
        return jwt.decode(
            token,
            material.public_pem,
            algorithms=["RS256"],
            audience=SESSION_AUDIENCE,
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise TokenError(str(e)) from e
