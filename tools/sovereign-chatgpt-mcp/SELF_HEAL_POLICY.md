# Policy-guarded internal repair engine

The Sovereign operator contains a deterministic repair engine in `self_heal.py`.
It is not a free-form autonomous shell agent. It classifies bounded runtime evidence, selects one registered failure family and returns only the repair workflow allowed by that family.

## Invariants

Every repair family defines:

- exact evidence signatures;
- whether automatic repair is allowed;
- the permitted mutation scope;
- whether current confirmation is required;
- mandatory post-repair checks;
- capabilities that remain blocked.

The following capabilities are always blocked by the repair engine:

- generic shell execution;
- generic SQL execution;
- direct writes to `main`;
- automatic merge;
- secret readout.

Unknown failure signatures fail closed. They may only lead to bounded evidence collection, an isolated workspace, targeted tests and a Draft PR.

## Automatic repair boundary

The first automatically repairable family is:

`migration_preview_transaction_wrapper`

It may remove exactly one outer SQL transaction wrapper for the rollback-only preview copy. It never changes the repository migration, its confirmed SHA-256 or the SQL sent to the confirmed production application.

Before detecting transaction controls, the engine masks SQL comments, quoted strings, quoted identifiers and PostgreSQL dollar-quoted bodies while preserving offsets. Therefore valid PL/pgSQL such as:

```sql
DO $$
BEGIN
    -- procedural body
END $$;
```

is not confused with a second top-level database transaction.

A real additional top-level `BEGIN`, `COMMIT` or `ROLLBACK` remains blocked.

Every automatic preview normalization reports:

- failure family;
- repair status;
- scope `preview_only`;
- attempt count and maximum attempts;
- source and normalized preview hashes;
- `source_unchanged=true`;
- `production_write_performed=false`;
- required rollback and hash checks.

## Recognized non-automatic families

The engine also recognizes:

- workspace ownership/path failures;
- repository clone and missing-file contract failures;
- `ToolEvent`/`SovereignAgentEvent` mapping failures;
- missing immutable backend images;
- stale backend revisions;
- PostgreSQL authentication failures;
- missing vector schema.

These families do not receive unrestricted automatic repair. They are routed to the existing guarded mechanisms: installer canaries, isolated workspace and Draft PR, exact-image verification, hash-confirmed migration preview/application or explicit deployment confirmation.

## MCP tool

`runtime_failure_diagnose(evidence)` accepts at most 32,000 evidence bytes, returns an evidence SHA-256 instead of echoing the supplied logs and exposes only the registered policy result.

## Attempt limit

Automatic repair is bounded to two attempts per operation. A failed post-check must stop the operation and return the exact blocker. The engine never converts a failed runtime state into UI success.
