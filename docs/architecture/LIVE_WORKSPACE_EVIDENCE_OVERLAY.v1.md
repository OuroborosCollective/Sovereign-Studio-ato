# Live Workspace Evidence Overlay v1

Issue: #1621
Status: repository implementation; runtime claims require separate PatchMon/target readback

## Boundary

The monitor is an observation surface. A frame, terminal text, browser page, UI label, model message, telemetry event, or liveness signal cannot create `VERIFIED`.

```text
canonical action/readback
→ canonical receipt in the existing Agent event/receipt store
→ immutable WorkspaceEvidenceAnchorV1 reference
→ current Attempt/revision reconciliation
→ small Evidence Rail + bounded Inspector
```

The anchor is a projection and has `authoritative: false`. It does not own the referenced receipt and cannot authorize, resume, deploy, merge, or change workflow state.

## Contract

`sovereign.workspace-evidence-anchor.v1` binds one granular claim to:

- current session, run, task, Attempt, and action;
- exact repository revision and optional target revision;
- one canonical source class and one or more SHA-256 source references;
- optional immutable image digest and runtime identity;
- optional frame observation correlation;
- observed time and immutable evidence hash.

Allowed verdicts are `OBSERVED`, `UNVERIFIED`, `VERIFIED`, `BLOCKED`, `CONTRADICTED`, and `STALE`. Generic claims such as `READY`, `DONE`, `GREEN`, or `EVERYTHING_WORKS` are rejected.

## Existing truth owners

No parallel evidence database is introduced. Anchors are stored in the existing PostgreSQL `sovereign_agent_events` table under the bounded `live_workspace_evidence_anchor` stage. Agent Run receipts, GitHub readbacks, PatchMon readbacks, database readbacks, and target readbacks remain their own canonical sources.

The exact Fleet Attempt repository-tool path emits an anchor only after the canonical Agent Run receipt has been persisted. Generic outer-clone tools cannot produce Attempt-labelled anchors.

## Freshness and isolation

- An anchor from another session or Attempt is historical and never appears on the current monitor rail.
- Repository head change makes an old repository/test anchor `STALE` for the current view while preserving its historical source verdict.
- Target revision, image digest, or runtime identity mismatch is `CONTRADICTED`.
- A runtime claim that requires PatchMon but lacks a fresh PatchMon identity tuple is `UNVERIFIED`; cached green is forbidden.
- Contradiction wins over staleness or apparent UI success.

## Frame correlation

A frame may supply `frameObservationId` and a frame-byte hash. `FRAME_OBSERVATION` can only produce `OBSERVED` or `UNVERIFIED`. A screenshot showing `PASS`, a PR page, a healthy label, or a deployed UI never upgrades a claim.

Persistent screen recording is not required and is not a truth store. The inspector contains bounded claim/source metadata only and excludes prompts, chain-of-thought, raw provider fields, and secrets.

## Continuity

Continuity may observe or log the lane separately. It is not read by the Evidence Overlay workflow, does not create anchors, and cannot require, mutate, or block GitHub workflows, merges, releases, deployments, or runtime actions.
