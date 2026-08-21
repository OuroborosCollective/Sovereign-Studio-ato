# Workspace Embedding Patterns

## Pattern A: Agent workspace with MCP

Connect the workspace to:

```text
https://your-domain.example/mcp
```

Use this when the workspace supports MCP and tool discovery.

## Pattern B: No-code workspace with OpenAPI

Import:

```text
https://your-domain.example/api/openapi.json
```

Use `POST /v1/tools/{name}` for a stable universal action.

## Pattern C: App backend integration

Your app backend calls the toolchain REST API; mobile/web clients never receive GitHub/OpenAI secrets.

```text
Client App → Your Backend → Sovereign Toolchain → GitHub / Patch Worker
```

## Pattern D: CI helper

Use the CLI inside CI:

```bash
sovereign-toolchain plan_sandbox_commands --args '{"goal":"verify"}'
```
