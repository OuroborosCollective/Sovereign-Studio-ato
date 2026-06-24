# OpenHands dedicated LLM proxy

OpenHands Enterprise uses a dedicated Cloudflare Workers AI bridge instead of the existing Sovereign LLM proxy when OpenHands needs an OpenAI-compatible endpoint.

## Public endpoint

```text
https://openhands-llm-proxy.projectouroboroscollective.workers.dev/v1
```

## Current model

```text
@cf/meta/llama-3.1-8b-instruct-fp8
```

## Runtime route

```text
OpenHands Enterprise
  -> openhands-llm-proxy Worker
  -> Cloudflare Workers AI
```

This path avoids LiteLLM virtual-key validation in the existing Sovereign LLM proxy and keeps provider secrets out of the Android app and repository.

## Required OpenHands server-side configuration

These values belong only on the VPS or server-side secret storage:

```bash
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://openhands-llm-proxy.projectouroboroscollective.workers.dev/v1
OPENAI_MODEL=@cf/meta/llama-3.1-8b-instruct-fp8
OPENAI_API_KEY=<server-side OpenHands proxy key>
```

The key must never be committed, printed in reports, returned by APIs, or embedded in the APK.

## Expected health response

```json
{
  "ok": true,
  "provider": "openhands-workers-ai-bridge",
  "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
  "authConfigured": true
}
```

## Verification gates

Before Sovereign Studio treats OpenHands as ready, all of these must be true:

1. The OpenHands proxy health endpoint returns `ok: true` and `authConfigured: true`.
2. A direct LLM smoke test through the proxy returns a real assistant response.
3. A real OpenHands job is started through the Sovereign backend.
4. The backend returns real OpenHands status/events, not a mock queue state.
5. `draftPrUrl` is set only when a real Draft PR exists.

## Security notes

- Do not expose Cloudflare tokens, OpenHands API keys, proxy keys, GitHub tokens, license files, or registry credentials.
- Rotate any value that is accidentally printed into chat, logs, screenshots, support bundles, or issue bodies.
- The Android app should know only the public Sovereign backend URL and OpenHands admin URL.
