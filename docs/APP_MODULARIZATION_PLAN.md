# App Modularization Plan

`src/App.tsx` is now large and should be split into focused containers.

## Target containers

1. `RemoteMemoryContainer`
   - Owns remote memory config state.
   - Owns health, monitoring, preview, sync, search and pull/intake handlers.
   - Passes view props into `RemoteMemoryPanel`.

2. `BuilderContainer`
   - Owns mission text, package building, generated-file review and preview.
   - Receives Aha Memory hints as plain context.

3. `WorkflowContainer`
   - Owns workflow watch and repair-plan orchestration.

4. `RepoSnapshotContainer`
   - Owns repo URL, branch and snapshot load/restore/clear.

5. `TelemetryContainer`
   - Owns display-only telemetry panel state.

## Rules

- Remote Memory containers must preserve contributor scoping.
- Shared pattern updates must remain separate from contributor submissions.
- Container actions should keep sequential runtime guards when they cross workflows.
- New containers need runtime tests when they add non-trivial logic.

## First extraction target

`RemoteMemoryContainer` should be extracted first because it has the most isolated runtime boundary and the clearest product surface.

Required inputs:

- `scanRegistry`
- `solutionPatternStore`
- `setSolutionPatternStore`
- `pushTelemetry`

Required output:

- rendered `RemoteMemoryPanel`

## Patch strategy

Do not rewrite the whole App in one change. Use focused codemods or small file moves so runtime gates remain readable and reviewable.
