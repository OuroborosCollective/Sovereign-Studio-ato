# Sovereign Brain — Continuity and Provenance

schema: sovereign.brain-projection.v1  
truth_class: DERIVED_PROJECTION  
runtime_verified: false

## compiled_truth

Continuity has a bounded purpose: preserve provenance, decisions, relationships, handoff context, and historical evidence so later work can understand where decisions came from.

It is **not** a technical completion authority.

For GitHub integration specifically:

- the `continuity-ledger` workflow is advisory historical evidence;
- Continuity validation findings may be surfaced as warnings and summaries;
- Continuity must not be a required PR/merge/release blocker;
- an incomplete or stale Continuity record does not negate independently verified repository, test, security, artifact, deployment, runtime, database, MCP, or PatchMon evidence;
- a Continuity record also cannot upgrade weak technical evidence into a stronger truth class.

The existing Continuity context and append-only ledgers remain useful historical/provenance sources. They should keep secrets and raw chat out, preserve owner-provenance distinctions, and avoid rewriting history.

Inside MCP/operator work, a Continuity read may still provide useful starting context. That context remains subordinate to fresh revision and runtime evidence.

## timeline

Canonical historical sources remain:

- `docs/sovereign-continuity/CONTEXT.md`;
- `docs/sovereign-continuity/LEDGER.jsonl`;
- `tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl`;
- Git history, Issues/PRs, CI, receipts, deployment/runtime evidence.

The two ledgers are historical append-only records; this brain page is only an index and interpretation boundary around them.
