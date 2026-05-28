# Keycloak setup

The `realm-export.json` file is imported on container start by `start-dev --import-realm`.

## What's preconfigured

- **Realm**: `agent-broker`
- **Demo user**: `alice` / `alice` (email `alice@example.com`, role `analyst`)
- **Client**: `broker` (confidential, secret `broker-secret-change-me`)
- **Roles**: `analyst`, `admin`

## Admin console

After `docker compose up`, the Keycloak admin console is at http://localhost:8080.

- Username: `admin`
- Password: `admin`

## Reimport after changes

If you change `realm-export.json`, the import only runs on a fresh DB. To reimport:

```bash
docker compose down -v   # drops the postgres volume
docker compose up
```
