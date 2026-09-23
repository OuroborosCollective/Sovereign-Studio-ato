---
name: sovereign-evidence-flywheel
description: Evidence-first evaluation and improvement loop for agent, tool, repository, CI, artifact, consent and runtime work. Use for changes that must be proven at the exact revision without lowering gates, hiding failures, or inventing runtime truth.
---

# Sovereign Evidence Flywheel

## Purpose

Turn agent/platform improvement into a repeatable loop that uses the existing Sovereign truth boundaries rather than creating a second evaluation or evidence system.

Canonical loop:

```
exact revision
→ baseline
→ bounded execution
→ failure-family analysis
→ minimal fix
→ regression + baseline comparison
→ independent target readback
→ receipt / Memory entry
```

The flywheel is a method. It is **not** a new truth source, registry, queue, runtime or approval authority.

## 1. Freeze the subject

Before changing anything:

- resolve the exact current revision;
- inspect related open PRs/issues and canonical/deployment mirror ownership;
- capture the relevant architecture snapshot and static drift candidates;
- define the expected effect class and required evidence;
- identify whether the change crosses an owner/permission boundary.

A branch or PR created from a stale base is not a valid baseline for current-main claims.

## 2. Establish a real baseline

Use the smallest relevant existing checks first, then the required aggregate gates.

Record:

- exact revision;
- exact test/check commands and terminal state;
- relevant runtime/artifact identity when already available;
- the known failure families and their provenance;
- no invented score, readiness flag or “green” interpretation.

Do not lower a threshold, remove a failing case, or call self-grading sufficient merely to make the baseline pass.

## 3. Execute only through bounded authority

Every mutation follows the existing Sovereign path:

```
action preview
→ authority / scope check
→ explicit approval when required
→ effect
→ action receipt
→ independent readback
```

The preview should identify, at minimum:

- action and effect class;
- mission / job identity;
- target repository/resource and exact revision;
- intended scope;
- payload/content hash where relevant;
- expected external effect;
- required evidence and rollback/stop condition.

Consent is an authorization boundary, not proof that the effect happened.

For asynchronous effects, revocation and authority must be checked again immediately before the effect if the path permits a stale authorization window.

## 4. Analyze failures causally

Classify the observed failure before patching.

Preferred sequence:

1. inspect the actual trace/log/readback;
2. identify the first violated invariant;
3. distinguish unavailable evidence from a negative result;
4. identify the owning surface;
5. patch the smallest canonical surface;
6. patch mirrors only where canonical/deployment parity requires them;
7. add a regression for the observed failure family.

Flakiness is evidence of an unresolved reliability problem. Do not hide it by skipping the case.

## 5. Compare before and after

After a fix:

- rerun the same baseline case;
- rerun relevant neighboring cases;
- run the appropriate skill regression and trigger-quality benchmarks;
- check tool idempotency for effects that can be repeated;
- compare the changed outcome with the baseline;
- look for regressions on unrelated metrics, permissions and evidence requirements.

A successful local test is only `TESTED_AT_REVISION`. It does not establish deployment or runtime truth.

## 6. Read back the real target

For deployment/runtime work, independently read back:

- source revision;
- immutable image/digest where applicable;
- container/runtime health;
- protocol/registry identity where applicable;
- PatchMon/fleet state;
- actual target effect;
- relevant database/vector state.

UI state, a model statement, an exit code, a workflow dispatch or a telemetry event alone cannot create `RUNTIME_VERIFIED`.

## 7. Close with provenance

Before merge:

- record exactly one concise Memory.md entry with change, learning and evidence;
- preserve the exact revision and check identities;
- verify mirror parity where applicable;
- retain open evidence gaps instead of converting them into success;
- keep the PR Draft until the repository's normal review/approval gate permits readiness.

After merge, resolve the new main revision again and repeat the applicable immutable/runtime readbacks.

## Required existing Sovereign surfaces

Use and extend existing canonical tools rather than introducing duplicates:

- `repository_architecture_snapshot`
- `repository_architecture_drift_report`
- `repository_architecture_runtime_drift_evidence`
- `backend_architecture_assess`
- `skill_capability_coverage_map`
- `skill_lifecycle_deprecation_preview`
- `skill_regression_benchmark`
- `skill_trigger_quality_benchmark`
- `tool_idempotency_verify`
- `owner_approval_policy_evaluate`
- `runtime_dependency_health_matrix`
- PatchMon / fleet readback tools
- exact GitHub CI and target-system readbacks

## Anti-shortcut invariants

Never:

- lower an evaluation threshold to hide a failure;
- skip a flaky case because it is inconvenient;
- replace an expected output with a moving target solely to pass;
- treat self-grading as independent verification;
- infer runtime success from repository source or CI alone;
- treat consent as evidence of execution;
- persist a synthetic snapshot as live runtime truth;
- introduce a second approval, registry or evidence authority;
- reintroduce Swarm or awareness-monitor execution paths;
- reintroduce LiteLLM routing.

## Archive provenance

This method incorporates selected, vendor-neutral patterns observed in the supplied `skills-main.zip`, especially the Agent Platform Eval Flywheel and its guidance against threshold-lowering, failure-skipping and self-grading. The archive is treated as reference material only; no vendor runtime, proprietary prompt, credential, telemetry or binary is imported.

Archive SHA-256: `dbfb60b5e0fbd84c2fbf16c1ae3d527cfb3782e7455d896a9e6749781e5c8787`.
