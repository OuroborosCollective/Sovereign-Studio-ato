# Sovereign Brain — Current State

schema: sovereign.brain-projection.v1  
truth_class: DERIVED_PROJECTION  
runtime_verified: false

## compiled_truth

The project brain does not carry a mutable "current runtime" snapshot. Current state must be reconstructed from the exact repository revision and the relevant target-system readbacks.

Use these truth classes instead of a generic green/done label:

- `PLANNED`
- `IMPLEMENTED_IN_REPOSITORY`
- `TESTED_AT_REVISION`
- `CI_VERIFIED`
- `ARTIFACT_VERIFIED`
- `DEPLOYED_UNVERIFIED`
- `RUNTIME_VERIFIED`
- `BLOCKED`
- `CONTRADICTED`

A dated current-state document is orientation only. Fresh Git, CI, registry, database, container, provider, artifact, deployment, MCP, and PatchMon evidence outrank stale prose.

For any task, resolve at least:

1. exact current repository/base/head revision;
2. changed paths and canonical ownership;
3. tests/checks actually executed on that head;
4. required artifact or image identity when applicable;
5. target-system runtime readback when the claim concerns live behavior.

This brain projection itself is always `DERIVED_PROJECTION`, even when all referenced systems are healthy.

## timeline

Use `docs/CURRENT_STATE_2026-08-03.md` as a dated orientation baseline and Git history/PRs for later repository changes. Use runtime/PatchMon evidence for live status. Never convert a historical snapshot into current truth merely because it remains tracked.
