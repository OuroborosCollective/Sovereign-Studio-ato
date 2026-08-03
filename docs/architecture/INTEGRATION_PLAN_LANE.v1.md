# Integration Plan Lane — Issue #1112

**Documentation version:** v1
**Implementation baseline:** the canonical `backend/agent_runtime/integration_plan_lane.py`
and `backend/agent_runtime/integration_plan_store.py` plus the byte-equivalent
deployment mirror under `scripts/sovereign-backend/agent_runtime/`.
**Authority rule:** the current Git revision and fresh target-system readback
override this dated document.

## Purpose

A thin, revision-bound Integration Plan Lane for long and multi-phase
Sovereign-Studio-ATO assignments. The lane keeps the work state visible
across context loss, compression and session change **without ever
becoming a truth source** for repository, CI, artifact, image, deployment,
database or runtime state.

It extends the canonical continuity layer
(`docs/sovereign-continuity/CONTEXT.md`,
`tools/sovereign-chatgpt-mcp/continuity.py`) and the Bug Evidence Lane
(`backend/agent_runtime/bug_evidence_lane.py`) and never replaces them.

## Non-negotiable boundaries

1. The lane is a **projection**, not a truth source. Plan status does
   not prove repository, CI, artifact, image, deployment, database or
   runtime success. Only fresh target-system readback does.
2. **Phase status is never set by Markdown alone.** It is computed from
   machine-checkable `EvidenceRecord` entries whose `kind` matches the
   phase's declared `required_evidence_kinds`.
3. The lane never claims success on its own authority. Markdown, LLM
   output, hook injection or UI render cannot promote a phase to
   `verified`.
4. Plan content and evidence are **append-only**. A new attestation
   always binds the previous attestation hash and carries a non-empty,
   redacted `amendmentReason`.
5. The lane is bounded to one integration assignment. Cross-plan,
   cross-workspace or cross-repository reads are denied.
6. The lane is repository-only by default. Runtime completion requires
   matching revision, image, deployment, PatchMon and live readback.

## Target layout

For each integration the store creates:

```text
.planning/<integration-id>/
├── task_plan.md              # human-readable goal, scope, phases, next step
├── findings.md               # untrusted / observed / verified / invalidated
├── progress.md               # real tool and test events
├── evidence-index.json       # append-only machine-checkable evidence
├── plan.receipt.json         # schema-versioned, attestation-bound receipt
├── ledger-actions.jsonl      # append-only action and phase journal
├── .mode                     # open | gated | closed
├── .attestation              # SHA-256 of the active plan content
└── .active_revision          # expected repository / workspace SHA
```

The store writes only the schema-versioned and machine-checkable files
(`plan.receipt.json`, `evidence-index.json`, `ledger-actions.jsonl`,
`.mode`, `.attestation`, `.active_revision`). The three markdown files
remain human-readable and are not interpreted by the lane.

## Canonical modules

| Path | Role |
| --- | --- |
| `backend/agent_runtime/integration_plan_lane.py` | Pure state machine: `PlanReceipt`, `Phase`, `EvidenceRecord`, `PhaseStatus`, `IntegrationPlanLane.evaluate_phase`, `amend_receipt`, `verify_receipt_attestation`. No I/O. |
| `backend/agent_runtime/integration_plan_store.py` | Path-safe filesystem adapter: `IntegrationPlanStore`, `init_plan`, `write_receipt`, `append_evidence`, `append_ledger_action`, `write_active_revision`, `write_mode`, `write_attestation`, `write_text`. |
| `backend/agent_runtime/integration_plan_helpers.py` | Bounded helpers: canonical `task_plan.md` / `findings.md` / `progress.md` renderers, size-bounded redacted `render_context_injection`, `evaluate_gated_completion` (block ceiling + progress check + recursion guard), `snapshot_plan_lane_surfaces` (architecture snapshot + drift report), `resume_session` (Plan / Ledger / Git-Diff / Workspace- / Remote-Revision readback). |
| `backend/agent_runtime/integration_plan_inventory.py` | CLI inventory runner (stdlib only, no mutation). Executes implementation step 1 and produces `docs/architecture/INTEGRATION_PLAN_LANE_INVENTORY.json` + a drift report. Truth-class annotations per surface (`canonical-truth` / `mirror` / `projection` / `documentation`). |
| `backend/tests/test_integration_plan_lane.py` | Live-path tests for the state machine: schema, attestation, append-only, evidence evaluator, secret redaction, no-I/O structural check. |
| `backend/tests/test_integration_plan_store.py` | Live-path tests for the store: path traversal, absolute paths, Windows drive letters, MSYS, NUL bytes, symlinked ancestors, symlinked plan dirs, cross-workspace isolation, attestation round-trip, text writers. |
| `backend/tests/test_integration_plan_helpers.py` | Live-path tests for the helpers: canonical Markdown templates, context-injection size + redaction, gated completion evaluator (block ceiling + progress check + recursion guard), architecture snapshot drift detection, resume drift detection. |
| `backend/tests/test_integration_plan_inventory.py` | Live-path tests for the inventory runner: surface catalogue, truth class coverage, mirror paths, drift reporting, CLI entry point, strict mode exit code. |
| `scripts/sovereign-backend/agent_runtime/integration_plan_lane.py` | Byte-equivalent mirror of the canonical lane. |
| `scripts/sovereign-backend/agent_runtime/integration_plan_store.py` | Byte-equivalent mirror of the canonical store. |
| `scripts/sovereign-backend/agent_runtime/integration_plan_helpers.py` | Byte-equivalent mirror of the canonical helpers. |
| `scripts/sovereign-backend/agent_runtime/integration_plan_inventory.py` | Byte-equivalent mirror of the canonical inventory runner. |
| `scripts/sovereign-backend/tests/test_integration_plan_lane.py` | Byte-equivalent mirror of the lane tests. |
| `scripts/sovereign-backend/tests/test_integration_plan_store.py` | Byte-equivalent mirror of the store tests. |
| `scripts/sovereign-backend/tests/test_integration_plan_helpers.py` | Byte-equivalent mirror of the helpers tests. |
| `scripts/sovereign-backend/tests/test_integration_plan_inventory.py` | Byte-equivalent mirror of the inventory tests. |

