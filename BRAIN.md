# Sovereign Project Brain

schema: sovereign.brain-projection.v1  
truth_class: DERIVED_PROJECTION  
runtime_verified: false

This file is the Git-native project-brain entrypoint for coding agents working on **Sovereign Studio ATO**. It adapts the useful `brain.md` idea without importing a second memory database, agent runtime, approval system, or technical truth source.

The projection exists to make durable decisions, requirements, constraints, boundaries, and history easier to discover across ChatGPT, Codex, Claude Code, and other repository-aware coding agents. It is intentionally subordinate to the canonical repository, CI, artifact, deployment, database, MCP, container, and PatchMon evidence lanes.

## compiled_truth

- Repository: `OuroborosCollective/Sovereign-Studio-ato`.
- Sovereign Studio ATO and **Arelorian Wasd remain separate projects**. No shared runtime or technical truth is implied here.
- The canonical product rule remains: runtime creates truth; projections display bounded views; independent readback decides technical completion.
- `BRAIN.md` and `brain/*.md` are navigation and context compression only. They cannot grant authority, prove a test, create a PR, prove a merge, prove deployment, or upgrade a state to `RUNTIME_VERIFIED`.
- Existing Continuity context and historical ledgers remain provenance surfaces. The GitHub `continuity-ledger` workflow is **advisory historical evidence only** and must not block PR integration, merge, release, artifact publication, deployment, or runtime verification.
- Paid LLM routing is direct OpenRouter; free routing belongs to the direct FreeLLM/Revolver architecture. LiteLLM is not a supported runtime or rollback path.
- Agent-authored repository changes use reviewable branches/PRs and exact-head evidence. Owner-scoped merge authority does not remove revision or target-system readback requirements.
- Secrets never belong in this project brain, its manifest, Continuity records, PR text, logs, or generated projections.

Canonical sources are hash-bound in `brain/manifest.json`. If a canonical source or brain page changes, `scripts/sovereign_brain_projection.py check` fails until the projection is deliberately reviewed and its manifest refreshed.

## pages

- [`brain/architecture.md`](brain/architecture.md) — canonical ownership, runtime boundaries, and where this projection sits.
- [`brain/current-state.md`](brain/current-state.md) — truth classes and how to read current state without promoting stale documentation.
- [`brain/decisions.md`](brain/decisions.md) — durable technical and governance decisions worth carrying between agents.
- [`brain/runtime-truth.md`](brain/runtime-truth.md) — evidence hierarchy and target-system readback rules.
- [`brain/workflows.md`](brain/workflows.md) — repository/PR/release operating flow.
- [`brain/roadmap.md`](brain/roadmap.md) — planned work and the rule against presenting plans as active functionality.
- [`brain/continuity.md`](brain/continuity.md) — the bounded role of Continuity as provenance/history rather than a GitHub blocker.

## usage

Read this file for orientation, then read the canonical source needed for the task. Before relying on a claim, inspect its source and the current target-system evidence.

```bash
python3 scripts/sovereign_brain_projection.py check
python3 -m unittest scripts.test_sovereign_brain_projection -v
```

After a deliberate update to canonical sources or brain pages:

```bash
python3 scripts/sovereign_brain_projection.py refresh
python3 scripts/sovereign_brain_projection.py check
```

`refresh` updates only the hash manifest. It does not invent summaries, alter canonical source files, or claim runtime success.

## timeline

Historical causality remains in Git history, Issues/PRs, CI runs, receipts, Continuity records, artifact/image metadata, deployment evidence, and runtime/PatchMon readbacks. This page deliberately points to those records instead of replacing them with an agent-written narrative.
