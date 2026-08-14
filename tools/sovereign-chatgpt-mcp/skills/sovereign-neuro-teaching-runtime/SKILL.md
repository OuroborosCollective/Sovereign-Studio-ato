# Sovereign Neuro Teaching Runtime

## Name

`sovereign-neuro-teaching-runtime`

## Purpose

Expose the canonical temporal event, sparse proposal, deterministic Foundation, evidence, and dry-run teaching lanes through the existing Sovereign FastMCP process. This skill does not create a second server, registry, router, code server, approval system, model route, or truth store.

## Core sequence

1. Read `neuro_runtime_contract_status`.
2. Resolve the exact source revision and current continuity policy.
3. Use `neuro_event_route_preview` for a bounded, secret-free candidate.
4. Stop on quarantine, registry drift, source-head drift, quota pressure, or an unaccepted Foundation decision.
5. Use `neuro_event_commit` only with the exact preview hash and source-head compare-and-swap values.
6. Treat the commit as proposal/evidence persistence, never as effect authorization.
7. Execute any selected tool separately through its own live contract, operating-profile gate, owner policy, and target readback.
8. Read outcome and integrity evidence again.

For teaching packages, first call `teaching_package_assess` with a repository-local path and exact SHA-256. Call `teaching_lesson_simulate` only with the successful receipt from the current live-registry snapshot.

## Hard boundaries

- Candidate and spike output is uncertain and `proposalOnly`.
- Foundation decisions always have `mayExecute=false` and no external effects.
- Unknown event and Foundation kinds fail closed.
- Time, sequence, predecessor, revision, policy, payload, registry, and receipt hashes are explicit data.
- Tool catalogs from supplied archives are never treated as live capability truth.
- Teaching simulation does not invoke tools, write packages, persist feedback, train a model, or promote rules.
- Known secret literals, unresolved provenance, and unknown/forbidden licensing are rejected.
- Persistent tool-outcome tracking is limited to mutating tools, bounded and fail-soft; read-only calls remain state-free and tracking cannot change the primary tool result.
- Arelorian Wasd code, state, truth, and provider routes are outside this skill.

## Verification

The immutable image must contain the canonical contract mirror, `neuromorphic_runtime.py`, `foundation_runtime.py`, `neuro_teaching_tools.py`, and this manifest. CI must compile/import the modules, verify all five registered tool names and typed output schemas, and run replay, concurrency, tamper, quota, and negative-path tests. The installer must verify the exact live tool surface and run isolated status, quarantine, real-registry routing, commit/replay, tamper, and protocol canaries without executing a selected tool. Production activation additionally requires exact revision, digest, container, MCP protocol, registry, and PatchMon readback.
