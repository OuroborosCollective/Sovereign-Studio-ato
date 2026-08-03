# Sovereign Studio ATO — Copilot Instructions

Before changing anything, read:

1. `AGENTS.md`
2. `docs/CURRENT_STATE_2026-08-03.md`
3. `docs/SOVEREIGN_PRODUCT_TRUTH.md`
4. the focused subsystem document and current Issue/PR

## Core contract

```text
Runtime creates truth.
UI displays bounded projections.
Evidence and target-system readback decide completion.
```

## Required behavior

- Resolve the exact current revision before editing.
- Work in an isolated branch/workspace.
- Read canonical and deployment-mirror ownership.
- Prefer small bounded edits with stale-SHA protection.
- Keep model reasoning, permission, tool execution, evidence and readback separate.
- Use structured failure states; do not parse success from prose.
- Import and test the real implementation.
- Preserve cross-owner, cross-tenant, cross-repository, cross-workspace and cross-revision isolation.
- Keep continuity ledgers append-only.
- Draft PR is the default review boundary.
- Merge requires explicit owner approval for the exact PR head and relevant green checks.

## Forbidden behavior

- No mock/stub/facade or hardcoded green state in live code.
- No UI/DOM text, telemetry, liveness, model output or tool exit code as target-system truth.
- No secrets or secret-shaped credential values in code, tests, docs, chat, logs, Issues, PRs or ledgers.
- No direct production container hotpatching.
- No package installation inside running containers.
- No `curl | bash`, `wget | sh` or unknown plugin/skill execution.
- No reintroduction of LiteLLM.
- No new parallel agent, queue, memory, MCP, approval or evidence truth layer without an approved architecture contract.
- No copied production logic inside tests.
- No stale SHAs, image digests, ports or old issue lists presented as current.

## Repository map

- Frontend: `src/`
- Product runtime: `src/features/product/runtime/` and related runtime modules
- Canonical backend agent runtime: `backend/agent_runtime/`
- Governed backend mirror: `scripts/sovereign-backend/agent_runtime/`
- MCP control plane: `tools/sovereign-chatgpt-mcp/`
- Architecture docs: `docs/architecture/`
- Continuity: `docs/sovereign-continuity/` and governed MCP mirror

## Common checks

```bash
pnpm run type-check
pnpm run test:unit
pnpm run test:integration
pnpm run test:release-gate
pnpm run build:web
pnpm run audit:sovereign
pnpm run audit:all
```

Use focused real-path Python tests for affected backend/MCP modules. Report unavailable checks honestly and rely on exact-head GitHub Actions for required aggregate gates.

## Completion report

Always state:

- source/final revision;
- changed paths;
- checks actually run;
- exact-head CI state;
- artifact/deployment/runtime evidence where applicable;
- blockers and final truth class.
