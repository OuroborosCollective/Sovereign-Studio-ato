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
