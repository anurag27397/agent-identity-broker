"""Thin client wrapper around the broker's HTTP API.

The agent uses this to (1) authenticate as a user, (2) request scoped
tokens for each tool call. Every method returns a dataclass so the agent
can branch cleanly on failure paths.
"""

from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class LoginResult:
    session_token: str
    sub: str
    preferred_username: str
    roles: list[str]


@dataclass
class ScopedTokenResult:
    access_token: Optional[str]
    expires_in: Optional[int]
    error: Optional[str]
    status: int


class BrokerClient:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base = base_url.rstrip("/")
        self.session_token: Optional[str] = None
        self.client = httpx.Client(timeout=10.0)

    def login(self, username: str, password: str) -> LoginResult:
        resp = self.client.post(
            f"{self.base}/auth/dev-login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        body = resp.json()
        self.session_token = body["session_token"]
        p = body["payload"]
        return LoginResult(
            session_token=self.session_token,
            sub=p["sub"],
            preferred_username=p.get("preferred_username", ""),
            roles=list(p.get("roles") or []),
        )

    def exchange(self, *, audience: str, scope: str) -> ScopedTokenResult:
        if not self.session_token:
            raise RuntimeError("not logged in")
        resp = self.client.post(
            f"{self.base}/token/exchange",
            json={
                "subject_token": self.session_token,
                "audience": audience,
                "scope": scope,
            },
        )
        if resp.status_code == 200:
            body = resp.json()
            return ScopedTokenResult(
                access_token=body["access_token"],
                expires_in=body["expires_in"],
                error=None,
                status=200,
            )
        try:
            detail = resp.json().get("detail")
        except Exception:
            detail = resp.text
        return ScopedTokenResult(
            access_token=None,
            expires_in=None,
            error=detail or "unknown",
            status=resp.status_code,
        )
