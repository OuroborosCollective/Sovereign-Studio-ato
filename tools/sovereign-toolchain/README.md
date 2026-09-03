# Sovereign Universal Toolchain

Reusable toolchain for Sovereign Studio, the sandbox bundle, GitHub Draft-PR patching, no-code workspaces, and LLM agents.

It is intentionally not tied to one chat. The package has two deliberately separate network boundaries:

1. The full **MCP**, **REST/OpenAPI**, and generic dispatcher app binds only to `127.0.0.1:8001` on a deployed host. MCP and authenticated REST tool routes require `X-Toolchain-Key` and fail closed when `TOOLCHAIN_API_KEY` is absent.
2. The minimal n8n CI-evidence listener binds on port `8002` for container-to-host access. It exposes only `/healthz` and `POST /api/v1/n8n/ci-evidence`; it has no MCP, OpenAPI, general tools, or write surface.
3. **CLI/scripts** remain available for local repo and CI workflows.

## What it combines

- Sovereign Studio repo intelligence from the uploaded Studio archive.
- Sandbox/runtime planning from the uploaded Node 22 / pnpm 9 / Playwright bundle profile.
- Safe GitHub Contents API file reads and Draft PR writes.
- The Sovereign `/git/patch` worker payload.
- Your `apply_toolchain_patch_guardrails.py` and `apply_toolchain_patch_guardrails_via_github_api.sh` guardrail flow.

## Safety model

The default write model is deliberately strict:

- no direct writes to `main`
- write actions require `confirm=true`
- GitHub writes use a new branch and Draft PR
- repos must be in `ALLOWED_REPOS`
- SEARCH/REPLACE blocks must match exactly once
- optional `expected_sha` prevents stale previews from being applied
- MCP and authenticated REST integrations require `X-Toolchain-Key`; the installer preserves or creates a root-only 64-hex capability and proves a real MCP initialize handshake
- the n8n listener accepts only two exact repository/workflow/branch lanes, each with its own HMAC-derived capability
- evidence calls mint a separate repository-scoped GitHub App token with only Actions/Contents read permissions; full Toolchain write authority is not inherited
- the n8n master key stays in a root-owned systemd credential and is never an n8n credential
- deployment is materialized from the exact Git commit archive; a root-only manifest verifies two-service rollback by revision, file hashes, directory identity, service state, and socket boundary

## Install

```bash
uv sync
cp .env.example .env
uv run uvicorn sovereign_toolchain.app:app --host 127.0.0.1 --port 8000
```

Open:

```text
REST manifest: http://127.0.0.1:8000/api/v1/manifest
OpenAPI:       http://127.0.0.1:8000/api/openapi.json
MCP endpoint:  http://127.0.0.1:8000/mcp
```

## No-code usage

Import `schemas/openapi.json` into a no-code HTTP/OpenAPI connector, or call the generic dispatcher:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tools/plan_sandbox_commands \
  -H "Content-Type: application/json" \
  -d '{"args":{"goal":"verify"}}'
```

On the deployed host, or through a trusted loopback proxy, use the authenticated full-app listener:

```bash
curl -X POST http://127.0.0.1:8001/api/v1/tools/github_read_file \
  -H "Content-Type: application/json" \
  -H "X-Toolchain-Key: $TOOLCHAIN_API_KEY" \
  -d '{"args":{"owner":"OuroborosCollective","repo":"Sovereign-Studio-ato","path":"README.md","ref":"main"}}'
```

## MCP usage

```bash
uv run python -m sovereign_toolchain.mcp_server
```

A deployed hybrid server listens only on `http://127.0.0.1:8001/mcp`. Every `/mcp` path requires exactly one `X-Toolchain-Key` header. Any remote access must use a separately authenticated trusted tunnel or loopback proxy; do not publish port `8001`.

## Apply the backend guardrails patch as Draft PR

Preview first:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tools/apply_backend_guardrails_patch_pr \
  -H "Content-Type: application/json" \
  -d '{"args":{"confirm":false}}'
```

Create Draft PR:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tools/apply_backend_guardrails_patch_pr \
  -H "Content-Type: application/json" \
  -H "X-Toolchain-Key: $TOOLCHAIN_API_KEY" \
  -d '{"args":{"confirm":true}}'
```

## Local guardrail script

The original scripts are preserved in:

```text
scripts/patches/apply_toolchain_patch_guardrails.py
scripts/patches/apply_toolchain_patch_guardrails_via_github_api.sh
```

## Archive access

The package stores a compact profile of the uploaded archives. To let agents read actual archive files, mount the ZIPs and set:

```bash
SOVEREIGN_STUDIO_ZIP=/archives/Sovereign-Studio-ato-main.zip
SOVEREIGN_SANDBOX_ZIP=/archives/sovereign-sandbox-dev-linux-node22-pnpm9-playwright.zip
```
