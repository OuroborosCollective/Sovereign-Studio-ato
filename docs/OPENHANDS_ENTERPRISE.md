# OpenHands Enterprise integration

OpenHands Enterprise is integrated as an external agent runtime for Sovereign Studio, not as a generic LLM router.

Sovereign remains the Android-first user interface and runtime-truth monitor. OpenHands is the optional backend worker that can operate on a real repository workspace, run commands, collect diffs, and return a Draft PR result.

## Runtime boundary

```text
Sovereign Android/Web UI
  -> Sovereign backend endpoint
  -> OpenHands Enterprise agent runtime
  -> isolated repo workspace
  -> tests / diff / Draft PR
```

Sovereign UI must only display runtime events returned by the backend. It must not invent OpenHands job progress.

## What must not be committed

Do not commit any of these values:

- license YAML files
- download authorization headers
- registry usernames or passwords
- Cloudflare, GitHub, OpenHands, LiteLLM or provider API keys
- generated support bundles containing environment data

The uploaded enterprise license is an operator secret. Keep it on the deployment host or secret manager only.

## App-side configuration

The app reads only public, non-secret endpoint configuration:

```bash
VITE_OPENHANDS_ENABLED=true
VITE_OPENHANDS_AGENT_API_URL=https://your-sovereign-backend.example.com/openhands
VITE_OPENHANDS_ADMIN_CONSOLE_URL=https://your-openhands-admin.example.com
```

The mobile app must not receive the OpenHands license, registry password, provider key, or GitHub write token. Those belong behind the backend/runtime boundary.

## Enterprise single-node deployment outline

Use the vendor-provided assets and license on the target Linux host. The license file path is local to the host.

1. Set a private registry value:

```bash
export YOUR_PRIVATE_REGISTRY=registry.example.com
```

2. Download the vendor installation bundle using the current authorization from the enterprise dashboard. Do not paste that authorization into the repository.

3. Extract the bundle:

```bash
tar -xvzf openhands-stable.tgz
```

4. Mirror required images into the private registry:

```bash
pnpm openhands:mirror -- --registry "$YOUR_PRIVATE_REGISTRY" --apply
```

The mirror script uses the known OpenHands Enterprise image list, retags images under `$YOUR_PRIVATE_REGISTRY/openhands/...`, and pushes them. It does not know or print registry credentials.

5. Install on the host:

```bash
sudo ./openhands install \
  --license /secure/path/license.yaml \
  --registry "$YOUR_PRIVATE_REGISTRY/openhands" \
  --registry-username "$OPENHANDS_REGISTRY_USERNAME" \
  --registry-password "$OPENHANDS_REGISTRY_PASSWORD"
```

Use shell history protection or a secret manager for the password. If the installer supports a safer password input mode in your version, prefer that.

## Sovereign job contract

Sovereign sends a backend job request with these rules:

- real repository URL required
- mission required
- branch defaults to `main`
- Draft PR only
- no auto-merge
- runtime truth required

The TypeScript contract lives in:

```text
src/features/product/runtime/openhandsEnterpriseRuntime.ts
```

## Expected backend behavior

A backend endpoint that fronts OpenHands should expose a small job API for Sovereign:

```text
POST /openhands/jobs
GET  /openhands/jobs/:jobId
POST /openhands/jobs/:jobId/cancel
```

The backend should return only sanitized state:

```json
{
  "jobId": "job_123",
  "status": "running",
  "changedFiles": ["src/App.tsx"],
  "events": [
    { "at": 1234567890, "level": "info", "stage": "repo", "message": "Repository cloned" }
  ]
}
```

Never return raw tokens, registry passwords, provider keys, license content, or full environment dumps to the app.

## Status mapping

| OpenHands/Sovereign state | UI meaning |
| --- | --- |
| `idle` | no agent job started |
| `queued` | backend accepted the job |
| `running` | real agent runtime is active |
| `waiting-for-user` | user decision required |
| `blocked` | guard or runtime gate blocked output |
| `failed` | job failed with an error |
| `completed` | result available, usually Draft PR |

## LLM routing relationship

OpenHands is the agent runtime. LiteLLM or Cloudflare AI Gateway remains the model router. Do not make the Android app talk directly to model provider keys.

Recommended split:

```text
Sovereign normal model calls -> Cloudflare AI Gateway / LiteLLM
Sovereign repo work jobs     -> OpenHands Enterprise runtime
```

## Verification

Before enabling this in production:

```bash
pnpm run type-check
pnpm run test:unit -- src/features/product/runtime/openhandsEnterpriseRuntime.test.ts
pnpm run build:web
```

Then run one real OpenHands job against a test repository and confirm the UI shows only actual runtime events, changed files, checks, and Draft PR URL.
