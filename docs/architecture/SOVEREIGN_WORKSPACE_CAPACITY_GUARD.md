# Sovereign VPS workspace admission: ENOSPC guard (non-destructive)

## Incident reason and live measurements

On 2026-10-24 the private Sovereign host capacity tool measured the same
underlying \`/\`, \`/opt\`, and Docker filesystem at **91.52% used**:
380,790,353,920 / 416,055,988,224 bytes used, **35,265,634,304 bytes
available**. This is a P0 capacity condition. Attribution to clone workspaces
is not yet proven; **do not** claim the directories explain the used capacity.

The existing implementation created a new workspace for each Agent Job and
performed \`git clone --depth 1\` inside it, while workspace cleanup was
owner-invoked after a terminal state. Stuck \`running\` and \`verifying\`
tasks could therefore retain historical workspaces. No automatic garbage
collection or per-job filesystem quota is proven.

## Implemented guard (source only until promoted)

- Every new workspace checks a shared file lock, direct-child workspace count
  (max **12**), and **at least 20% free filesystem space**, never less than
  **4 GiB**, before creating a directory. The threshold is on the filesystem
  hosting the actual workspace mount, not a UI estimate.
- Every clone takes the **same** cross-process non-blocking flock and
  re-checks free space while holding it through the Git clone.
- The repository job route rejects admission **before GitHub queries or DB
  job creation** when the filesystem is full, locked or workspace-count capped.
  The actual provisioner and clone recheck independently: no TOCTOU based on
  an earlier optimistic API response.
- Invalid lock files, symlinks and unavailable disk accounting fail closed.
  Cleanup rejects a workspace symlink pointing at another job.
- No code automatically removes an existing job, repository clone, Docker
  volume, release artifact, database, evidence, backup or open worktree.

**Limits:** This is admission control, not a strict per-job disk quota. A
single admitted test process or another workload can still grow unexpectedly.
Do not enable OpenShell agents until backed by a separately limited host
mount (e.g. project quota or size-limited sandbox writable layer), max
per-job runtime, cooperative cancellation and verified cleanup/retention.

## Required live rollout gates

1. CI tests on exact branch HEAD (budget, parallel contention, root symlinks,
   read-only probe, canonical/deploy mirrors, unrelated runtime regressions).
2. Read exact running image, workspace mount, filesystem capacity and current
   workspaces without reading secrets; verify whether outstanding clones,
   Docker layers, backup sets or database volumes dominate disk usage.
3. Do **not** trigger an image build/deploy on the 91.5%-full VPS without
   a separately validated free-space margin/rollback plan.
4. When approved, release with exact SHA and verify **one rejected
   non-mutating canary** while disk pressure is present, including absence
   of job record and clone path; then normal admission on isolated host.
5. Implement later a two-phase GC: dry-run exact job/lease/repository readback,
   pre-retain patch/test/evidence, settle claim and closeout, minimum 24h grace,
   owner-gated deletion of only a named and identified terminal workspace,
   independent directory-absent and filesystem readback. No \`rm -rf\`,
   Docker prune or global cleanup.

**Before deployment:** Keep new Agent Job submission paused while disk
pressure remains. Success in code/CI is not runtime proof.
