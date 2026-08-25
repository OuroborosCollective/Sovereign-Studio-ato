# Sovereign Studio ATO — Current State

**Documentation snapshot:** 2026-08-03  
**Product architecture reconciled:** 2026-08-25
**Repository baseline:** `63ddbdf4ed8cd6fa895147e6b09dc39bb2330483`  
**Authority rule:** the current Git revision and fresh target-system readbacks override this dated snapshot.

## Purpose

This document is the short, current orientation layer for contributors and agents. It records what is present in the repository at the baseline above, what still requires runtime proof, and which older documentation patterns are no longer authoritative.

It does not replace:

- the current repository tree and exact Git blobs;
- runtime, CI, registry, database, container, image or PatchMon readbacks;
- `AGENTS.md` and the Continuity Policy for mutation rules;
- append-only continuity records;
- focused architecture documents for individual subsystems.

## Product identity

Sovereign Studio ATO is an Android-first, monitor-first NoCode/AI service and agent workbench for controlled work on real repositories and connected runtime systems. Natural-language interaction remains embedded in the monitor through a compact communication dock.

The canonical product rule remains:

```text
Runtime creates truth.
UI displays bounded projections of that truth.
Evidence and target-system readback decide completion.
```

The repository is proprietary and unlicensed for reuse except with prior express written permission from Thomas Markgraf for himself and OuroborosCollective. Third-party components retain their own licenses.

## Repository architecture at this baseline

### Frontend

- React 19, Vite 8 and Capacitor 6.
- Android-first delivery with a web build as the shared frontend artifact.
- Permanent monitor-first product surface under `src/features/product/`, with an embedded communication dock rather than a legacy chat-first body.
- Runtime and capability decisions belong in runtime modules, not in visual widgets or DOM text.
- GitHub, diff, workflow, runtime, health, memory and inspector views are bounded projections and inspection surfaces.

### Backend and agent runtime

- Canonical backend agent code lives under `backend/agent_runtime/`.
- Deployment mirrors under `scripts/sovereign-backend/agent_runtime/` must remain byte-equivalent where mirror ownership applies.
- Agent jobs, tasks, events, workspaces, tools, permissions, evidence and recovery are separate contracts; a model response or tool exit code is not target-system proof.
- Cross-user, cross-tenant, cross-repository, cross-workspace and cross-revision separation is mandatory.

### MCP control plane

- The repository MCP implementation lives under `tools/sovereign-chatgpt-mcp/`.
- Tool schemas, registry state, operating profile, continuity policy and deployment state must be read from the exact running revision.
- A repository implementation does not prove that the deployed MCP registry exposes the same tools.
- MCP self-update is valid only after immutable image, revision, digest, registry, protocol, container and PatchMon readback agree.

### Repository Intelligence & Evidence Lane

Merged repository functionality includes a clean-room Repository Intelligence & Evidence Lane with:

- revision-bound local repository indexing;
- Git-blob and content-hash readback;
- capability-scoped, hash-bound replace and restore operations;
- toolchain and schema diagnostics;
- deployment evidence sessions;
- bounded resource exploration;
- repository/context drift readback.

The index and parser/projection results are discovery side channels. The tracked file, exact Git blob, repository revision and external target readback remain canonical.

See [`architecture/REPOSITORY_INTELLIGENCE_EVIDENCE_LANE.v1.md`](architecture/REPOSITORY_INTELLIGENCE_EVIDENCE_LANE.v1.md).

### Evidence, continuity and rollback

- Continuity context and policy are mandatory before mutating MCP work.
- Continuity ledgers are append-only and mirrored according to their contract.
- Fleet deployment and rollback evidence must be bound to a real repository revision or immutable image digest.
- Liveness alone cannot prove revision parity, successful deployment or rollback readiness.
- A missing or unbound rollback reference fails closed.

### Integration Plan Lane (Issue #1112, added after the 2026-08-03 baseline)

- Revision-bound, owner-bound Integration Plan Lane implemented under
  `backend/agent_runtime/integration_plan_lane.py` (canonical) with
  byte-equivalent mirror at `scripts/sovereign-backend/agent_runtime/`.
- Path-safe filesystem adapter at `backend/agent_runtime/integration_plan_store.py`.
- Bounded helpers (canonical Markdown templates, context injection,
  gated completion evaluator, architecture snapshot + drift report,
  resume readback) at `backend/agent_runtime/integration_plan_helpers.py`.
- Stdlib-only inventory runner at
  `backend/agent_runtime/integration_plan_inventory.py` producing
  `docs/architecture/INTEGRATION_PLAN_LANE_INVENTORY.json` with 30
  surfaces, truth-class annotations and a drift report (currently
  zero drift).
- Persists the per-integration `.planning/<integration-id>/` tree
  (`task_plan.md`, `findings.md`, `progress.md`, `plan.receipt.json`,
  `evidence-index.json`, `ledger-actions.jsonl`, `.mode`,
  `.attestation`, `.active_revision`).
