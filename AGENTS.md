# Repository Agent Rules

This file is mandatory reading for every agent, model, Copilot session, automation and human contributor working in this repository.

## Project identity

Repository: `OuroborosCollective/Sovereign-Studio-ato`  
Product: Sovereign Studio ATO  
Owner authority: Thomas Markgraf for himself and OuroborosCollective

Do not mix this repository with Arelorian Wasd, game runtimes, ARE/Kappa truth claims or unrelated projects unless the owner explicitly requests a bounded integration.

## Mandatory reading order

Before any mutation, read:

1. this file;
2. `docs/CURRENT_STATE_2026-08-03.md`;
3. `docs/SOVEREIGN_PRODUCT_TRUTH.md`;
4. `docs/sovereign-continuity/CONTEXT.md`;
5. the machine-readable Continuity Policy;
6. the latest append-only continuity ledger head;
7. the focused architecture document and current Issue/PR for the task.

A dated document never overrides current Git or fresh runtime readback.

## Prime directive

```text
Runtime creates truth.
UI displays bounded projections of that truth.
Evidence and target-system readback decide completion.
```

Every workflow must preserve this causal chain:

```text
action
→ result
→ persisted or bound state
→ next allowed, blocked or approval-required action
→ independent target-system readback
```

Do not advance because a button is visible, a model says it succeeded, an exit code is zero, telemetry emitted an event or a container is merely alive.

## Truth classes

Use explicit states rather than a generic `done`:

- `IMPLEMENTED_IN_REPOSITORY`
- `TESTED_AT_REVISION`
- `CI_VERIFIED`
- `ARTIFACT_VERIFIED`
- `DEPLOYED_UNVERIFIED`
- `RUNTIME_VERIFIED`
- `BLOCKED`
- `CONTRADICTED`
- `PLANNED`

A tool result, model answer, UI state, liveness probe or workflow dispatch cannot create `RUNTIME_VERIFIED`.

## Preflight before mutation

1. Resolve the exact current `main` revision.
2. Check open PRs, related issues and any existing uncommitted workspace.
3. Create or use an isolated workspace/branch based on that exact revision.
4. Read canonical versus deployment-mirror ownership.
5. Identify effect class: inspect, mutate, coordinate or deploy.
6. Resolve required owner approval, permission and evidence contracts.
7. Read continuity context, policy and current ledger head from the same revision.
8. Define the relevant checks and target-system readbacks before editing.

Unknown ownership, missing revision binding or missing permission fails closed.

## Repository ownership and mirrors

Canonical backend agent code lives under:

```text
backend/agent_runtime/
```

Deployment mirrors may exist under:

```text
scripts/sovereign-backend/agent_runtime/
```

Where mirror ownership applies, both paths must remain byte-equivalent and tests must verify parity. Do not patch only the deployment copy or only the canonical copy.

The MCP control plane lives under:

```text
tools/sovereign-chatgpt-mcp/
```

Repository implementation does not prove deployed registry parity. Verify the running MCP revision and registry after an immutable deployment.

The revision-bound Integration Plan Lane lives under:

```text
backend/agent_runtime/integration_plan_lane.py
backend/agent_runtime/integration_plan_store.py
backend/agent_runtime/integration_plan_helpers.py
backend/agent_runtime/integration_plan_inventory.py
```

The lane persists the per-integration ``.planning/<integration-id>/`` tree (task_plan, findings, progress, evidence-index, plan.receipt, ledger-actions, .mode, .attestation, .active_revision). Plan status is always a **projection** derived from machine-checkable evidence. It is never a truth source for repository, CI, artifact, image, deployment, database or runtime state. The lane never replaces the canonical continuity ledger. The inventory runner writes `docs/architecture/INTEGRATION_PLAN_LANE_INVENTORY.json` and a drift report; it is stdlib-only and non-mutating.

## Change rules

- Prefer bounded search/replace with exact match count and stale-SHA protection.
- Blind full-file replacement is forbidden for large or high-risk files.
- Keep changes narrowly scoped to the task and current architecture.
- Do not create a second agent runtime, queue, memory store, MCP registry, approval system or evidence truth layer when an existing canonical surface can be extended.
- Do not add provider routes outside the canonical direct OpenRouter paid and direct FreeLLM/Revolver free architecture without a separately approved design.
- LiteLLM is not a supported runtime or rollback path.
- No unknown plugin, skill, archive or binary may enter the repository or runtime without static inspection, license review, provenance, pinning and required approval.

