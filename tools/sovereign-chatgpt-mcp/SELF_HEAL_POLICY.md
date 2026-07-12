# Policy-guarded repair and private broker admin mode

The private ChatGPT MCP operator contains a deterministic repair engine in `self_heal.py` and privileged host actions in `admin_mode.py`.
The OpenAI secure tunnel remains transport only. Database administration and Git writes run through the local root-separated host broker.

## Always blocked

The broker still does not expose:

- a generic operating-system shell;
- secret or environment-file readout;
- automatic PR merge;
- uncontrolled Docker commands.

## Private administrator capabilities

These capabilities are available when their VPS switches are set to `1`:

```dotenv
SOVEREIGN_MCP_ENABLE_ADMIN_SQL=1
SOVEREIGN_MCP_ENABLE_MAIN_PUSH=1
```

`postgres_admin_sql` executes complete PostgreSQL SQL through the existing backend administrator identity. It accepts DDL, DML, transactions, functions, extensions and multi-statement SQL. psql meta commands such as `\!` are not SQL and remain unavailable because they would create an operating-system shell escape.

`repository_push_main` stages and commits the current isolated workspace and pushes its `HEAD` directly to `refs/heads/main`. Draft PR remains available but is no longer mandatory when the private main-push switch is active. A repository branch-protection rule may still reject the Git push at GitHub itself.

The active capability state is included in `runtime_failure_diagnose`.

## Repair families

Every repair family defines:

- exact evidence signatures;
- whether automatic repair is allowed;
- the permitted mutation scope;
- mandatory post-repair checks;
- a maximum of two automatic attempts.

Unknown signatures remain reported as unknown; they do not become success automatically.

## Transaction wrapper repair

`migration_preview_transaction_wrapper` removes exactly one outer SQL transaction wrapper for rollback previews. It does not change the repository migration or its confirmed SHA-256.

Comments, strings, quoted identifiers and PostgreSQL dollar-quoted PL/pgSQL bodies are masked before top-level transaction detection. Therefore:

```sql
DO $$
BEGIN
    -- procedural body
END $$;
```

is not confused with a second database transaction. A real additional top-level `BEGIN`, `COMMIT` or `ROLLBACK` remains rejected.

## Migration ledger schema repair

`schema_migrations_layout_drift` handles the two migration-ledger layouts that currently exist in the project:

```text
legacy: version, applied_at
current: id, name, applied_at
```

When a confirmed production migration fails specifically because its ledger insert expects the other layout, the broker:

1. keeps the repository SQL and confirmed source hash unchanged;
2. reads the real production ledger columns;
3. changes only the runtime migration-record insert;
4. executes the adapted migration against the real production structure inside `BEGIN ... ROLLBACK`;
5. applies it only when that preview succeeds;
6. returns `APPLIED_AFTER_REPAIR` and repair evidence.

This allows migration 008 and older `version`-based migrations to coexist while the database architecture is being consolidated.

## Other diagnosed families

The engine also recognizes workspace, clone, event mapping, missing image, stale backend, PostgreSQL authentication and missing vector-schema failures. Their repair paths use the available MCP and broker capabilities rather than converting a failure into a UI-only success.

## Evidence

`runtime_failure_diagnose(evidence)` accepts at most 32,000 evidence bytes and returns an evidence SHA-256 instead of echoing the supplied logs. Migration repairs report source and runtime SQL hashes, detected ledger columns, attempt count and rollback-preview evidence.
