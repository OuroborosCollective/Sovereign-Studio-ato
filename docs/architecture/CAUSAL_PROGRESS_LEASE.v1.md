# Sovereign Causal Progress Lease v1

SCPL separates **A2A liveness** from **material repository progress**.

## Truth boundary

- `tasks/get = working` proves only remote-task liveness.
- UI polling, chat activity, heartbeats and repeated task observations never renew progress.
- Material repository progress comes only from the canonical real Git workspace readback owned by `agent_run_receipts.read_git_workspace_identity()`.
- Repeating a previously attested workspace readback (including A -> B -> A oscillation) never renews the lease.
- A clean first workspace readback is only a baseline. It does not reset the no-progress clock.
- A first readback that already contains real changed paths is a material `WORKSPACE_DELTA`.
- Completion, correctness and publication readiness remain owned by regression, Janitor, Evidence Gate and Draft-PR readbacks. SCPL never claims those states.

## Receipt chain

`CausalProgressReceiptV1` binds job, workspace, A2A task, repository/source revision, progress kind, previous workspace readback, current workspace readback, sequence and predecessor receipt hash.
Timestamps are deliberately outside the receipt hash; the PostgreSQL event row's `created_at` supplies the operational lease observation time.

## Lease

The no-progress window reuses `SOVEREIGN_REPOSITORY_STALL_SECONDS`.
An independent absolute cap is configured by `SOVEREIGN_REPOSITORY_ABSOLUTE_DEADLINE_SECONDS` (bounded by the runtime).
A material workspace delta may renew the no-progress window, but never the absolute deadline.

## Fleet ownership

Issue #1525 / `RemoteWorkerLease` remains the liveness/attempt lease owner. SCPL does not create a second worker heartbeat or worker authority. It only answers whether a valid repository execution has produced a new independently observed workspace state.

## Positive product evidence

Mocks and synthetic workspace snapshots may test pure contract logic, but they cannot substantiate a production SCPL claim. A production claim requires the exact backend revision/image identity, real Agent Zero `tasks/get`, real shared-workspace Git readbacks and the persisted PostgreSQL progress-receipt chain from the same execution.
