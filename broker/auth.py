import secrets

import httpx
from authlib.integrations.starlette_client import OAuth
from authlib.jose import JsonWebKey, jwt as jose_jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from audit import AuditStore, LOGIN, SESSION_MINTED
from config import settings
from keys import KeyMaterial
from tokens import mint_session_token


class DevLoginRequest(BaseModel):
    username: str
    password: str


oauth = OAuth()
oauth.register(
    name="keycloak",
    client_id=settings.keycloak_client_id,
    client_secret=settings.keycloak_client_secret,
    authorize_url=settings.authorization_endpoint,
    access_token_url=settings.token_endpoint,
    jwks_uri=settings.jwks_uri,
    client_kwargs={"scope": "openid email profile"},
)


def build_router(material: KeyMaterial, store: AuditStore) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.get("/login")
    async def login(request: Request):
        state = secrets.token_urlsafe(16)
        request.session["oauth_state"] = state
        return await oauth.keycloak.authorize_redirect(
            request,
            redirect_uri=settings.redirect_uri,
            state=state,
        )

    @router.get("/callback")
    async def callback(request: Request):
        stored_state = request.session.pop("oauth_state", None)
        received_state = request.query_params.get("state")
        if not stored_state or stored_state != received_state:
            raise HTTPException(status_code=400, detail="state mismatch")

        token = await oauth.keycloak.authorize_access_token(request)
        id_token = token.get("id_token")
        if not id_token:
            raise HTTPException(status_code=400, detail="keycloak did not return id_token")

        claims = await _validate_id_token(id_token)
        user_claims = {
            "sub": claims["sub"],
            "email": claims.get("email"),
            "preferred_username": claims.get("preferred_username"),
            "name": claims.get("name"),
            "roles": claims.get("realm_access", {}).get("roles", []),
        }

        session_jwt, payload = mint_session_token(
            material,
            user_claims=user_claims,
            issuer=settings.broker_public_url,
            ttl_seconds=settings.session_token_ttl_seconds,
        )
        _record_login(store, payload, source="oidc-callback")

        response = HTMLResponse(_render_success(session_jwt, payload))
        response.set_cookie(
            "session_token",
            session_jwt,
            httponly=True,
            samesite="lax",
            max_age=settings.session_token_ttl_seconds,
        )
        return response

    @router.get("/logout")
    async def logout():
        response = RedirectResponse(url="/")
        response.delete_cookie("session_token")
        return response

    @router.post("/dev-login")
    async def dev_login(req: DevLoginRequest) -> dict:
        """DEV-ONLY: Resource-Owner-Password-Credentials grant against
        Keycloak, then mint a broker session JWT. Intended for the demo
        agent so it can authenticate without a browser. Do not enable
        this endpoint in production deployments.
        """
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                settings.token_endpoint,
                data={
                    "grant_type": "password",
                    "client_id": settings.keycloak_client_id,
                    "client_secret": settings.keycloak_client_secret,
                    "username": req.username,
                    "password": req.password,
                    "scope": "openid email profile",
                },
            )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=401,
                detail=f"keycloak rejected credentials: {resp.text}",
            )
        id_token = resp.json().get("id_token")
        if not id_token:
            raise HTTPException(status_code=500, detail="keycloak returned no id_token")

        claims = await _validate_id_token(id_token)
        user_claims = {
            "sub": claims["sub"],
            "email": claims.get("email"),
            "preferred_username": claims.get("preferred_username"),
            "name": claims.get("name"),
            "roles": claims.get("realm_access", {}).get("roles", []),
        }
        session_jwt, payload = mint_session_token(
            material,
            user_claims=user_claims,
            issuer=settings.broker_public_url,
            ttl_seconds=settings.session_token_ttl_seconds,
        )
        _record_login(store, payload, source="dev-login")
        return {"session_token": session_jwt, "payload": payload}

    return router


def _record_login(store: AuditStore, payload: dict, *, source: str) -> None:
    common = {
        "actor_sub": payload.get("sub"),
        "actor_username": payload.get("preferred_username"),
        "session_id": payload.get("session_id"),
    }
    store.record(event_type=LOGIN, **common, metadata={"source": source})
    store.record(event_type=SESSION_MINTED, **common)


async def _validate_id_token(id_token: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(settings.jwks_uri)
        resp.raise_for_status()
        jwks = resp.json()

    key = JsonWebKey.import_key_set(jwks)
    claims = jose_jwt.decode(id_token, key)
    claims.validate_iss = lambda *_: True  # issuer validation handled below
    if claims.get("iss") != settings.issuer:
        raise HTTPException(
            status_code=400,
            detail=f"unexpected issuer {claims.get('iss')!r}",
        )
    if settings.keycloak_client_id not in (claims.get("aud") or []) and claims.get("aud") != settings.keycloak_client_id:
        raise HTTPException(status_code=400, detail="audience mismatch")
    claims.validate(leeway=10)
    return dict(claims)


def _render_success(token: str, payload: dict) -> str:
    return f"""<!doctype html>
<html><head><title>Signed in</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #e6edf3; padding: 40px; max-width: 760px; margin: 0 auto; }}
  h1 {{ color: #7ee787; }}
  pre {{ background: #161b22; padding: 16px; border-radius: 8px; overflow-x: auto; font-size: 13px; }}
  code {{ word-break: break-all; }}
  a {{ color: #58a6ff; }}
</style></head>
<body>
<h1>Signed in as {payload.get("preferred_username", payload.get("sub"))}</h1>
<p>Session token (also set as <code>session_token</code> cookie, TTL {settings.session_token_ttl_seconds}s):</p>
<pre><code>{token}</code></pre>
<p>Payload:</p>
<pre><code>{payload}</code></pre>
<p>Try it: <a href="/me">/me</a> &middot; <a href="/auth/logout">logout</a></p>
</body></html>"""
