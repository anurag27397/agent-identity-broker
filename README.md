# agent-identity-broker

[![tests](https://img.shields.io/badge/tests-45%20passing-green)](#tests) [![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Identity governance for AI agents.** A working example of how to wire up agent-to-tool authorization without handing your LLM a long-lived god key.

Most "AI agent" demos give the LLM a single API key with full access to every tool. That works for prototypes and fails immediately in production: prompt injections walk straight into the database, audit trails point at "the bot," and security has no kill switch.

This repo is a runnable counter-example. The agent never holds tool credentials. Instead:

1. The **human user** authenticates once (Keycloak OIDC).
2. The **broker** issues a 1-hour session JWT bound to that user.
3. Before every tool call, the **agent** asks the broker for a 60-second **scoped token** for one specific tool and one specific scope.
4. The **tool** validates the scoped token against the broker's JWKS and serves the request (or refuses).
5. **Every step** is audited with stable `session_id` and `jti` correlation, viewable on a live HTMX dashboard.
6. The **operator** can revoke a session or engage a global kill switch with one click, mid-conversation.

The pattern is OAuth 2.1 token exchange (RFC 8693) applied to LLM agents. Most teams will end up here as soon as they move beyond prototypes.

---

## Quickstart (under 5 minutes)

Requirements: Docker Desktop, Python 3.12, an Anthropic API key.

```bash
git clone https://github.com/anurag27397/agent-identity-broker
cd agent-identity-broker
docker compose up -d --build
```

This brings up Postgres, Keycloak, the broker, and three mock tool services.

| Service       | URL                                      | Notes                                  |
|---------------|------------------------------------------|----------------------------------------|
| Broker        | http://localhost:8001                    | `/health`, `/docs`, `/dashboard`       |
| Keycloak      | http://localhost:8080                    | admin / admin                          |
| customer-data | http://localhost:8101                    | `/customers`, `/customers/{id}`        |
| finance-data  | http://localhost:8102                    | `/accounts`, `/accounts/{id}`          |
| email-send    | http://localhost:8103                    | `/send`                                |
| Dashboard     | http://localhost:8001/dashboard          | live audit + operator controls         |

Demo user: `alice` / `alice` (realm role: `analyst`).

---

## Demo it three ways

### 1. Login flow in your browser

1. Open http://localhost:8001/auth/login.
2. Sign in as `alice` / `alice`.
3. You'll see your session JWT and decoded payload. A cookie is set so http://localhost:8001/me works.

### 2. Exchange + tool call by hand

```bash
SESSION=$(curl -sS -X POST http://localhost:8001/auth/dev-login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"alice"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['session_token'])")

SCOPED=$(curl -sS -X POST http://localhost:8001/token/exchange \
  -H "Content-Type: application/json" \
  -d "{\"subject_token\":\"$SESSION\",\"audience\":\"customer-data\",\"scope\":\"customer-data:read\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -sS -H "Authorization: Bearer $SCOPED" http://localhost:8101/customers
```

Try to mint a token for `email-send`:

```bash
curl -sS -X POST http://localhost:8001/token/exchange \
  -H "Content-Type: application/json" \
  -d "{\"subject_token\":\"$SESSION\",\"audience\":\"email-send\",\"scope\":\"email-send\"}"
# -> 403 {"detail":"scope 'email-send' not granted to roles ['analyst']"}
```

Now open http://localhost:8001/dashboard. You'll see both calls in the audit feed, correlated by `session_id`. The successful call's `jti` matches the tool call's `jti`.

### 3. Claude as the agent

```bash
python3.12 -m venv agent/.venv && source agent/.venv/bin/activate
pip install -r agent/requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
python agent/main.py
```

Try:
- `list our customers`
- `what is the balance of account ACC-1004?`
- `summarize C001 in one line then email ops@example.com about it`

The third prompt is the interesting one: Claude calls `get_customer` (granted), then `send_email` (denied at the broker). The denial surfaces back to Claude as a `tool_result` error, and Claude explains the missing scope to alice in natural language.

---

## Operator controls

While the agent is running, open the dashboard.

- **Click a session** in the left rail to filter the event stream to just that session.
- **Revoke session.** Future `/token/exchange` calls for that session JWT return `403 session has been revoked`. In-flight 60-second scoped tokens still work until they expire.
- **Engage kill switch.** All token exchanges return `503 broker kill switch is engaged` until disengaged. Login still works; only minting is frozen.

Every action emits its own audit event. State persists across broker restarts.

---

## Architecture

```
+----------+      OIDC code flow       +-----------+
|   User   +--------------------------->  Keycloak |
+----+-----+                            +-----+-----+
     |                                        |
     | session JWT (1h)                       |
     v                                        |
+----+-----+                            +-----+-------+
|  Agent   +--------------------------->|             |
| (Claude) | POST /token/exchange       |   Broker    |
+----+-----+ (audience, scope)          |             |
     |                                  | + audit DB  |
     | scoped JWT (60s)                 | + revocation|
     |                                  +-----+-------+
     v                                        ^
+----+----+ +---------+ +-----------+         |
| customer| | finance | | email-send|---------+
|  -data  | |  -data  | |           | tool_call audit
+----+----+ +----+----+ +-----+-----+
     |          |             |
     +----------+-------------+
         each validates the scoped JWT
         against the broker's JWKS
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for sequence diagrams, threat model, and the production roadmap.

---

## Layout

```
broker/      FastAPI broker: OIDC login, session + scoped JWTs, JWKS,
             policy, audit, revocation, dashboard
broker/tests/      34 unit + integration tests
tools/       Three mock services sharing tool_lib (JWKS validator + audit middleware)
tools/tests/       11 unit tests
agent/       Claude agent (Anthropic SDK) that calls the broker + tools
keycloak/    IdP realm config (preconfigured demo user + client)
docs/        scope and architecture
ARCHITECTURE.md    design, sequence diagrams, threat model, prod roadmap
```

---

## Tests

```bash
# broker
docker compose exec broker python -m pytest tests/ -v

# tools
docker compose exec customer-data python -m pytest tests/ -v
```

Coverage: token mint/verify, policy decisions, exchange happy paths and denials,
revocation + kill switch state transitions and their effect on `/token/exchange`,
audit store reads/writes/aggregations, and per-tool JWKS validation
(audience mismatch, scope mismatch, expired, tampered).

---

## What this is not

- It is **not** a production broker. See [ARCHITECTURE.md](ARCHITECTURE.md#what-production-ready-would-look-like) for what would have to change.
- The policy is a hardcoded `dict`. Real deployments use OPA / Cedar.
- The revocation list is SQLite. Real deployments use Redis with TTL.
- The dev-login endpoint is an open password grant. Real agents authenticate through a dedicated trust path.

The point of this repo is to make the *pattern* concrete and runnable, not to be the artifact you ship to prod.

---

## License

MIT. See [LICENSE](LICENSE).
