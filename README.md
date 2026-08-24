# Sovereign Studio ATO

[![Frontend: React + Vite](https://img.shields.io/badge/Frontend-React%2019%20%2B%20Vite%208-646CFF)](package.json)
[![Mobile: Capacitor Android](https://img.shields.io/badge/Mobile-Capacitor%206-119EFF)](android/)
[![Process: Evidence first](https://img.shields.io/badge/Process-Evidence%20first-111827)](docs/SOVEREIGN_PRODUCT_TRUTH.md)
[![Truth: Runtime readback](https://img.shields.io/badge/Truth-Runtime%20readback-6D28D9)](docs/CURRENT_STATE_2026-08-03.md)

[![GitHub Stars](https://img.shields.io/github/stars/OuroborosCollective/Sovereign-Studio-ato?style=social)](https://github.com/OuroborosCollective/Sovereign-Studio-ato/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/OuroborosCollective/Sovereign-Studio-ato?style=social)](https://github.com/OuroborosCollective/Sovereign-Studio-ato/network)
[![GitHub Issues](https://img.shields.io/github/issues/OuroborosCollective/Sovereign-Studio-ato)](https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues)
[![GitHub PRs](https://img.shields.io/github/issues-pr/OuroborosCollective/Sovereign-Studio-ato)](https://github.com/OuroborosCollective/Sovereign-Studio-ato/pulls)

Sovereign Studio ATO is an Android-first NoCode/AI service and agent workbench for controlled work on real repositories and connected runtime systems. Chat remains the control and question surface; during a live, workspace-bound execution the runtime monitor becomes the primary work surface without hiding the user's ability to communicate.

> [!IMPORTANT]
> **Proprietary software — all rights reserved.** Sovereign-Studio-ato is not open source. Use, execution, copying, modification, coding, adaptation, derivative works, model training, deployment, hosting, distribution or commercialization require prior express written permission from Thomas Markgraf for himself and OuroborosCollective. Third-party components retain their own licenses. See [LICENSE](LICENSE).

## Current documentation baseline

The dated orientation snapshot remains [`docs/CURRENT_STATE_2026-08-03.md`](docs/CURRENT_STATE_2026-08-03.md), but this README describes the current architecture contract rather than pinning a historical repository SHA.

The authoritative code identity is always the exact current Git or PR head being reviewed. Git, CI, image, registry, database, container and PatchMon readbacks take precedence over dated documentation and UI state.

## Product truth

```text
Runtime creates truth.
UI displays bounded projections of that truth.
Evidence and target-system readback decide completion.
```

Consequences:

- Chat is the idle/control surface and remains available for missions, questions and required user decisions.
- A fresh, workspace-bound live projection promotes the Desktop/Live Workspace Monitor to the primary execution surface; stale projections or `waiting-for-user` return interaction to chat.
- The monitor exposes only bounded runtime observations. It never upgrades a projection into Evidence or completion truth.
- A compact, non-overlay communication dock keeps the monitor visible while the user asks questions. `THINK` is limited to observable runtime status; `COMMUNICATE` contains user-visible responses and never exposes hidden model reasoning.
- Repository, files, diff, workflow, runtime, health, memory and inspector views are inspection surfaces.
- UI text, telemetry, liveness, model output and tool success are not target-system Evidence.
- A repository implementation is not automatically deployed.
- A deployed container is not automatically revision- or digest-matched.
- A completed tool call is at most `SUCCEEDED_UNVERIFIED` until the required readback exists.
- No mock, stub, facade or hardcoded green state may enter the live path.

## Current architecture

```text
Android / Web frontend
        │
        ├── Chat / mission / question controls
        │
        └── Live Workspace Monitor when a fresh bound runtime projection exists
                         │
                         ▼
                Typed Engine Boundary
       commands ─────────┼───────── canonical events
                         │
                         ▼
            Sovereign backend / agent runtime
                         │
            capability + consent + policy gates
                         │
                         ▼
       isolated workspace / GitHub / MCP / providers
                         │
                         ▼
             execution observations + receipts
                         │
                         ▼
          independent target-system readbacks
                         │
                         ▼
        verified evidence / next allowed action
```

### Typed Engine Boundary

Product state is not allowed to change merely because a model emitted text, a tool returned success or a UI control was clicked. Frontend/engine transitions cross a typed boundary: UI intent becomes a typed command, and only an accepted canonical typed engine event may mutate canonical product state. Replay, stale, malformed or foreign events remain non-mutating.

This keeps the following classes separate:

```text
assistant/model text  -> presentation or advisory content
UI interaction        -> command request
projection event      -> bounded observation
runtime/target readback -> evidence candidate
typed accepted engine event -> canonical product-state transition
```

### Live Workspace Monitor and communication

During an active run, a fresh projection bound to the current workspace/attempt makes the Live Workspace Monitor the primary surface. The monitor can expose Editor, Diff, Terminal, Browser and Window-Focus observations, but only from allowlisted projection fields and with secret redaction. Missing observations remain visibly empty rather than simulated.

The monitor does not force the user back into a full chat view to ask a question. A compact dock remains in normal document flow below the monitor, so it does not cover the desktop surface. It supports user questions plus bounded `THINK` and `COMMUNICATE` bubbles. `THINK` reports only observable runtime status; it is not chain-of-thought or hidden reasoning. When the runtime explicitly enters `waiting-for-user`, or when only stale projection evidence remains, the normal chat/control surface becomes primary again.

### Frontend -> endpoint assurance

The frontend endpoint contract is checked independently from runtime health. A deterministic repository scanner inventories production `/api/...` references, normalizes dynamic path parameters and Blueprint prefixes, and binds active internal frontend references to real backend route owners. Unbound active endpoints fail closed. External and retired bridges are classified explicitly and are never counted as backend/runtime proof.

The runtime layer is separate: Playwright smoke probes are GET-only, reject missing routes, redirects and server errors, preserve authentication boundaries, and never invoke mutating methods merely to prove reachability. A passing static endpoint contract therefore does **not** imply deployment, authentication, business-effect or revision parity.

### Main repository surfaces

| Area | Canonical path | Responsibility |
| --- | --- | --- |
| Frontend shell | `src/App.tsx` | application shell and navigation |
| Product workbench | `src/features/product/` | chat/control surface, typed runtime state and live-monitor projections |
| Backend agent runtime | `backend/agent_runtime/` | jobs, tasks, tools, permissions, evidence and recovery |
| Backend deployment mirror | `scripts/sovereign-backend/agent_runtime/` | deployment mirror where canonical ownership requires parity |
| MCP control plane | `tools/sovereign-chatgpt-mcp/` | repository, CI, runtime, continuity and operational tools |
| Continuity | `docs/sovereign-continuity/` and MCP continuity data | context, policy and append-only handoff records |
| Architecture docs | `docs/architecture/` | focused contracts and evidence lanes |

### Browser mirror of the Android app

The user-facing web test surface is `/app/`; `/admin/` is a separate, authenticated backend administration surface and is not the APK user interface. Both are built from the revision-bound Vite output, while the route boundary selects the correct entry surface: `/app/` mounts `src/App.tsx`, and `/admin/` mounts the admin panel. The Android release continues to embed the product build under `android/app/src/main/assets/public/`.

## Implemented repository capabilities

At the current architecture baseline, the repository contains:

- React/Vite/Capacitor product surfaces with chat/control mode and runtime-monitor-primary execution mode;
- a typed engine boundary that separates UI intent, canonical events and product-state mutation;
- a receipt-bound Live Workspace Monitor with non-overlay user communication and observable-status bubbles;
- deterministic frontend-to-backend endpoint assurance with fail-closed ownership checks and GET-only runtime smoke coverage;
- backend agent jobs, tasks, events, workspaces and tool contracts;
- GitHub, PR, workflow and evidence-oriented operations;
- direct paid OpenRouter routing and direct FreeLLM/Revolver free routing;
- MCP control-plane and self-update contracts;
- continuity policy, context and mirrored append-only ledgers;
- Repository Intelligence & Evidence Lane with revision/blob/hash binding;
- capability-scoped replace and restore operations;
- schema, toolchain, deployment and context-drift diagnostics;
- revision- or digest-bound fleet rollback evidence.

### Neuro-inspired MCP verification lane

The MCP repository also contains an additive, clean-room verification lane that
keeps the existing FastMCP server, live tool registry, predictive router and
plugin endpoint authoritative. Its current truth class is
`IMPLEMENTED_IN_REPOSITORY`; exact-head CI, immutable-image and runtime
readbacks are still required before it may be called live.

The lane provides five tools for contract status, event preview, idempotent
event admission and evidence-bound teaching simulation. It combines canonical
change/delta events, temporal ordering, sparse capability selection and a
separate deterministic Foundation decision. Candidates are proposal-only:
they cannot execute tools, promote lessons or perform external effects. Local
SQLite ledgers are revision/policy/hash bound, replay-safe and independently
verified; the existing MCP registry remains the only tool authority.

See [`docs/architecture/NEURO_ARCHITECTURE_FOUNDATION.v1.md`](docs/architecture/NEURO_ARCHITECTURE_FOUNDATION.v1.md).

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
pnpm run test:frontend-endpoints
pnpm run test:release-gate
pnpm run test:e2e
pnpm run build:web
pnpm run audit:sovereign
pnpm run audit:all
```

A dedicated live endpoint smoke is intentionally opt-in and read-only:

```bash
VITE_ADMIN_API_BASE=https://<deployed-backend> pnpm run test:e2e:endpoints-live
```

It performs GET probes only. `405` may demonstrate that a non-GET route exists without authorizing the test to invoke its mutating method; `404`, redirects and server errors remain failures.

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
- Every implementation or fix must be followed by its relevant regression/runtime-contract check before the next material code step; unavailable environments remain explicitly unverified.
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
