# Sovereign Studio ATO

[![Frontend: React + Vite](https://img.shields.io/badge/Frontend-React%2019%20%2B%20Vite%208-646CFF)](package.json)
[![Mobile: Capacitor Android](https://img.shields.io/badge/Mobile-Capacitor%206-119EFF)](android/)
[![Process: Evidence first](https://img.shields.io/badge/Process-Evidence%20first-111827)](docs/SOVEREIGN_PRODUCT_TRUTH.md)
[![Truth: Runtime readback](https://img.shields.io/badge/Truth-Runtime%20readback-6D28D9)](docs/CURRENT_STATE_2026-08-03.md)

Sovereign Studio ATO is an Android-first, chat-first NoCode/AI service and agent workbench for controlled work on real repositories and connected runtime systems.

> [!IMPORTANT]
> **Proprietary software — all rights reserved.** Sovereign-Studio-ato is not open source. Use, execution, copying, modification, coding, adaptation, derivative works, model training, deployment, hosting, distribution or commercialization require prior express written permission from Thomas Markgraf for himself and OuroborosCollective. Third-party components retain their own licenses. See [LICENSE](LICENSE).

## Current documentation baseline

The current orientation snapshot is:

- [`docs/CURRENT_STATE_2026-08-03.md`](docs/CURRENT_STATE_2026-08-03.md)
- repository baseline: `63ddbdf4ed8cd6fa895147e6b09dc39bb2330483`

The baseline is dated provenance, not a permanent runtime claim. Current Git, CI, image, registry, database, container and PatchMon readbacks always take precedence.

## Product truth

```text
Runtime creates truth.
UI displays bounded projections of that truth.
Evidence and target-system readback decide completion.
```

Consequences:

- Chat is the default product surface.
- Repository, files, diff, workflow, runtime, health, memory and inspector views are inspection surfaces.
- UI text, telemetry, liveness, model output and tool success are not target-system Evidence.
- A repository implementation is not automatically deployed.
- A deployed container is not automatically revision- or digest-matched.
- A completed tool call is at most `SUCCEEDED_UNVERIFIED` until the required readback exists.
- No mock, stub, facade or hardcoded green state may enter the live path.

## Current architecture

```text
Android/Web frontend
  ↓
chat-first product runtime
  ↓
Sovereign backend and agent runtime
  ↓
capability, permission and evidence contracts
  ↓
GitHub / isolated workspaces / MCP / provider routes / operational systems
  ↓
result and execution receipts
  ↓
independent target-system readbacks
  ↓
UI projection and next allowed action
```

### Main repository surfaces

| Area | Canonical path | Responsibility |
| --- | --- | --- |
| Frontend shell | `src/App.tsx` | application shell and navigation |
| Product workbench | `src/features/product/` | chat-first UI and runtime projections |
| Backend agent runtime | `backend/agent_runtime/` | jobs, tasks, tools, permissions, evidence and recovery |
| Backend deployment mirror | `scripts/sovereign-backend/agent_runtime/` | deployment mirror where canonical ownership requires parity |
| MCP control plane | `tools/sovereign-chatgpt-mcp/` | repository, CI, runtime, continuity and operational tools |
| Continuity | `docs/sovereign-continuity/` and MCP continuity data | context, policy and append-only handoff records |
| Architecture docs | `docs/architecture/` | focused contracts and evidence lanes |

### Browser mirror of the Android app

The user-facing web test surface is `/app/`; `/admin/` is a separate, authenticated backend administration surface and is not the APK user interface. Both are built from the revision-bound Vite output, while the route boundary selects the correct entry surface: `/app/` mounts `src/App.tsx`, and `/admin/` mounts the admin panel. The Android release continues to embed the product build under `android/app/src/main/assets/public/`.

## Implemented repository capabilities

At the documented baseline, the repository contains:

- chat-first React/Vite/Capacitor product surfaces;
- backend agent jobs, tasks, events, workspaces and tool contracts;
- GitHub, PR, workflow and evidence-oriented operations;
- direct paid OpenRouter routing and direct FreeLLM/Revolver free routing;
- MCP control-plane and self-update contracts;
- continuity policy, context and mirrored append-only ledgers;
- Repository Intelligence & Evidence Lane with revision/blob/hash binding;
- capability-scoped replace and restore operations;
- schema, toolchain, deployment and context-drift diagnostics;
- revision- or digest-bound fleet rollback evidence.

See [`docs/CURRENT_STATE_2026-08-03.md`](docs/CURRENT_STATE_2026-08-03.md) for the exact distinction between repository implementation, tests, CI, artifacts, deployment and runtime verification.

## Planned work is not active functionality

Issue [#1182](https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/1182) specifies planned clean-room work for:

- Skill A/B and trigger-quality benchmarks;
- per-mutation tool checkpoints;
- deterministic context-pack receipts;
- optional bounded permission and asynchronous-task UI projections.

These capabilities remain `PLANNED` until code, tests, exact-head CI and required runtime readbacks exist.

## Provider truth

- Paid routes: direct OpenRouter.
- Free routes: direct FreeLLM/Revolver surfaces.
- LiteLLM: historical/deactivated evidence only; not a supported product transport or rollback route.
- Provider configuration in Git does not prove model availability, pricing validity, funding or runtime health.

## Contributor reading order

1. [`AGENTS.md`](AGENTS.md)
2. [`docs/CURRENT_STATE_2026-08-03.md`](docs/CURRENT_STATE_2026-08-03.md)
3. [`docs/SOVEREIGN_PRODUCT_TRUTH.md`](docs/SOVEREIGN_PRODUCT_TRUTH.md)
4. [`docs/SOVEREIGN_READER.md`](docs/SOVEREIGN_READER.md)
5. [`docs/sovereign-continuity/CONTEXT.md`](docs/sovereign-continuity/CONTEXT.md)
6. the machine-readable Continuity Policy and latest ledger head
7. the focused subsystem document and current Issue/PR

## Local development

Requirements:

- Node.js 22 or newer
- `pnpm@9.12.2`

```bash
pnpm install
pnpm run dev
```

Common bounded checks:

```bash
pnpm run type-check
pnpm run test:unit
pnpm run test:integration
pnpm run test:release-gate
pnpm run build:web
pnpm run audit:sovereign
pnpm run audit:all
```

Full verification:

```bash
pnpm run verify
```

Android debug build:

```bash
pnpm run build:apk:debug
```

Do not claim a check was run when dependencies or the required environment were unavailable. Local success does not replace required exact-head GitHub Actions, artifact or runtime Evidence.

## Change and release rules

- Start from an isolated workspace or review branch based on the exact current revision.
- Read canonical and mirrored ownership before changing backend or MCP code.
- Prefer bounded search/replace or small-file replacement with stale-SHA protection.
- Draft PR is the default review boundary.
- Merge is allowed only through the explicit owner-scoped path with exact head binding, mergeability and required green checks.
- Direct mutation of running containers and package installation inside them are not release methods.
- Build immutable images first; deploy and self-update only after digest/revision evidence is available.
- Read back revision, digest, registry, protocol, container and PatchMon state after deployment.

## Documentation map

- [`docs/CURRENT_STATE_2026-08-03.md`](docs/CURRENT_STATE_2026-08-03.md) — current dated orientation and removed drift.
- [`docs/SOVEREIGN_PRODUCT_TRUTH.md`](docs/SOVEREIGN_PRODUCT_TRUTH.md) — non-negotiable product and evidence rules.
- [`docs/SOVEREIGN_READER.md`](docs/SOVEREIGN_READER.md) — practical contributor map.
- [`docs/architecture/REPOSITORY_INTELLIGENCE_EVIDENCE_LANE.v1.md`](docs/architecture/REPOSITORY_INTELLIGENCE_EVIDENCE_LANE.v1.md) — repository intelligence truth boundaries.
- [`docs/SOVEREIGN_ARCHITECTURE_MANIFEST.md`](docs/SOVEREIGN_ARCHITECTURE_MANIFEST.md) — broad historical architecture handbook; dated runtime literals require fresh readback.
- [`docs/sovereign-continuity/CONTEXT.md`](docs/sovereign-continuity/CONTEXT.md) — continuity and provenance context.
- [`AGENTS_KNOWLEDGE.md`](AGENTS_KNOWLEDGE.md), [`AGENTS_SKILLS.md`](AGENTS_SKILLS.md), [`AGENTS_BEST_PRACTICES.md`](AGENTS_BEST_PRACTICES.md) — current operational guidance.
