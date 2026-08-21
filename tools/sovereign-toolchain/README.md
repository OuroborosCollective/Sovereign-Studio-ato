# Sovereign Universal Toolchain

Reusable toolchain for Sovereign Studio, the sandbox bundle, GitHub Draft-PR patching, no-code workspaces, and LLM agents.

It is intentionally not tied to one chat. The same package exposes four integration surfaces:

1. **MCP** at `/mcp` for MCP-compatible clients and agent workspaces.
2. **REST/OpenAPI** at `/api` for no-code tools such as n8n, Make, Zapier-like HTTP actions, Retool, Bubble, custom dashboards, and app backends.
3. **Generic tool dispatcher** at `/api/v1/tools/{name}` for agent routers.
4. **CLI/scripts** for local repo and CI workflows.

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
- REST integrations can require `X-Toolchain-Key`

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

With API key:

```bash
curl -X POST https://your-domain.example/api/v1/tools/github_read_file \
  -H "Content-Type: application/json" \
  -H "X-Toolchain-Key: $TOOLCHAIN_API_KEY" \
  -d '{"args":{"owner":"OuroborosCollective","repo":"Sovereign-Studio-ato","path":"README.md","ref":"main"}}'
```

## MCP usage

```bash
uv run python -m sovereign_toolchain.mcp_server
```

Or deploy the hybrid server and connect clients to:

```text
https://your-domain.example/mcp
```

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
