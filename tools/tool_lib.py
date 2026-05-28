"""Shared library used by every mock tool service.

Responsibilities:
  - Fetch and cache the broker's JWKS.
  - Validate scoped JWTs (signature, iss, aud, scope, expiry).
  - Expose a FastAPI dependency factory `require_scope`.
"""

import logging
import time
from typing import Awaitable, Callable

import httpx
import jwt
from fastapi import Header, HTTPException, status
from jwt import PyJWK


logger = logging.getLogger("tool_lib")

JWKS_CACHE_TTL_SECONDS = 60


class ToolConfig:
    def __init__(
        self,
        *,
        tool_id: str,
        broker_public_url: str,
        broker_internal_url: str,
        broker_jwks_path: str = "/.well-known/jwks.json",
    ):
        self.tool_id = tool_id
        self.broker_public_url = broker_public_url
        self.broker_internal_url = broker_internal_url
        self.broker_jwks_path = broker_jwks_path
        self._jwks_cache: dict | None = None
        self._jwks_fetched_at: float = 0.0

    @property
    def jwks_url(self) -> str:
        return self.broker_internal_url.rstrip("/") + self.broker_jwks_path

    def _jwks_is_fresh(self) -> bool:
        return (
            self._jwks_cache is not None
            and (time.time() - self._jwks_fetched_at) < JWKS_CACHE_TTL_SECONDS
        )

    def get_jwks(self) -> dict:
        if self._jwks_is_fresh():
            return self._jwks_cache  # type: ignore[return-value]
        logger.info("Fetching JWKS from %s", self.jwks_url)
        resp = httpx.get(self.jwks_url, timeout=5.0)
        resp.raise_for_status()
        self._jwks_cache = resp.json()
        self._jwks_fetched_at = time.time()
        return self._jwks_cache

    def _key_for_kid(self, kid: str):
        jwks = self.get_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return PyJWK(key).key
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"no key in JWKS for kid {kid!r}",
        )

    def decode_and_validate(self, token: str, *, expected_scope: str) -> dict:
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"malformed token: {e}",
            ) from e

        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token header missing kid",
            )

        key = self._key_for_kid(kid)

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.tool_id,
                issuer=self.broker_public_url,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "scope", "jti"]},
            )
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"token rejected: {e}",
            ) from e

        if claims.get("scope") != expected_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"scope mismatch: required {expected_scope!r}, "
                    f"got {claims.get('scope')!r}"
                ),
            )
        return claims


def require_scope(config: ToolConfig, scope: str) -> Callable[..., Awaitable[dict]]:
    """Return a FastAPI dependency that validates a Bearer token for `scope`."""

    async def dependency(authorization: str = Header(default="")) -> dict:
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing Bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = authorization[7:].strip()
        return config.decode_and_validate(token, expected_scope=scope)

    return dependency