## Security and supply-chain rules

Never:

- store or reveal secrets, tokens, credentials, private keys or secret-shaped fixture values;
- put secrets in chat, logs, docs, Issue/PR bodies, ledgers, tests or tool arguments;
- use `curl | bash`, `wget | sh` or equivalent remote execution;
- install npm, pip or system packages into a running production container;
- use mutable `latest` images for evidence-bound deployment;
- trust a package or skill because of its name, vendor or URL prefix;
- use `AutoAddPolicy` or silently accept unknown SSH host keys;
- authorize from client-supplied owner, tenant, repository or workspace IDs without server-side resolution;
- promote sanitized or model-transformed content to verified evidence.

Secret-like test fixtures must use synthetic formats that are explicitly excluded or redacted by the repository scanner without containing valid credentials.

## Testing rules

Tests must import and exercise the real live-path implementation. Do not copy production logic into a standalone test and call that coverage.

Minimum useful coverage for new contracts:

- success;
- expected failure;
- invalid input;
- stale revision or hash;
- cross-scope/replay denial;
- permission or approval boundary;
- mirror parity where applicable;
- target-system readback boundary.

Mocks are allowed only at external adapter boundaries inside tests. They cannot count as product or runtime proof.

## Local and CI checks

Use the smallest relevant check first, then required aggregate gates.

Common commands:

```bash
pnpm run type-check
pnpm run test:unit
pnpm run test:integration
pnpm run test:release-gate
pnpm run build:web
pnpm run audit:sovereign
pnpm run audit:all
```

Full repository verification:

```bash
pnpm run verify
```

Python checks should run against the canonical module and its actual dependencies. If the environment cannot run a check, report it as unavailable and delegate it to GitHub Actions. Never claim it passed.

## PR and merge rules

- Draft PR is the default review boundary for generated or agent-authored work.
- A Draft PR must contain real, reviewable changes, not only a plan or generated preview.
- Do not mark a PR ready until the exact current head has the required terminal checks.
- Merge requires explicit owner approval, exact PR head SHA, confirmed mergeability and relevant green gates.
- A merge tool must not infer approval from a previous task or from general repository access.
- After merge, resolve the new `main` revision again.

## Deployment and self-update rules

Direct edits to a running container are not a release method.

Required order:

```text
reviewed exact head
→ required CI
→ merge exact head
→ immutable image bound to merge revision
→ registry digest readback
→ controlled deployment/self-update
→ revision, digest, protocol, registry, container and PatchMon readback
```

A self-update is incomplete if any required identity is missing, stale or contradictory. Rollback evidence must reference a real prior revision or immutable digest.

## Continuity rules

Continuity ledgers are append-only. Do not rewrite or reorder old entries.

Before Draft PR creation, direct main push or merge, append the required redacted handoff entry with:

- source revision and mission;
- decisions;
- complete changed paths;
- checks and evidence;
- open items;
- bound context and policy hashes;
- privacy/redaction status;
- mandatory experience rubrics required by the Continuity Policy.

Never store raw chat transcripts or secrets in continuity files.

## Documentation rules

Documentation is a claim surface and must use the same truth classes as code and operations.

- Remove superseded instructions instead of stacking contradictory paragraphs.
- Historical SHAs, images, ports and issue lists must be labeled historical.
- Current-state documents must name their baseline revision and date.
- Planned issues must be labeled `PLANNED` until implementation and evidence exist.
- Do not document direct container hotpatches, embedded IPs, OAuth application IDs or credentials as contributor workflow.
- Update README, Reader, Product Truth and agent knowledge together when the canonical architecture changes.

## Current clean-room boundaries

The Repository Intelligence & Evidence Lane is an independent implementation. Do not import proprietary plugin binaries, prompts, telemetry, embedded keys or vendor-specific runtimes.

Issue #1182 is a plan for Skill A/B benchmarks, mutation checkpoints and deterministic context-pack receipts. Those features are not active until separately implemented and verified.

## Completion rule

Before claiming completion, report:

- exact source and final revision;
- changed paths;
- relevant tests and checks actually run;
- GitHub check state at the exact head;
- artifact/image digest if applicable;
- deployment and target-system readbacks if applicable;
- blockers or unavailable evidence;
- whether the result is repository-only, CI-verified, deployed-unverified or runtime-verified.

If any required evidence is missing, state the exact blocker instead of claiming success.
