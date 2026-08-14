# Bounded Predictive Self-Healing (Backend Contract)

Status: `PLANNED` (this document) Ã¢ implementation `IMPLEMENTED_IN_REPOSITORY` for the
Action Policy + Causal Readback contract described here.

Baseline revision: `main` @ `027f742` (2026-08-14).
Related issue: #1173 (Bounded Self-Healing: predictive action policy, safe reflexes,
swarm repair, causal readback).

## Scope of this change

This documents the **backend contract** layer for bounded predictive self-healing.
It is a pure data/evidence contract: it binds, validates and fail-closes. It does
**not** execute actions, does not touch the network, database, filesystem or any
runtime. Execution projection remains the responsibility of the TypeScript runtime
(`src/features/product/runtime/sovereignPredictiveActionRuntime.ts` and
`sovereignPredictiveRuntimePolicy.ts`).

Canonical ownership: `backend/agent_runtime/predictive/`. Deployment mirror:
`scripts/sovereign-backend/agent_runtime/predictive/`. The two must remain
byte-equivalent; `test_live_and_deploy_predictive_subdir_remain_exact_mirrors`
enforces this.

## Action levels

Higher levels never derive from lower capability classes.

| Level | Name | Capability class (minimum) | Boundary |
|------:|------|----------------------------|----------|
| 0 | Observe | `read_only` | no runtime mutation, projection only |
| 1 | Safe Reflex | `bounded_reversible` | reversible, pre-defined, bounded |
| 2 | Bounded Recovery | `bounded_stateless` | stateless replica restart / isolate / stop |
| 3 | Swarm Repair | `draft_pr` | isolated workspace, ends at most in a Draft PR |
| 4 | Owner-bound | `owner_bound` | never derived from a lower capability |

Level 4 actions are restricted to explicit owner-bound categories (`db_migration`,
`permanent_data_change`, `secret_credential`, `permission_change`, `github_ruleset`,
`branch_protection`, `merge`, `irreversible_delete`, `new_production_target`,
`new_egress_capability`, `truth_boundary_change`). A Level 4 plan whose action_id
prefix is not one of these categories is rejected at construction.

## Predictive Action Plan binding

An `ActionPlan` is the bound candidate produced by the Predictive Lane. A plan is
admissible only when all of the following hold at evaluation time:

1. **TTL** Ã¢ plan age (`now_s - created_at_s`) is within `[0, ttl_s]`. Negative age
   (plan created in the future) is also rejected as expired.
2. **Attempt budget** Ã¢ `attempts_used < max_attempts`.
3. **Idempotency** Ã¢ `idempotency_key` has not already been executed within the
   window (`idempotency_seen[key] < 1`).
4. **Revision binding** Ã¢ `source_revision`, `runtime_revision` (and, when
   present, `model_revision`, `index_revision`, `image_digest`) match the live
   target. Any drift rejects as `STALE_REVISION`.
5. **Config binding** Ã¢ `config_fingerprint` matches the live target.
6. **Capability derivation** Ã¢ the granted capability class can satisfy the
   level's minimum. Level 4 requires `OWNER_BOUND` exactly
   (`OWNER_BOUND_FROM_LOWER` otherwise).
7. **Payload integrity** Ã¢ `payload_hash` equals the deterministic SHA-256 of the
   normalized (sorted-key, compact-JSON) parameters.
8. **Pre-conditions** Ã¢ every declared precondition name is present and `True` in
   the live context's `precondition_results`. Missing or `False` is fail-closed.

The first failing check wins; the verdict is `REJECT` with exactly one explicit
`RejectReason`. Order matters: expiry and staleness are checked before capability
so a stale plan is never admitted by a coincidentally-high capability.

### Deterministic payload hash

`normalize_parameters` serializes parameters with `sort_keys=True` and
`separators=(",", ":")`, `ensure_ascii=False`, then SHA-256s the UTF-8 bytes.
This is stable across processes and runs. Non-JSON-serializable values raise, so
secrets or objects never silently corrupt the binding.

## Causal Readback verdicts

An execution that "succeeded" is not causal proof. The readback classifies the
effect from two independent real evidence windows (pre-action, post-action):

| Verdict | Meaning |
|---------|---------|
| `EFFECT_VERIFIED` | every declared expected metric moved in the expected direction |
| `EFFECT_NOT_OBSERVED` | metrics did not move as expected (neither matched nor contradicted) |
| `EFFECT_CONTRADICTED` | at least one expected metric moved opposite to expected |
| `TARGET_CHANGED_EXTERNALLY` | post-action target binding drifted from the plan (or pre baseline missing) Ã¢ effect not attributable |
| `INSUFFICIENT_POST_WINDOW` | post window captured before `created_at_s + max_effect_duration_s` |
| `ROLLBACK_REQUIRED` | unexpected negative side effects observed and the plan declared a rollback plan |

Expected metrics map a metric key to a direction token in `{"up", "down", "flat"}`.
An improvement after the action is NOT automatically causal.

## What this is NOT

- Not a second execution runtime. The TypeScript runtime owns execution
  projection; this module owns the bound contract and verdict only.
- Not a network/DB/filesystem component. It is stdlib-only and pure.
- Not a truth source for runtime state. Plan status is a projection; only real
  readback against the target system can produce `EFFECT_VERIFIED`.
- No secrets. Fixtures are synthetic contract-shaped data.

## Validation

`backend/tests/test_predictive_action_policy.py` (29 tests) exercises the real
modules: construction/binding validation, all fail-closed rejection reasons,
capability derivation semantics, and all six causal verdicts. Mirror parity is
enforced by `test_live_and_deploy_predictive_subdir_remain_exact_mirrors`.
