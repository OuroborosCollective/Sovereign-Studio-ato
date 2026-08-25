# Agent Knowledge Base — Sovereign Studio ATO

**Reconciled:** 2026-08-25
**Revision authority:** exact current Git or PR head; never infer it from this document

This file records durable, repository-specific knowledge. It is not a changelog, credential store, runtime status page or substitute for current Git and target-system readback.

## 1. Truth hierarchy

Use this order when sources disagree:

1. exact current Git revision and blob;
2. schema-valid canonical repository contract;
3. exact-head tests and GitHub checks;
4. immutable artifact/image digest bound to that revision;
5. target-system revision, digest, registry, database, container and PatchMon readbacks;
6. dated documentation and continuity records;
7. model output, telemetry and UI projections.

A lower item cannot overrule a higher item.

## 2. Repository map

| Surface | Canonical location | Notes |
| --- | --- | --- |
| Frontend | `src/` | React/Vite/Capacitor monitor-first workspace, embedded communication dock and inspection surfaces |
| Product runtime | `src/features/product/runtime/` and related runtime modules | capability decisions and state transitions belong here, not in DOM text |
| Backend agent runtime | `backend/agent_runtime/` | canonical jobs, tasks, tools, evidence, permission and recovery code |
| Backend mirror | `scripts/sovereign-backend/agent_runtime/` | deployment mirror; byte parity is required where ownership applies |
| Backend migrations | `backend/migrations/` and deployment mirror | migrations are contracts, not proof they ran in production |
| MCP | `tools/sovereign-chatgpt-mcp/` | repository, CI, deployment, continuity and operational tooling |
| Architecture docs | `docs/architecture/` | focused subsystem contracts |
| Continuity | `docs/sovereign-continuity/` plus MCP mirror | context, policy and append-only ledger |
| Learning | `.sovereign/`, learning logbook and proven-learning tools | candidates require evidence before promotion |

## 3. Current stable architecture knowledge

### Monitor-first product

- The Live Workspace Monitor is the permanent primary user surface.
- Natural-language interaction stays in the embedded communication dock; no legacy full-chat body becomes primary.
- Repo, files, diff, workflow, runtime, telemetry, health, memory and inspector views are bounded inspection surfaces.
- Runtime state allows, blocks or routes the next action.
- UI state must not manufacture readiness, progress or completion.

### Agent runtime

- Model reasoning, tool execution, permissions, evidence and target readback are separate layers.
- A tool call can complete without its intended target effect being verified.
- Jobs, child tasks and events must remain owner/tenant/repository/workspace/revision scoped.
- Unknown or ambiguous tool contracts fail closed.

### GitHub work

- Isolated branch/workspace first.
- Draft PR is the default review boundary.
- Merge requires explicit owner approval, exact head binding, mergeability and relevant green checks.
- After merge, resolve `main` again; do not reuse the PR head as the merge revision.

### Provider routing

- Paid: direct OpenRouter.
- Free: direct FreeLLM/Revolver surfaces.
- LiteLLM is historical/deactivated and must not return as a transport or rollback path.
- Price, model and route snapshots must be schema-valid and refreshed; numeric-looking strings require canonical normalization rather than unhandled 500s.

### Repository Intelligence & Evidence Lane

Current repository functionality includes:

- revision-bound local FTS5/discovery indexing;
- deterministic token/content projections;
- Git-blob and content-hash readback;
- capability-scoped, hash-bound replace and restore;
- managed toolchain verification without installation;
- schema, workflow and Compose diagnostics;
- deployment evidence sessions;
- bounded resource exploration;
- context/revision/digest drift readback.

The index, parser and projection results are side channels. Canonical truth remains the tracked file, exact Git blob, revision and required external readback.

### Neuro-inspired MCP verification lane

- Extend the existing FastMCP server and live registry; never introduce a
  parallel MCP, registry, router, code server or automatic effect lane.
- The canonical neuro contract has governed byte-identical runtime mirrors;
  parity is a tested deployment invariant.
- Change events bind delta identity, time/order, source head, repository
  revision and continuity-policy hash.
