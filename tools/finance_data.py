"""Mock finance-data tool.

Scope: finance-data:read.
"""

import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

from tool_lib import AuditMiddleware, ToolConfig, require_scope


config = ToolConfig(
    tool_id="finance-data",
    broker_public_url=os.getenv("BROKER_PUBLIC_URL", "http://localhost:8001"),
    broker_internal_url=os.getenv("BROKER_INTERNAL_URL", "http://broker:8000"),
)


ACCOUNTS: dict[str, dict[str, Any]] = {
    "ACC-1001": {"id": "ACC-1001", "customer_id": "C001", "balance_usd": 845_321.12, "currency": "USD"},
    "ACC-1002": {"id": "ACC-1002", "customer_id": "C002", "balance_usd": 89_440.00, "currency": "USD"},
    "ACC-1003": {"id": "ACC-1003", "customer_id": "C003", "balance_usd": 12_180.55, "currency": "USD"},
    "ACC-1004": {"id": "ACC-1004", "customer_id": "C004", "balance_usd": 1_982_004.91, "currency": "USD"},
    "ACC-1005": {"id": "ACC-1005", "customer_id": "C005", "balance_usd": 4_220.07, "currency": "USD"},
}


app = FastAPI(title="finance-data tool", version="0.1.0")
app.add_middleware(
    AuditMiddleware,
    tool_id=config.tool_id,
    broker_internal_url=config.broker_internal_url,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/accounts")
async def list_accounts(
    claims: dict = Depends(require_scope(config, "finance-data:read")),
) -> dict[str, Any]:
    return {
        "items": list(ACCOUNTS.values()),
        "_caller_jti": claims["jti"],
    }


@app.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    claims: dict = Depends(require_scope(config, "finance-data:read")),
) -> dict[str, Any]:
    account = ACCOUNTS.get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"account {account_id} not found")
    return {**account, "_caller_jti": claims["jti"]}
