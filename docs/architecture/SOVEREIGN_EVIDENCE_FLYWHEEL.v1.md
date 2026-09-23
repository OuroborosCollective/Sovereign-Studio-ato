# Sovereign Evidence Flywheel v1

## Status

`IMPLEMENTED_IN_REPOSITORY` when this document is present on a reviewed revision. It is a procedural contract, not a runtime truth authority.

## Why this exists

The supplied `skills-main.zip` contained useful evaluation and agent-operations patterns, but Sovereign already has canonical architecture, consent, registry, CI, runtime and readback surfaces. The integration therefore adopts the useful **method** without importing a second runtime or vendor-specific truth model.

## Canonical loop

```
freeze exact revision
→ establish real baseline
→ bounded execution
→ causal failure-family analysis
→ minimal canonical fix
→ same-case + neighbor regressions
→ independent target readback
→ one Memory entry
→ normal Draft-PR / Owner / merge gates
```

## Consent/effect binding

Sensitive or external effects must preserve the existing sequence:

```
Action Preview
→ Authority + scope resolution
→ explicit Owner/user approval when required
→ effect
→ Action Receipt
→ independent target readback
```

For asynchronous effects, stale approval must not survive a revocation or authority change. Consent authorizes; it does not prove execution.

## Evaluation rules

The evaluation layer must never obtain a green state by:

- lowering thresholds;
- skipping flaky/failing cases;
- moving expected outputs only to make the candidate pass;
- replacing independent evaluation with self-grading;
- confusing repository/CI success with runtime success.

Failure is first classified against the actual evidence source, then patched at the smallest canonical owner and turned into a regression.

## Existing Sovereign ownership

This method composes existing architecture and assurance tools. It must not introduce another registry, queue, approval store, evidence ledger, runtime, or deployment mechanism.

Archive reference SHA-256:

`dbfb60b5e0fbd84c2fbf16c1ae3d527cfb3782e7455d896a9e6749781e5c8787`.
