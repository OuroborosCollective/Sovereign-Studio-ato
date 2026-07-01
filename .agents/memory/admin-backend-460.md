---
name: Admin Backend (#460)
description: Implementation notes for the Sovereign Studio admin backend, CI/CD, and secrets setup.
---

## VPS Backend
- Flask app at `/opt/sovereign-backend/app.py`, served by gunicorn on port 8787 (proxied via nginx to 8788)
- Docker Compose: `sovereign-backend` image, `extra_hosts: host.docker.internal:host-gateway` for DB access
- PostgreSQL via psycopg2 `ThreadedConnectionPool` — host = `host.docker.internal:5432`, db = `postgres`, user = `postgres`
- Auth: `require_admin` decorator checks `Authorization: Bearer <key>` against `ADMIN_API_KEY` env var
- `ADMIN_API_KEY` = long hex in GH secrets and VPS `.env`

## Database schema (supabase-db / postgres)
Tables: `admin_users`, `transactions`, `launcher_overrides`, `llm_routes`, `audit_log`
Seeded with demo data.

## GitHub Secrets (all 16 set)
`ADMIN_API_KEY`, `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `VITE_ADMIN_API_BASE`, `JWT_SECRET`, `LLM_PROXY_KEY`, `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`

## Frontend
- `src/features/admin/` — AdminPanel, AdminGate, hooks, components
- API client reads `VITE_ADMIN_API_BASE` env var (fallback to prod URL)
- `useUserStore` defaults `user: null`; real auth wired in Issue #459
- Hooks only fire after API key validated (gated by `ReadyContent` component)
- Registered as `sovereign-admin` launcher tool

## CI Workflow
`.github/workflows/build-and-deploy.yml`: deploy-backend job (SSH + docker rebuild) → build-apk job (Vite + cap sync + Gradle release)

**Why:** All secrets must be in GH secrets, never hardcoded in workflow YAML. Keystore must not be committed to git (stored as ANDROID_KEYSTORE_BASE64 secret instead).

## Known next steps
Issues #459 (User Account System), #458, #457, #456, #461 pending implementation.
