# No-Code Integration Guide

## Generic dispatcher

Every no-code platform that can send HTTP POST can use:

```text
POST /api/v1/tools/{tool_name}
Content-Type: application/json
X-Toolchain-Key: required-shared-secret

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

### Sovereign and Aurion CI evidence watches

The disabled, declarative templates are:

- `adapters/sovereign-ci-evidence-watch.n8n.json`, pinned to
  `OuroborosCollective/Sovereign-Studio-ato` workflow
  `sovereign-coordinated-release.yml`;
- `adapters/aurion-ci-evidence-watch.n8n.json`, pinned to
  `OuroborosCollective/Echoes_of_Aurion` workflow ID `340269357`
  (`deploy-aurion-zone-runtime.yml`).

Each template contains only a 15-minute schedule and one credential-bound HTTP Request node. It
has no Code node, environment expression, direct GitHub request, or effect node. The request uses:

```text
POST http://host.docker.internal:8002/api/v1/n8n/ci-evidence
```

The body is direct and strict; it is not wrapped in `args`:

```json
{
  "owner": "OuroborosCollective",
  "repo": "Sovereign-Studio-ato",
  "branch": "main",
  "workflow_id": "sovereign-coordinated-release.yml"
}
```

The toolchain reads GitHub through its scoped GitHub App, resolves the selected workflow and current
branch head server-side, and returns deterministic workflow/run/job/step evidence. There is no
repo-wide latest-run fallback and n8n cannot supply the expected branch SHA.

The installer generates or preserves one high-entropy master key at
`/etc/sovereign-toolchain/n8n-evidence.key` as `root:root` mode `0600`. The full Toolchain app does
not receive it. The minimal evidence service runs as a systemd `DynamicUser` with a strict read-only
filesystem and receives the master through `LoadCredential`, never as an environment variable.

A trusted host-side provisioning worker derives a different lowercase-hex HMAC-SHA256 capability
for each exact lane. The HMAC key is the UTF-8 bytes of the master-key text. The message is:

```text
sovereign.n8n-ci-evidence-capability.v1
<owner>/<repo>
<workflow_id>
<branch>
```

Bind the Sovereign-derived value only to `Sovereign Toolchain Evidence` and the Aurion-derived value
only to `Aurion Toolchain Evidence`; both use header
`X-Sovereign-Evidence-Capability`. The listener rejects a missing or malformed capability before
parsing JSON and caps both declared and streamed request bodies at 4096 bytes. A lane capability cannot
authorize the other lane, and sending the raw master key is rejected. Replace each template's
matching credential-ID placeholder during import. Never place the master or derived values in Git,
workflow JSON, container environment, logs, or chat output.

Activate each imported workflow only after:

1. the Header Auth credential is bound;
2. a request without the credential returns 401 and a wrong value also returns 401;
3. the other lane's credential and the raw master key both return 401;
4. a manual execution succeeds for the exact repository, workflow, and branch;
5. the returned workflow identity and server-resolved branch-head comparison match.

A successful GitHub run remains observation evidence and still requires independent runtime
readback before Sovereign may call it verified. These adapters contain no workflow dispatch, merge,
deploy, VPS, database, Docker-socket, Linear, or PatchMon mutation node. Add effects only through
separate permission-bound plan/apply/readback contracts.

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