- Relevance, bounded spike filtering, resource homeostasis and predictive
  routing are advisory. Candidate receipts are proposal-only and cannot
  execute tools.
- Foundation verification is explicit, fail-closed and persisted in its own
  transactionally hash-chained ledger. A recovery intent binds the
  neuromorphic and Foundation receipts without pretending two SQLite commits
  are one atomic transaction.
- Teaching packages require bounded, hash-bound provenance and exact live tool
  contracts. Assessment/simulation cannot promote learning or execute tools.
- Mutating-tool outcome projections are incremental and quota-bounded.
  Read-only tools do not persist ranking or neuromorphic state. Tracking errors
  must never replace the wrapped tool result or its original exception.
- Status readback must use the same canonical integrity verifier used for
  events, heads, projections and metrics; SQLite `quick_check` alone is not
  evidence of semantic integrity.
- Five additive tools are registered. Never infer or document a total live
  tool count without registry readback from the exact deployed revision.

### Continuity

- Continuity context and policy are read before mutating MCP work.
- Both ledgers are append-only and mirror-bound.
- Every mutating handoff records source revision, mission, decisions, changed paths, evidence, open items and privacy status.
- Raw chat and secrets do not belong in continuity records.

### Deployment and rollback

- Direct edits in a running container are not a release.
- Immutable image build precedes deployment/self-update.
- Revision, image digest, registry, protocol, container and PatchMon must agree.
- Rollback evidence must identify a real prior revision or immutable digest.
- Liveness alone is insufficient.

## 4. Recent repository facts represented by the baseline

The baseline includes repository merges for:

- PR #1177: Repository Intelligence & Evidence Lane;
- PR #1179: secret-shaped literal remediation and secret-scan fixture hardening;
- PR #1181: fail-closed fleet rollback evidence bound to revision or digest.

These are repository facts, not automatic proof of current live deployment parity.

## 5. Planned integration knowledge

Issue #1182 defines planned clean-room work for:

- Skill A/B and trigger-quality evaluation;
- per-mutating-tool checkpoints;
- deterministic context-pack receipts;
- optional bounded permission and asynchronous-task UI projections.

Do not write documentation, UI or tests as though these are already implemented.

## 6. Testing lessons that remain valid

- Tests should import the real implementation.
- Use shared rendering/test helpers for components that require providers rather than duplicating ad hoc setup.
- Prefer exact contract assertions for security and evidence fields; use partial matching only when additional fields are intentionally irrelevant.
- Test stale hashes, replay, cross-scope access, unknown fields and missing evidence, not only happy paths.
- Mocks may isolate external adapters but cannot prove product behavior or runtime effects.
- Canonical and deployment-mirror modules need parity tests.
- A synthetic secret fixture must never resemble a usable credential.

## 7. Documentation lessons

- Remove superseded instructions rather than appending corrections beneath them.
- Dated runtime SHAs, image digests, issue lists and provider states are historical provenance.
- Current-state documents identify their date and baseline revision.
- `IMPLEMENTED_IN_REPOSITORY`, `CI_VERIFIED`, `ARTIFACT_VERIFIED`, `DEPLOYED_UNVERIFIED`, `RUNTIME_VERIFIED` and `PLANNED` are distinct states.
- Contributor docs must not contain infrastructure addresses, credentials, OAuth application IDs or mutable production commands.

## 8. Removed knowledge drift

The following former guidance is explicitly obsolete:

- manual `docker cp` updates to production;
- installing Python or system packages inside live containers;
- password-based SSH examples and unknown-host acceptance;
- fixed VPS ports/IPs as current architecture truth;
- copied standalone production logic inside tests;
- `draft=false` as a universal PR rule;
- OpenHands as the only write-capable executor;
- old issues #500–#505 as the active route plan;
- a known failing test treated as permanently unrelated;
- old commit lists presented as current state.

## 9. Updating this knowledge base

Update this file only for durable lessons that are supported by current repository evidence. Put event history in `docs/UPDATE_HISTORY.md`, subsystem detail in `docs/architecture/`, personal/relational provenance in the continuity context, and runtime state in evidence/readback surfaces.
