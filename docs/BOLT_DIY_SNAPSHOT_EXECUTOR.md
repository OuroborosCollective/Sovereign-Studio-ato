# Bolt.diy Snapshot Executor

## Purpose

Sovereign may use the self-hosted Bolt.diy surface as an **external development executor** when the environment works from a repository ZIP rather than a persistent local checkout.

Bolt is not a production authority. Sovereign remains the orchestration/evidence boundary and Aurion remains the owner of gameplay, simulation, persistence and world truth.

## Truth path

```text
GitHub repository
  -> exact 40-char source revision
  -> Sovereign creates/obtains ZIP bytes for that revision
  -> Bolt.diy imports the ZIP as an isolated development snapshot
  -> optional add-ons are probed, never assumed
  -> code / Blender / Python / game-dev work happens in that snapshot
  -> result bundle names the exact source revision
  -> Sovereign validates changed paths + evidence
  -> Draft PR
  -> required CI / regression / runtime readback
  -> merge only after the normal evidence gate
```

A ZIP built from the moving name `main` is not enough. The manifest must bind the snapshot to the exact Git commit that `main` resolved to when the job was created.

## Executor identity

Runtime identifier:

```text
bolt-diy-snapshot
```

Workspace host:

```text
remote-snapshot
```

The host name is intentionally different from a persistent workspace. Sovereign must not report a durable local workspace merely because Bolt imported an archive successfully.

## Capability discovery

The following capabilities are supported by the contract, but are **ready only after positive probe evidence**:

- Node
- terminal
- Python
- Blender headless
- Ninja
- generic game-development tools
- Git/diff tooling

Typical probes are exported by `buildBoltCapabilityProbePlan()`. A missing tool is an observed limitation, not a failure of the whole executor.

This is important for the current installation because online add-ons may provide Python, headless Blender and additional game-development utilities while the base Bolt surface itself remains primarily web/Node oriented.

## Authority boundary

A Bolt snapshot job always carries:

```json
{
  "production": false,
  "rawVps": false,
  "rawDatabase": false,
  "gameplayMutation": false,
  "githubDirectMerge": false
}
```

Therefore Bolt may produce development artifacts and evidence, but it may not:

- mutate Aurion's live world directly;
- use raw production SQL;
- receive unrestricted VPS authority;
- silently merge a branch;
- claim that a browser preview proves production runtime success.

## Evidence gate

A returned snapshot is accepted only when:

1. its schema is recognized;
2. its `sourceRevision` exactly equals the requested revision;
3. every changed file has a safe repository-relative path;
4. all evidence required by the job exists and reports success.

The default evidence set is:

```text
snapshot-provenance
diff
tests
```

Callers may additionally require `build` and `runtime-readback`.

A Bolt-side test result is development evidence. The normal Sovereign PR/CI/runtime gates still run afterward and remain authoritative for merge/release decisions.

## Why a thin adapter

Do not fork Bolt merely to make it look like Sovereign. The safe boundary is a small revision-pinned snapshot adapter:

```text
Sovereign -> snapshot contract -> Bolt.diy
                              -> Python / Blender / game-dev add-ons
Sovereign <- evidence contract <- returned bundle
```

This keeps upstream Bolt updates independent and preserves Sovereign's agent-neutral executor architecture.
