"""Mock customer-data tool.

Scopes accepted: customer-data:read, customer-data:write.
Mock data is deterministic so the demo output is reproducible.
"""

import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

from tool_lib import AuditMiddleware, ToolConfig, require_scope


config = ToolConfig(
    tool_id="customer-data",
    broker_public_url=os.getenv("BROKER_PUBLIC_URL", "http://localhost:8001"),
    broker_internal_url=os.getenv("BROKER_INTERNAL_URL", "http://broker:8000"),
)


CUSTOMERS: dict[str, dict[str, Any]] = {
    "C001": {"id": "C001", "name": "Acme Corp", "tier": "enterprise", "arr": 1_250_000},
    "C002": {"id": "C002", "name": "Globex", "tier": "midmarket", "arr": 320_000},
    "C003": {"id": "C003", "name": "Initech", "tier": "smb", "arr": 48_000},
    "C004": {"id": "C004", "name": "Hooli", "tier": "enterprise", "arr": 2_100_000},
    "C005": {"id": "C005", "name": "Pied Piper", "tier": "smb", "arr": 12_500},
}


app = FastAPI(title="customer-data tool", version="0.1.0")
app.add_middleware(
    AuditMiddleware,
    tool_id=config.tool_id,
    broker_internal_url=config.broker_internal_url,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/customers")
async def list_customers(
    claims: dict = Depends(require_scope(config, "customer-data:read")),
) -> dict[str, Any]:
    return {
        "items": list(CUSTOMERS.values()),
        "_caller": {
            "sub": claims["sub"],
            "session_id": claims.get("session_id"),
            "jti": claims["jti"],
        },
    }


@app.get("/customers/{customer_id}")
async def get_customer(
    customer_id: str,
    claims: dict = Depends(require_scope(config, "customer-data:read")),
) -> dict[str, Any]:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"customer {customer_id} not found")
    return {**customer, "_caller_jti": claims["jti"]}
