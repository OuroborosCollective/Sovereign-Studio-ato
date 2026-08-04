---
name: data-integrity
description: Audit PostgreSQL, migrations, vectors, queues, backups, retention, and repair candidates without confusing metadata or previews with production truth.
triggers:
  - inspect database
  - verify migration
  - audit vector memory
  - plan data repair
---

# Data integrity

Prefer schema, migration, aggregate, receipt, and canary evidence that does not expose row data.

Use database architecture inventory and schema reconciliation to identify canonical ownership. Use deterministic receipts and previous-hash chains for revision-bound reads. A migration preview proves only rollback-path behavior in its isolated preview target; it does not prove production application.

For inconsistent data, first build a bounded, idempotent repair plan with exact predicates, current identity hashes, row estimates, and reversibility. Apply nothing until state and authorization are reconfirmed.

Verify backups through isolated restoration, digest equality, and integrity checks. Reconcile vector memory using source hashes, vector hashes, embedding-model identity, outbox state, duplicate counts, and queue progress. Audit retention, pseudonymization, export, tenant separation, and legal-hold controls separately.

Never expose secrets or unrestricted SQL through plugin guidance. Never label a database, migration, vector index, or backup healthy solely because a static file exists.
