# Sovereign Reader — Current Contributor Map

**Reconciled:** 2026-08-03  
**Repository baseline:** `63ddbdf4ed8cd6fa895147e6b09dc39bb2330483`

This is the practical orientation layer for contributors. It explains where current responsibilities live, how to classify evidence and which older route assumptions are obsolete.

Read first:

1. [`../AGENTS.md`](../AGENTS.md)
2. [`CURRENT_STATE_2026-08-03.md`](CURRENT_STATE_2026-08-03.md)
3. [`SOVEREIGN_PRODUCT_TRUTH.md`](SOVEREIGN_PRODUCT_TRUTH.md)
4. [`sovereign-continuity/CONTEXT.md`](sovereign-continuity/CONTEXT.md)
5. current Continuity Policy and ledger head

## Product shape

Sovereign Studio ATO is Android-first and chat-first.

```text
User talks to Sovereign.
Runtime resolves capability, permission and evidence boundaries.
Tools operate only inside staged scopes.
Target systems provide readback.
UI displays the bounded result and next allowed action.
```

Chat remains the default room. Repository, files, diff, workflow, runtime, health, memory and inspector surfaces are opened for inspection; they do not become a separate truth-producing dashboard.

## Current repository map

| Area | Entry point | Responsibility |
| --- | --- | --- |
| App shell | `src/App.tsx` | frontend shell and navigation |
| Product surfaces | `src/features/product/` | chat workbench, runtime projections and guarded user actions |
| Product runtime | `src/features/product/runtime/` and related runtime modules | state transitions, route decisions and frontend contracts |
| GitHub integration | `src/features/github/` | repository access and frontend GitHub surfaces |
| Backend agent runtime | `backend/agent_runtime/` | canonical jobs, tasks, tools, permissions, evidence and recovery |
| Backend deployment mirror | `scripts/sovereign-backend/agent_runtime/` | mirror requiring parity where the ownership contract applies |
| Backend tests | `backend/tests/` | real-path and contract tests |
| MCP control plane | `tools/sovereign-chatgpt-mcp/` | repository, CI, continuity, deployment and runtime operations |
| Migrations | `backend/migrations/` plus governed mirror | database contracts; not proof of production application |
| Architecture | `docs/architecture/` | focused subsystem contracts |
| Continuity | `docs/sovereign-continuity/` plus MCP mirror | context, policy and append-only handoff evidence |

## Current functional model

```text
natural-language request
↓
model response and structured action candidate
↓
runtime validation and exact identity resolution
↓
capability snapshot and permission decision
↓
read-only response, GitHub operation, isolated workspace, MCP or operator tool
↓
execution result/receipt
↓
independent repository, CI, artifact, registry, DB, container or PatchMon readback
↓
classified state and next action
```

The model interprets language. It does not decide that a capability exists, a mutation is allowed or a target effect occurred.

## Capability boundaries

Sovereign composes bounded capabilities rather than routing everything through one executor.

Examples:

- local/runtime answer;
- model/provider answer;
- repository read and Repository Intelligence;
- hash-bound repository patch/restore;
- GitHub Issue, PR and workflow operations;
- isolated workspace and test execution;
- backend/MCP evidence tools;
- deployment and self-update operations;
- continuity, memory and learning projections.

OpenHands may be used as an optional workspace executor. It is not the product's only write path and is not a provider route.

## Repository Intelligence & Evidence Lane

The clean-room lane under `tools/sovereign-chatgpt-mcp/` provides revision-bound repository discovery and controlled operations.

Important rules:

- Index/search results are side channels.
- Read the exact tracked file and Git blob before mutation.
- Capability scope, repository SHA and blob SHA must match.
- Replace/restore affects only the isolated working tree until a separate commit/PR/merge path succeeds.
- Schema and toolchain diagnostics are findings, not runtime proof.
- Deployment/context drift observations require target readback.

See [`architecture/REPOSITORY_INTELLIGENCE_EVIDENCE_LANE.v1.md`](architecture/REPOSITORY_INTELLIGENCE_EVIDENCE_LANE.v1.md).

## Neuro-inspired MCP verification lane

The clean-room lane under `tools/sovereign-chatgpt-mcp/` is additive to the
existing control plane. It registers exactly five tools on the existing
FastMCP instance and consumes the live registry and predictive router; it does
not create another server, registry, router, code server or execution path.

