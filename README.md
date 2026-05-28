# agent-identity-broker

Most "AI agent" demos give the LLM a long-lived API key with full access to every tool. That works for prototypes and fails immediately in production.

This repo is a working example of how to do it properly: a broker service that authenticates the human user, mints short-lived scoped tokens for each tool call, logs every action with a correlation ID, and lets the user revoke a session mid-conversation.

It demonstrates OAuth 2.1 token exchange (RFC 8693) applied to LLM agents, the pattern most teams will need as soon as they move beyond proofs of concept.

**Status:** in development. Week 5 of 8 (Claude agent with tool use).

## Quickstart

```bash
docker compose up --build
```

Then:

- Broker: http://localhost:8001 (`/health`, `/docs`, `/.well-known/jwks.json`)
- Keycloak admin: http://localhost:8080 (`admin` / `admin`)
- Demo user: `alice` / `alice` in realm `agent-broker`
- Tool services (mock):
  - customer-data: http://localhost:8101 (`/customers`, `/customers/{id}`)
  - finance-data: http://localhost:8102 (`/accounts`, `/accounts/{id}`)
  - email-send: http://localhost:8103 (`/send`)

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

## Call a tool end-to-end

```bash
# 1. Log in via browser at /auth/login, copy the session JWT.
SESSION="<your session JWT>"

# 2. Exchange for a scoped token.
SCOPED=$(curl -sS -X POST http://localhost:8001/token/exchange \
  -H "Content-Type: application/json" \
  -d "{\"subject_token\":\"$SESSION\",\"audience\":\"customer-data\",\"scope\":\"customer-data:read\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. Call the tool.
curl -sS -H "Authorization: Bearer $SCOPED" http://localhost:8101/customers
```

Each tool service fetches the broker's JWKS at `/.well-known/jwks.json`, validates the
signature, issuer, audience (must be its own tool ID), expiry, and the required scope.
Failure modes return 401 (auth) or 403 (scope) with a clear reason.

## Talk to the agent

Claude calls the same broker + tools you just exercised by hand.

```bash
python3.12 -m venv agent/.venv && source agent/.venv/bin/activate
pip install -r agent/requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...  # your personal key
python agent/main.py
```

The agent logs in as alice, then runs a chat loop. For every tool call Claude
wants to make, the agent asks the broker for a 60-second scoped JWT first.
Allowed calls execute; denied calls (e.g. `send_email` for the analyst role)
surface back to Claude, which explains the denial to alice.

Sample prompts:

- `list our customers`
- `what is the balance of account ACC-1004?`
- `summarize C001 in one line then email ops@example.com about it` (demonstrates the denial)

See [`agent/README.md`](agent/README.md) for details.

## Run tests

```bash
docker compose exec broker python -m pytest tests/ -v
docker compose exec customer-data python -m pytest tests/ -v
```

## Layout

```
broker/      FastAPI service: OIDC login, session JWTs, scoped JWTs, JWKS
broker/tests/    18 unit + integration tests
tools/       Three mock services sharing tool_lib (JWKS validator)
tools/tests/     11 unit tests covering happy paths and rejection cases
agent/       Claude agent (Anthropic SDK) that calls the broker + tools
keycloak/    IdP realm config (preconfigured demo user + client)
docs/        scope and architecture
```

