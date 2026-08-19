---
name: sovereign-mission-control
description: Plan and execute multi-step Sovereign Studio ATO repository missions with exact-revision identity, continuity, bounded authority, causal repair loops and authoritative readback.
---

# Sovereign Mission Control

Use this skill for substantial, multi-step or mutating Sovereign work.

## Canonical sources

Read the current repository copies of:

1. `AGENTS.md`
2. `.github/copilot-instructions.md`
3. `docs/SOVEREIGN_PRODUCT_TRUTH.md`
4. `docs/CURRENT_STATE_2026-08-03.md` as dated orientation only
5. `docs/sovereign-continuity/CONTEXT.md`
6. `tools/sovereign-chatgpt-mcp/config/sovereign-continuity-policy.json`
7. the current append-only ledger head and focused subsystem architecture

When the Sovereign MCP is available, the canonical MCP operation workflow remains `tools/sovereign-chatgpt-mcp/skills/sovereign-mcp-optimal-operation/SKILL.md`; this GitHub skill does not replace it.

## Sequence

- Resolve repository, base/workspace/PR and relevant runtime revision identities.
- Determine effect class and evidence required before editing.
- Search for canonical ownership and mirrors.
- Decompose into dependency-aware tasks and delegate independent analysis where useful.
- Implement the smallest causal patch.
- Run focused checks, then relevant broader checks.
- Use an independent verifier for significant work.
- On recoverable failure, classify the failure family and repair the earliest causal source rather than weakening the gate.
- Before idempotency-sensitive retry, read the target state.
- After effects, obtain authoritative target-system readback.
- Report scoped truth classes and unresolved evidence gaps.

Never turn a plan, model answer, tool exit code or projection into runtime truth.