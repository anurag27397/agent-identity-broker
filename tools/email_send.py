"""Mock email-send tool.

Scope: email-send.

This tool exists to demonstrate the denial path. The demo user `alice`
(role `analyst`) does not have the `email-send` scope, so any attempt
to call /send with her tokens will fail at the broker's policy
evaluation, never reaching this tool. The admin role would be allowed.
"""

import os
from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel, EmailStr

from tool_lib import ToolConfig, require_scope


config = ToolConfig(
    tool_id="email-send",
    broker_public_url=os.getenv("BROKER_PUBLIC_URL", "http://localhost:8001"),
    broker_internal_url=os.getenv("BROKER_INTERNAL_URL", "http://broker:8000"),
)


class SendRequest(BaseModel):
    to: EmailStr
    subject: str
    body: str


app = FastAPI(title="email-send tool", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/send")
async def send(
    req: SendRequest,
    claims: dict = Depends(require_scope(config, "email-send")),
) -> dict[str, Any]:
    # In a real tool we'd actually send. Here we just confirm the call
    # would have been made, with the caller identified.
    return {
        "status": "queued",
        "to": req.to,
        "subject": req.subject,
        "_caller": {
            "sub": claims["sub"],
            "session_id": claims.get("session_id"),
            "jti": claims["jti"],
        },
    }
