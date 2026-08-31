# No-Code Integration Guide

## Generic dispatcher

Every no-code platform that can send HTTP POST can use:

```text
POST /api/v1/tools/{tool_name}
Content-Type: application/json
X-Toolchain-Key: optional-shared-secret

{"args": {...}}
```

## Useful tools

| Tool | Mode | Purpose |
| --- | --- | --- |
| `toolchain_briefing` | read | Project + sandbox context |
| `plan_sandbox_commands` | read | Safe CI/sandbox command plan |
| `github_read_file` | read | Read a file from allowed GitHub repo |
| `github_apply_search_replace_pr` | write with confirm | Create Draft PR via full-file replacement |
| `apply_patch_worker` | write with confirm | Call external `/git/patch` worker |
| `apply_backend_guardrails_patch_pr` | write with confirm | Apply embedded backend guardrails patch |

## n8n

Use an HTTP Request node:

- Method: `POST`
- URL: `https://your-domain.example/api/v1/tools/toolchain_briefing`
- Body: JSON
- JSON body: `{"args":{"include_rules":true}}`

See `adapters/n8n-http-node-example.json`.

### Sovereign CI evidence watch

`adapters/sovereign-ci-evidence-watch.n8n.json` is an importable, disabled-by-default workflow for public GitHub Actions observation. It polls every five minutes, reads recent workflow runs plus jobs, and sends only bounded run/job/step metadata to `sovereign_ci_evidence_receipt`.

Required non-secret configuration:

- `SOVEREIGN_N8N_REPOSITORY=OuroborosCollective/Sovereign-Studio-ato`
- `SOVEREIGN_N8N_EXPECTED_HEAD_SHA=<exact expected SHA-40>` when revision binding is required
- `SOVEREIGN_TOOLCHAIN_BASE_URL=<private/reverse-proxied toolchain URL>`

`SOVEREIGN_TOOLCHAIN_API_KEY` is a credential and must only be injected after the n8n editor/runtime is behind the approved HTTPS/auth/network boundary. Do not place repository, VPS, database, Docker-socket, or unrestricted GitHub credentials in this workflow. Public repository observation itself requires no GitHub token.

The workflow's n8n static data stores only `stateFingerprint` values to suppress duplicate delivery. This is a delivery cursor, not canonical state. A successful GitHub run produces `SUCCESS` observation evidence only; it never produces Sovereign `VERIFIED`. External effects remain governed by the durable workflow permission/execution receipt contract and require independent authoritative readback.

The adapter intentionally has no Linear write, workflow dispatch, merge, deploy, VPS, database, or PatchMon mutation node. Add those only as separate permission-bound effect steps whose exact payload/revision is approved by Sovereign and whose effect is independently read back.

Before activating the workflow on a self-hosted n8n instance:

1. remove direct public editor port exposure and place the editor behind the approved reverse proxy/HTTPS/auth path;
2. keep sandbox API/runner ports private and avoid host Docker-socket authority;
3. pin coordinated n8n/sandbox image versions rather than independently floating `latest` tags;
4. run the n8n security audit and verify execution-data redaction;
5. import the workflow while it remains `active=false`, configure the bounded environment values, run a manual canary, then activate it.

## Make / Zapier-like tools

Use a Webhook or HTTP action:

```json
{
  "args": {
    "goal": "verify"
  }
}
```

Endpoint:

```text
POST https://your-domain.example/api/v1/tools/plan_sandbox_commands
```

## Bubble / Retool

Import `schemas/openapi.json`, then bind UI actions to endpoints. Use `confirm=false` previews by default, and only send `confirm=true` from a visible confirmation button.