- Phase status is **never** set by Markdown alone; it is derived from
  machine-checkable `EvidenceRecord` entries whose kind matches the
  phase's declared required evidence kinds.
- The lane is a projection; runtime, CI, deployment and database truth
  remain canonical and are not replaced by the lane.
- See [`architecture/INTEGRATION_PLAN_LANE.v1.md`](architecture/INTEGRATION_PLAN_LANE.v1.md)
  for the full contract, schema versions and acceptance criteria.

### Provider routing

- Paid model routing is direct through OpenRouter.
- Free routing uses the repository's direct FreeLLM/Revolver surfaces.
- LiteLLM is historical/deactivated evidence and is not a supported product transport or rollback route.
- Repository configuration never proves that a provider route is currently selectable, funded or healthy; refresh and runtime evidence are required.

## Changes represented by the 2026-08-03 baseline

The baseline includes the repository results merged through:

- PR #1177 — Repository Intelligence & Evidence Lane;
- PR #1179 — secret-shaped literal remediation and tracked-fixture hardening;
- PR #1181 — revision- or digest-bound fleet rollback evidence.

These merge records prove repository changes. They do not by themselves prove live deployment parity.

## Planned, not implemented by this snapshot

Issue #1182 specifies a clean-room integration plan for:

1. Skill A/B and trigger-quality benchmarks;
2. per-mutation tool checkpoints;
3. deterministic context-pack receipts;
4. optional UI projections for bounded session permissions and asynchronous tasks.

Until code, tests, exact-head CI and required runtime readbacks exist, these remain planned work and must not be described as active product functionality.

## Required truth classes

Use these classes consistently:

- `IMPLEMENTED_IN_REPOSITORY` — present in tracked code at an exact revision.
- `TESTED_AT_REVISION` — relevant tests passed at an exact unchanged head.
- `CI_VERIFIED` — required GitHub checks are terminal green for that exact head.
- `ARTIFACT_VERIFIED` — artifact or image digest is bound to that revision.
- `DEPLOYED_UNVERIFIED` — deployment was attempted or observed but parity is incomplete.
- `RUNTIME_VERIFIED` — target-system revision, digest, configuration and behavior readbacks agree.
- `BLOCKED` — required evidence is missing or failed.
- `CONTRADICTED` — observations disagree.
- `PLANNED` — issue or design exists without completed implementation evidence.

Do not collapse these states into a single `done`, `green` or `healthy` label.

## Documentation drift removed by the 2026-08-03 reconciliation

The following patterns are no longer authoritative and must not be reintroduced:

- issues #500–#505 as the active architecture roadmap;
- claims that OpenHands is the only or required executor;
- direct `docker cp` hotpatching of running production containers;
- package installation inside running containers;
- unpinned `curl | bash`, `wget | sh`, npm, pip or system mutation;
- fixed VPS IP addresses, credentials, OAuth application IDs or ports in agent guidance;
- copied standalone test implementations that do not import the real live path;
- `draft=false` as a universal PR rule;
- `no auto-merge` phrased so broadly that it hides the explicit owner-scoped merge tool and its gates;
- old runtime/image SHAs presented as current without fresh readback;
- UI text, telemetry, liveness, model output or tool success used as Evidence.

Historical documents may retain old values as dated provenance. They must clearly defer to current Git and runtime readback.

## Current contributor reading order

1. [`../AGENTS.md`](../AGENTS.md)
2. [`SOVEREIGN_PRODUCT_TRUTH.md`](SOVEREIGN_PRODUCT_TRUTH.md)
3. [`SOVEREIGN_READER.md`](SOVEREIGN_READER.md)
4. [`sovereign-continuity/CONTEXT.md`](sovereign-continuity/CONTEXT.md)
5. the machine-readable Continuity Policy and latest append-only ledger head
6. the focused architecture document for the subsystem being changed
7. current open Issue/PR and exact GitHub checks

## Development and verification

The repository uses `pnpm@9.12.2` and Node.js 22 or newer.

Common checks:

```bash
pnpm run type-check
pnpm run test:unit
pnpm run test:integration
pnpm run test:release-gate
pnpm run build:web
pnpm run audit:sovereign
pnpm run audit:all
```

Run only the relevant bounded checks locally when dependencies are unavailable, and delegate Node-dependent or complete release checks to GitHub Actions. Report unavailable checks honestly.

The full repository verification contract is exposed by:

```bash
pnpm run verify
```

A successful local command is not a substitute for required exact-head CI, artifact and runtime evidence.

## Updating this snapshot

Create a new dated current-state file or deliberately replace this one only after:

1. resolving current `main`;
2. inventorying canonical and mirrored ownership;
3. comparing repository, issue, CI, artifact and runtime evidence;
4. removing superseded claims rather than stacking contradictory paragraphs;
5. preserving historical provenance in history/ledger surfaces;
6. binding the documentation change to a reviewable PR.
