# agent-identity-broker

Most "AI agent" demos give the LLM a long-lived API key with full access to every tool. That works for prototypes and fails immediately in production.

This repo is a working example of how to do it properly: a broker service that authenticates the human user, mints short-lived scoped tokens for each tool call, logs every action with a correlation ID, and lets the user revoke a session mid-conversation.

It demonstrates OAuth 2.1 token exchange (RFC 8693) applied to LLM agents, the pattern most teams will need as soon as they move beyond proofs of concept.

**Status:** in development. Week 3 of 8 (scoped token exchange).

## Quickstart

```bash
docker compose up --build
```

Then:

- Broker: http://localhost:8001 (`/health`, `/docs`, `/.well-known/jwks.json`)
- Keycloak admin: http://localhost:8080 (`admin` / `admin`)
- Demo user: `alice` / `alice` in realm `agent-broker`

## Try the login flow

1. Open http://localhost:8001/auth/login in a browser.
2. Sign in as `alice` / `alice` on the Keycloak page.
3. You land on a page showing your session JWT and decoded payload.
4. `session_token` is also set as an HttpOnly cookie, so http://localhost:8001/me returns your claims.

The session token is signed with RS256 using a key generated on first startup and published at `/.well-known/jwks.json`. Tool services downstream will verify against that JWKS in later weeks.

## Try token exchange

Once you have a session token, exchange it for a 60-second scoped token:

```bash
SESSION="<your session JWT>"

curl -sS -X POST http://localhost:8001/token/exchange \
  -H "Content-Type: application/json" \
  -d "{\"subject_token\":\"$SESSION\",\"audience\":\"customer-data\",\"scope\":\"customer-data:read\"}"
```

Allowed for `alice` (role `analyst`): `customer-data:read`, `finance-data:read`.
Denied for `alice`: `email-send`, `customer-data:write`. Denials return HTTP 403 with the reason.

Policy lives in [`broker/policy.py`](broker/policy.py) as a hardcoded role-to-scope map.

## Run tests

```bash
docker compose exec broker python -m pytest tests/ -v
```

## Layout

```
broker/      FastAPI service: OIDC login, session JWTs, JWKS
broker/tests/    unit tests
keycloak/    IdP realm config (preconfigured demo user + client)
docs/        architecture, scope
```

