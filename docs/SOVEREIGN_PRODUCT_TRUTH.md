# Sovereign Product Truth

This document defines the non-negotiable product and evidence contract for Sovereign Studio ATO.

**Reconciled:** 2026-08-25
**Dated orientation:** [`CURRENT_STATE_2026-08-03.md`](CURRENT_STATE_2026-08-03.md)

## Prime directive

```text
Runtime creates truth.
UI displays bounded projections of that truth.
Evidence and target-system readback decide completion.
```

A proposed UI, runtime, agent, MCP, provider or deployment change that conflicts with this contract is wrong unless this document is deliberately revised with evidence and owner approval.

## Product rules

| Rule | Meaning |
| --- | --- |
| The monitor is the default surface. | The Live Workspace Monitor remains primary during execution, unavailable evidence and `waiting-for-user`; no legacy full-chat body replaces it. |
| Communication is embedded. | The LLM converses through a compact dock inside the monitor and proposes typed intent; the runtime does not keyword-interpret free language. |
| Inspection surfaces are explicit. | Repo, files, diff, workflow, runtime, telemetry, health, memory and inspector views are bounded monitor projections and do not create truth. |
| Every action produces a result. | No invisible or decorative work. |
| Every result creates or updates bound state. | State must identify owner/scope/revision where applicable. |
| State allows, blocks or approval-gates the next action. | No blind continuation loops. |
| Progress must be measured. | No hard percentages or fixed step counts without real runtime measurement. |
| Live paths are real. | No mocks, stubs, facades, fake snapshots or hardcoded green states. |
| Secrets never enter user-visible or tracked surfaces. | No credentials in chat, logs, docs, PRs, Issues, telemetry, tests or ledgers. |
| Repository state is not deployment state. | Code at `main` does not prove a running image or registry contains it. |
| Tool success is not target success. | Exit code, `ok: true`, model text or event completion is at most unverified execution evidence. |
| Draft PR is the default review boundary. | Agent-authored work is reviewed before merge. |
| Merge is owner-scoped and evidence-bound. | Exact head, mergeability, required checks and explicit owner approval are mandatory. |
| Deployment is immutable and revision-bound. | No direct running-container hotpatch as release method. |

## Truth classes

Sovereign must distinguish:

```text
PLANNED
IMPLEMENTED_IN_REPOSITORY
TESTED_AT_REVISION
CI_VERIFIED
ARTIFACT_VERIFIED
DEPLOYED_UNVERIFIED
RUNTIME_VERIFIED
BLOCKED
CONTRADICTED
```

These states must not be collapsed into one generic success badge.

## Route truth

```text
user input
→ model/structured intent candidate
→ runtime validation
→ capability and permission decision
→ read-only answer, repository operation, isolated workspace, MCP or operator route
→ execution receipt
→ independent target-system readback
→ stored state and UI projection
```

The model may understand language and propose structured actions. It cannot create permission, capability availability, repository state, passing tests, a PR, a deployment or runtime health.

## Capability truth

Sovereign is one assistant at the product surface but many bounded capabilities internally.

Examples include:

- chat and explanation;
- repository read/search/intelligence;
- hash-bound repository patching;
- isolated workspace execution and tests;
- GitHub Issue/PR/workflow operations;
- MCP and control-plane operations;
- provider routing;
- evidence, continuity and learning;
- immutable deployment and PatchMon readback.

No executor, including OpenHands or an internal agent runtime, is the universal mandatory path. The runtime selects only staged and permitted capabilities.

## GitHub and write truth

- Repository identity and access are resolved against the real target.
- A token-looking value is not proof of access.
- Read and write capabilities remain separate.
- Draft PR creation requires a real diff and guarded publication path.
- Plan-only output is not an actionable PR.
- Merge requires explicit owner approval for that exact PR head.
- A previous owner approval does not authorize a later mutation.

## Provider truth

- Paid routing is direct through OpenRouter.
- Free routing uses direct FreeLLM/Revolver surfaces.
- LiteLLM is historical/deactivated evidence and is not an active product transport or rollback path.
- Provider/model configuration in Git does not prove current selectability, price validity, credits or health.
- External numeric/null snapshots are normalized at the boundary and fail with structured errors when invalid.

## Repository Intelligence truth

Repository Intelligence is a discovery and controlled-editing side channel. It may provide:

- lexical/local projection search;
- Git-blob and content-hash identities;
- capability scopes;
- hash-bound replace/restore;
- schema and toolchain diagnostics;
- deployment/context drift observations.

It does not replace the tracked file, Git revision, permission receipts, CI, artifact or runtime evidence.

## Evidence truth

Evidence must be bound to the relevant identity:

- owner/tenant/organization;
- repository and workspace;
- run/workflow/step;
- source and target revision;
- tool/capability/schema/payload hashes;
- artifact or image digest;
- target-system readback source.

Telemetry and traces help observation but are not canonical receipts. Liveness proves only liveness.

## Neuro-inspired verification truth

Neuromorphic principles may optimize routing and evidence processing, but they
do not replace deterministic authority. The allowed MCP shape is hybrid:

```text
change/delta + temporal envelope
→ bounded relevance and sparse advisory routing
→ proposal-only candidate
→ deterministic Foundation verification
→ explicit admission receipt
→ separate approved effect path and target readback, when applicable
```

- The existing FastMCP instance, live registry and permission/effect contracts
  remain authoritative.
- Sparse routing selects a bounded candidate subset; it never grants
  permission or executes a tool.
- Unknown kinds, stale revision/policy identities, ambiguous provenance and
  partial cross-ledger state fail closed.
- Event, Foundation and teaching receipts are hash-bound evidence. They are not
  target-system effect proof.
- Mutating-tool outcome projections are a bounded best-effort side channel.
  Read-only tools do not write ranking or neuromorphic state. Tracking failure
  must not alter a primary tool result, and integrity status must come from the
  canonical ledger verifier.
- Repository implementation, CI, image construction, deployment and live
  plugin usability remain separate truth classes.

## Continuity truth

- Continuity context, policy and ledgers are advisory historical provenance only; they do not authorize, delay or block repository mutations, PRs, merges, releases, deployments or runtime work.
- Exact Git revision, explicit owner/permission gates, required CI/evidence and fresh target-system readback remain the technical authority.
- When written, ledgers are append-only.
- Historical records are not current runtime state.
- Owner-asserted personal provenance and technical evidence remain distinct.
- Raw chat and secrets are not persisted.

## Deployment truth

```text
reviewed exact head
→ exact-head CI
→ merge
→ resolve new main revision
→ immutable image and digest
→ controlled deploy/self-update
→ registry/protocol/container/revision/digest/PatchMon readback
```

A deployment or rollback is blocked when the expected revision/digest or prior rollback reference is absent or contradictory.

## Planned work

Issue #1182 describes planned Skill A/B benchmarks, per-mutation checkpoints and deterministic context-pack receipts. This document does not classify them as implemented.

## Drift prevention

Do not:

- create another main shell or parallel control plane;
- use UI text, telemetry or liveness as truth;
- make a single executor the only write path;
- reintroduce LiteLLM;
- install packages or copy files into running production containers as release practice;
- trust unknown plugins, skills or URL prefixes;
- expose secrets or secret-shaped fixtures;
- present old SHAs, image digests, ports or issue lists as current;
- claim CI green when checks are empty, stale or pending;
- claim runtime verification from repository code alone;
- rewrite append-only continuity records.

Breaking these rules should fail tests, contract gates, review or runtime policy.
