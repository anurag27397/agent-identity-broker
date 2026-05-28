"""Tool definitions Claude sees and the local executors that run them.

Each executor:
  1. Asks the broker for a scoped token (audience + scope).
  2. If the broker denies, returns a structured error Claude can read.
  3. Otherwise calls the tool's HTTP endpoint with the scoped token.
  4. Returns whatever the tool returned, or its error.

Keeping the audience/scope mapping in one place makes it obvious to
anyone reading the code what permission each tool actually needs.
"""

import os
from typing import Any, Callable

import httpx

from broker_client import BrokerClient


CUSTOMER_DATA_URL = os.getenv("CUSTOMER_DATA_URL", "http://localhost:8101")
FINANCE_DATA_URL = os.getenv("FINANCE_DATA_URL", "http://localhost:8102")
EMAIL_SEND_URL = os.getenv("EMAIL_SEND_URL", "http://localhost:8103")


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_customers",
        "description": (
            "List all customers in the CRM. Returns id, name, tier, and ARR for each. "
            "Use this for any general 'who are our customers' question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_customer",
        "description": "Look up details for one customer by their ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer ID like 'C001'.",
                },
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "list_accounts",
        "description": "List all financial accounts. Returns id, customer_id, balance_usd.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_account",
        "description": "Look up balance and details for one account by id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
            },
            "required": ["account_id"],
        },
    },
    {
        "name": "send_email",
        "description": (
            "Send an email on the user's behalf. Use only when the user explicitly "
            "asks you to send a message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
]


def _call(method: str, url: str, *, token: str, json_body: dict | None = None) -> dict:
    try:
        resp = httpx.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=json_body,
            timeout=10.0,
        )
    except httpx.HTTPError as e:
        return {"error": f"tool unreachable: {e}"}
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    if resp.status_code >= 400:
        return {"error": body.get("detail", body), "status": resp.status_code}
    return body


def _with_scoped(
    broker: BrokerClient,
    audience: str,
    scope: str,
    runner: Callable[[str], dict],
) -> dict:
    scoped = broker.exchange(audience=audience, scope=scope)
    if scoped.error is not None:
        return {
            "error": scoped.error,
            "permission_denied": True,
            "required_scope": scope,
            "audience": audience,
        }
    return runner(scoped.access_token or "")


# --- per-tool executors ----------------------------------------------------


def exec_list_customers(broker: BrokerClient, _params: dict) -> dict:
    return _with_scoped(
        broker,
        "customer-data",
        "customer-data:read",
        lambda tok: _call("GET", f"{CUSTOMER_DATA_URL}/customers", token=tok),
    )


def exec_get_customer(broker: BrokerClient, params: dict) -> dict:
    cid = params["customer_id"]
    return _with_scoped(
        broker,
        "customer-data",
        "customer-data:read",
        lambda tok: _call("GET", f"{CUSTOMER_DATA_URL}/customers/{cid}", token=tok),
    )


def exec_list_accounts(broker: BrokerClient, _params: dict) -> dict:
    return _with_scoped(
        broker,
        "finance-data",
        "finance-data:read",
        lambda tok: _call("GET", f"{FINANCE_DATA_URL}/accounts", token=tok),
    )


def exec_get_account(broker: BrokerClient, params: dict) -> dict:
    aid = params["account_id"]
    return _with_scoped(
        broker,
        "finance-data",
        "finance-data:read",
        lambda tok: _call("GET", f"{FINANCE_DATA_URL}/accounts/{aid}", token=tok),
    )


def exec_send_email(broker: BrokerClient, params: dict) -> dict:
    return _with_scoped(
        broker,
        "email-send",
        "email-send",
        lambda tok: _call(
            "POST",
            f"{EMAIL_SEND_URL}/send",
            token=tok,
            json_body={
                "to": params["to"],
                "subject": params["subject"],
                "body": params["body"],
            },
        ),
    )


TOOL_EXECUTORS: dict[str, Callable[[BrokerClient, dict], dict]] = {
    "list_customers": exec_list_customers,
    "get_customer": exec_get_customer,
    "list_accounts": exec_list_accounts,
    "get_account": exec_get_account,
    "send_email": exec_send_email,
}