Its deterministic flow is:

```text
canonical ChangeEvent + temporal envelope
→ relevance and optional bounded spike filter
→ sparse selection from the live MCP registry
→ proposal-only candidate
→ Foundation verification
→ idempotent, hash-chained admission evidence
```

Unknown event or Foundation kinds, stale revision/policy bindings, registry
drift, source-head conflicts, invalid teaching provenance and incomplete
cross-ledger admissions fail closed. The Foundation and neuromorphic ledgers
are evidence stores, not an alternative source of tool authority. Persistent
outcome tracking is limited to mutating tools; read-only tools do not write
ranking or neuromorphic state. Tracking is a best-effort side channel and must
never change the primary tool result or exception.

Repository presence is `IMPLEMENTED_IN_REPOSITORY`, not deployment proof. A
live claim additionally requires exact-head CI, an immutable revision-labelled
image, five-tool registry readback, protocol/container identity and PatchMon
verification. See
[`architecture/NEURO_ARCHITECTURE_FOUNDATION.v1.md`](architecture/NEURO_ARCHITECTURE_FOUNDATION.v1.md).

## Backend and mirror ownership

Before changing backend agent code:

1. identify the canonical module under `backend/agent_runtime/`;
2. identify any governed deployment mirror under `scripts/sovereign-backend/agent_runtime/`;
3. change both where required;
4. run real-path tests and parity checks;
5. list both paths in continuity and PR evidence.

A running-container copy is never the canonical fix.

## GitHub workflow

```text
resolve current main
→ isolated branch/workspace
→ bounded edit
→ targeted checks
→ continuity handoff
→ Draft PR
→ read exact PR head and checks
→ explicit owner approval
→ merge exact head
→ resolve new main
```

Draft PR is the default review boundary, not a claim that every PR must remain draft forever. The private owner-scoped merge path is valid only when exact-head, approval and gate contracts are satisfied.

## Provider routing

- Direct OpenRouter for paid routes.
- Direct FreeLLM/Revolver surfaces for free routes.
- No LiteLLM product or rollback route.
- Provider configuration must be refreshed and validated; Git configuration alone does not prove availability or health.

## Evidence classes

Use:

- `IMPLEMENTED_IN_REPOSITORY`
- `TESTED_AT_REVISION`
- `CI_VERIFIED`
- `ARTIFACT_VERIFIED`
- `DEPLOYED_UNVERIFIED`
- `RUNTIME_VERIFIED`
- `BLOCKED`
- `CONTRADICTED`
- `PLANNED`

Examples:

- merged code without deployment readback: `IMPLEMENTED_IN_REPOSITORY`;
- green exact-head checks: `CI_VERIFIED`;
- running container with unknown digest: `DEPLOYED_UNVERIFIED`;
- liveness but revision mismatch: `CONTRADICTED`;
- Issue #1182 before implementation: `PLANNED`.

## Verification commands

Common local checks from `package.json`:

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

Use focused `pytest` commands for affected backend/MCP tests. Run dependency-heavy aggregate gates through GitHub Actions when the local environment is not prepared.

## Deployment reader

The only valid release sequence is immutable and revision-bound:

```text
reviewed revision
→ exact-head CI
→ merge revision
→ immutable image digest
→ controlled deployment/self-update
→ registry/protocol/container/revision/digest/PatchMon readback
```

Do not use direct container file copies, in-container dependency installs or mutable images as release evidence.

## Current planned quality integration

Issue #1182 plans:

- Skill A/B and trigger-quality benchmarks;
- checkpoints before mutating tool calls;
- deterministic context-pack receipts;
- optional UI projections for bounded permission profiles and asynchronous tasks.

These are not active capabilities until separately implemented and verified.

## Obsolete route guidance

The following no longer defines the current architecture:

- issues #500–#505 as the active route roadmap;
- small docs changes being inherently tied to a special old Direct Patch v1 route;
- OpenHands as a required executor;
- fixed VPS IP/port and OAuth application details in contributor docs;
- manual production hotpatch instructions;
- permanently accepted pre-existing test failures.

Use the current repository, current open Issues/PRs and exact evidence instead.

## Before declaring success

Report:

- source and final revisions;
- changed paths;
- checks actually run;
- exact-head GitHub status;
- artifact/image digest where applicable;
- deployment/runtime readbacks where applicable;
- unavailable evidence and blockers;
- final truth class.
