# agent-identity-broker

Most "AI agent" demos give the LLM a long-lived API key with full access to every tool. That works for prototypes and fails immediately in production.

This repo is a working example of how to do it properly: a broker service that authenticates the human user, mints short-lived scoped tokens for each tool call, logs every action with a correlation ID, and lets the user revoke a session mid-conversation.

It demonstrates OAuth 2.1 token exchange (RFC 8693) applied to LLM agents, the pattern most teams will need as soon as they move beyond proofs of concept.

**Status:** in development. Week 1 of 8 (scaffolding).

## Quickstart

```bash
docker compose up --build
```

Then:

- Broker: http://localhost:8000 (health at `/health`, API docs at `/docs`)
- Keycloak admin: http://localhost:8080 (`admin` / `admin`)
- Demo user: `alice` / `alice` in realm `agent-broker`

## Layout

```
broker/      FastAPI service that issues scoped tokens
keycloak/    IdP realm config (preconfigured demo user + client)
docs/        architecture, scope
```