Mirror parity is enforced by `diff` in the CI workflow and is a hard
invariant of the agent-runtime ownership contract.

## Schema versions

| Schema | Version |
| --- | --- |
| Plan receipt | `sovereign.integration-plan-lane.v1` |
| Evidence record | `sovereign.integration-plan-evidence.v1` |

Both versions are pinned inside the lane module and any future bump must
be paired with a `policyVersion` bump in the continuity policy and a new
append-only ledger entry.

## Evidence kinds

The lane recognises these machine-checkable evidence kinds:

| Kind | Source identity | Purpose |
| --- | --- | --- |
| `repo_revision` | 40-hex SHA | Git SHA of canonical main or PR head. |
| `ci_workflow` | workflow file or run id | CI workflow identity. |
| `artifact_digest` | `sha256:<64-hex>` | immutable image or artifact digest. |
| `deployment` | container/service name | deployment identity. |
| `postgres_readback` | host FQDN | Postgres migration head evidence. |
| `patchmon_readback` | host FQDN | PatchMon fleet/lane identifier. |
| `runtime_readback` | host FQDN | runtime health response. |
| `container_readback` | container/service name | container readback. |
| `pr_head` | 40-hex SHA | Pull request exact head SHA. |
| `ledger_head` | identifier | continuity ledger entry id. |

Each kind has a strict source regex; an `EvidenceRecord` whose `source`
does not match the binding for its `kind` is rejected at construction.

## Status flow

```text
pending
    │ (lane moves phase to in_progress)
    ▼
in_progress
    │ (all required evidence kinds present + verified)
    ▼
verified
    │ (or) → blocked       (missing or contradictory evidence)
    │ (or) → invalidated   (ledger_head invalidation record present)
```

`verified` cannot be reached through Markdown, LLM or hook injection. The
`IntegrationPlanLane.evaluate_phase` method is the single source of phase
status and is exercised directly by the unit tests.

## Path safety contract

The store rejects:

- absolute paths (`/`, Windows drive letters, MSYS mangling);
- `..` traversal segments anywhere in the path;
- NUL bytes in any path component;
- symlinks at any level of the workspace root ancestors;
- symlinks inside the plan directory (re-checked on every read);
- plan ids that do not match `^[a-z][a-z0-9_.:-]{1,119}$`;
- receipts whose `attestation_sha256` does not match the recomputed hash;
- evidence whose `kind` is not in the known set or whose `source` does
  not match the kind binding;
- evidence records whose `is_verified` is `True` while `redacted` is
  `False`;
- secret-shaped material (bearer tokens, GitHub tokens, AWS keys, PEM
  blocks, password `k=v` pairs, JWTs, Postgres DSNs with credentials).

These rules are covered by `backend/tests/test_integration_plan_store.py`.

## Continuity interaction

The lane is **adjacent to** the canonical continuity layer, not a
replacement. Before mutating an integration plan, agents must still read:

- `docs/sovereign-continuity/CONTEXT.md`
- `tools/sovereign-chatgpt-mcp/config/sovereign-continuity-policy.json`
- `docs/sovereign-continuity/LEDGER.jsonl`

Before Draft PR, direct main push or merge, the canonical append-only
continuity ledger must receive a new, redacted handoff entry that lists
the lane-related changed paths (`backend/agent_runtime/integration_plan_*.py`,
`backend/tests/test_integration_plan_*.py`, mirror copies).

## Completion rule

The lane is **not** a runtime-truth surface. A phase is `verified` only
when real, machine-checkable evidence has been recorded for every
required kind. A full integration is closed only when:

- every phase in the active receipt is `verified` or explicitly
  `invalidated`;
- the canonical continuity ledger has a new append-only entry
  referencing this integration;
- the repository-side readback (PR head, CI green, exact merge
  revision) matches the `.active_revision` recorded in the lane;
- for runtime assignments: image digest, deployment identity,
  container readback, Postgres readback, PatchMon readback and a real
  public or private health probe all agree.

Plan, progress, LLM or UI text alone may never produce a green
completion state.

## Tests

The lane, store, helpers and inventory runner ship with **122 live-path
unit tests** that import and exercise the real implementation. They cover:

- schema and identifier boundaries;
- attestation hash recomputation and tamper detection;
- amendment binding to the predecessor attestation hash;
- evidence kind bindings and source regexes;
- evidence evaluator rules (untrusted, observed, verified, invalidated);
- phase status flow for `pending`, `in_progress`, `blocked`, `verified`,
  `invalidated`;
- secret redaction at every entry point;
- path traversal, Windows drive letters, MSYS, NUL bytes, symlinked
  ancestors, symlinks inside the plan directory;
- cross-workspace and cross-plan isolation;
- append-only semantics for `evidence-index.json` and
  `ledger-actions.jsonl`;
- structural check that the lane module has no `open`, `socket`,
  `requests`, `time`, `datetime` or `psycopg2` imports.

Tests are mirrored byte-equivalently under `scripts/sovereign-backend/`
to satisfy the agent-runtime ownership contract.