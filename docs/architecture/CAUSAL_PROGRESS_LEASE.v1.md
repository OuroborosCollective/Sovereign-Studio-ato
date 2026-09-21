# Sovereign Causal Progress Lease (SCPL) v1

## Purpose

SCPL separates **Agent Zero liveness** from **material repository progress**.

A2A `tasks/get` observations, heartbeats, frontend polling and chat activity never
renew a causal progress lease. Only bounded, independently observed repository
state transitions may do so.

## Ownership boundary

- **#1525 RemoteWorkerLease** owns WorkerHost/attempt liveness and capability leases.
- **Agent Zero A2A** owns remote task state.
- **Git workspace identity** owns repository HEAD/status/diff/untracked readback.
- **SCPL** owns only the derived question: has this already-valid repository
  execution produced a new material workspace state recently enough to continue?

SCPL does not claim quality, correctness, completion, CI success, deployment
success, or runtime health.

## Canonical evidence

`CausalProgressReceiptV1` is bound to:

- Sovereign job ID
- workspace ID
- Agent Zero task ID
- repository identity and observed repository revision
- progress kind
- predecessor workspace readback hash
- current authoritative workspace readback hash
- predecessor progress receipt hash
- observed epoch

Repeated workspace fingerprints are not credited again. This prevents a simple
A→B→A oscillation from earning an unbounded sequence of leases.

A retry or replacement Agent Zero task ID does not itself renew progress. The
next previously unseen authoritative Git workspace fingerprint may continue the
same predecessor chain under the new task ID. The `A2A_STATE_TRANSITION` kind
is reserved for an explicitly observed state transition and is not synthesized
from task-ID replacement.

The persisted predecessor chain is periodically read oldest-first and validated
as a whole. Invalid JSON, invalid hashes, missing predecessors, repeated credited
material fingerprints, or a bounded-chain overflow fail closed; historical rows
are never silently skipped.

## Lease semantics

`CausalProgressLeaseV1` returns one of:

- `CONTINUE_VERIFIED` — recent independently observed material state exists.
- `NO_PROGRESS` — no material progress has yet been observed.
- `STALLED` — no-progress window or absolute execution deadline is exhausted.
- `UNVERIFIED` — the required material readback is currently unavailable.
- `CONTRADICTED` — supplied progress evidence conflicts with the bound execution.

`UNVERIFIED` never renews a lease. While the last verified lease is still valid
the reconciler reports a transient evidence failure without resubmitting work. If
evidence remains unavailable through that lease boundary, continuation is
fail-closed and the existing remote-cancel/quarantine path is used without
claiming that repository stasis itself was observed.

An absolute deadline remains independent of material progress. Repeated changes
therefore cannot make a repository mission immortal.

## Runtime path

For an active Agent Zero repository task the server-owned reconciler:

1. reads the real A2A task state;
2. reads the shared Git workspace through the existing canonical Git identity
   primitive when available;
3. persists a new progress receipt only for a previously unseen workspace
   fingerprint;
4. evaluates the lease against the existing submitted/working no-progress policy
   and the independent absolute deadline;
5. uses the existing cancel/quarantine path when the lease is exhausted;
6. persists A2A observations separately without turning them into progress.

## Truth and consent

SCPL never widens authority. It only narrows continuation of an already
authorized execution. Existing owner permission, revocation, stop/cancel,
capability and effect boundaries remain authoritative.

The user-facing system must not present a progress receipt as a percentage,
completion estimate, quality score, or success verdict. A stop/revoke action
must remain immediately available and must not be defeated by a fresh progress
receipt.

## Positive evidence boundary

Unit tests may use synthetic hashes and fake A2A clients to exercise pure
contracts. A production claim of causal progress requires:

- the actual running backend revision/digest,
- a real Agent Zero task readback,
- a real shared workspace,
- a real Git workspace identity readback,
- persisted progress receipt readback,
- and the existing regression/evidence gates.

Mocks, stubs, UI activity and workflow status labels cannot produce that claim.
