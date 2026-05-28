import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from starlette.middleware.sessions import SessionMiddleware

import auth
from config import settings
from keys import load_or_generate
from tokens import TokenError, verify_session_token


logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("broker")


material = load_or_generate(settings.keys_dir)
logger.info("Loaded signing key kid=%s", material.kid)


app = FastAPI(
    title="Agent Identity Broker",
    version="0.2.0",
    description="Identity governance for AI agents",
)

app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.include_router(auth.build_router(material))


def current_user(request: Request) -> dict:
    token = _bearer_token(request) or request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        return verify_session_token(
            material,
            token=token,
            issuer=settings.broker_public_url,
        )
    except TokenError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict:
    return {
        "service": "agent-identity-broker",
        "version": "0.2.0",
        "login": "/auth/login",
        "me": "/me",
        "jwks": "/.well-known/jwks.json",
        "docs": "/docs",
    }


@app.get("/.well-known/jwks.json")
async def jwks() -> dict:
    return material.jwks()


@app.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return user
