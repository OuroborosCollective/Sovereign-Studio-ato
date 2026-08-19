---
name: sovereign-evidence-verdict
description: Decide the strongest truthful completion state for Sovereign work by checking exact-revision evidence, independent readback and contradictions without upgrading weaker evidence into runtime truth.
---

# Sovereign Evidence Verdict

Use this skill before a substantial mission is reported complete.

Read the repository truth classes from `AGENTS.md` and `docs/SOVEREIGN_PRODUCT_TRUTH.md`. Evaluate each requested claim independently and bind its evidence to the exact relevant revision and target identity.

A claim may advance only when its required evidence exists. Keep repository, tests, CI, artifact, deployment and runtime as separate layers. Do not upgrade a weaker layer merely because it is green.

Reject evidence laundering from model output, generated prose, UI text, telemetry, liveness, mocks, stubs, fixtures, stale workflow runs or another agent's unsupported assertion. If authoritative observations disagree, classify that scope as `CONTRADICTED` until resolved.

Prefer the repository's explicit states: `PLANNED`, `IMPLEMENTED_IN_REPOSITORY`, `TESTED_AT_REVISION`, `CI_VERIFIED`, `ARTIFACT_VERIFIED`, `DEPLOYED_UNVERIFIED`, `RUNTIME_VERIFIED`, `BLOCKED`, and `CONTRADICTED`.

Return a claim-by-claim verdict, supporting evidence, missing evidence, contradictions and the exact next evidence-producing action. The absence of a required source is an evidence gap, not permission to invent one.