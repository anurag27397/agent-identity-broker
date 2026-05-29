from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from audit import AuditStore, SCOPED_DENIED, SCOPED_MINTED
from config import settings
from keys import KeyMaterial
from policy import evaluate
from revocation import RevocationStore
from tokens import (
    ISSUED_TOKEN_TYPE_ACCESS,
    TokenError,
    mint_scoped_token,
    verify_session_token,
)


class TokenExchangeRequest(BaseModel):
    subject_token: str = Field(..., description="The caller's session JWT")
    audience: str = Field(..., description="Target tool ID (e.g. 'customer-data')")
    scope: str = Field(..., description="Requested scope (e.g. 'customer-data:read')")


class TokenExchangeResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    issued_token_type: str = ISSUED_TOKEN_TYPE_ACCESS
    scope: str
    audience: str


def build_router(
    material: KeyMaterial, store: AuditStore, rev: RevocationStore
) -> APIRouter:
    router = APIRouter(prefix="/token", tags=["exchange"])

    @router.post("/exchange", response_model=TokenExchangeResponse)
    def exchange(req: TokenExchangeRequest) -> TokenExchangeResponse:
        try:
            session_claims = verify_session_token(
                material,
                token=req.subject_token,
                issuer=settings.broker_public_url,
            )
        except TokenError as e:
            raise HTTPException(
                status_code=401, detail=f"invalid subject_token: {e}"
            ) from e

        session_id = session_claims.get("session_id")

        if rev.is_kill_switch_on():
            reason = "broker kill switch is engaged"
            store.record(
                event_type=SCOPED_DENIED,
                actor_sub=session_claims.get("sub"),
                actor_username=session_claims.get("preferred_username"),
                session_id=session_id,
                audience=req.audience,
                scope=req.scope,
                reason=reason,
            )
            raise HTTPException(status_code=503, detail=reason)

        if session_id and rev.is_revoked(session_id):
            reason = "session has been revoked"
            store.record(
                event_type=SCOPED_DENIED,
                actor_sub=session_claims.get("sub"),
                actor_username=session_claims.get("preferred_username"),
                session_id=session_id,
                audience=req.audience,
                scope=req.scope,
                reason=reason,
            )
            raise HTTPException(status_code=403, detail=reason)

        roles: list[str] = list(session_claims.get("roles") or [])
        decision = evaluate(roles=roles, audience=req.audience, scope=req.scope)
        if not decision.allowed:
            store.record(
                event_type=SCOPED_DENIED,
                actor_sub=session_claims.get("sub"),
                actor_username=session_claims.get("preferred_username"),
                session_id=session_id,
                audience=req.audience,
                scope=req.scope,
                reason=decision.reason,
            )
            raise HTTPException(status_code=403, detail=decision.reason)

        token, payload = mint_scoped_token(
            material,
            session_claims=session_claims,
            audience=req.audience,
            scope=req.scope,
            issuer=settings.broker_public_url,
            ttl_seconds=settings.scoped_token_ttl_seconds,
        )
        store.record(
            event_type=SCOPED_MINTED,
            actor_sub=session_claims.get("sub"),
            actor_username=session_claims.get("preferred_username"),
            session_id=session_claims.get("session_id"),
            jti=payload["jti"],
            audience=req.audience,
            scope=req.scope,
        )

        return TokenExchangeResponse(
            access_token=token,
            expires_in=settings.scoped_token_ttl_seconds,
            scope=req.scope,
            audience=req.audience,
        )

    return router
