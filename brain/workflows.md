# Sovereign Brain — Workflows

schema: sovereign.brain-projection.v1  
truth_class: DERIVED_PROJECTION  
runtime_verified: false

## compiled_truth

### Repository mutation

1. Resolve exact current `main` and relevant PR/Issue state.
2. Work on an isolated branch/workspace bound to that revision.
3. Read canonical ownership and truth boundaries.
4. Make the smallest architecture-compatible change.
5. Run focused tests/checks on the exact changed head.
6. Publish a reviewable PR with real changed paths and evidence.
7. Merge only with owner-scoped authority and exact-head binding.
8. Re-read merged `main` before any release/deployment claim.

### Release/runtime

Repository implementation and merge are not deployment proof. Build immutable artifacts, bind them to the merged revision, deploy through the controlled path, then read back the actual target system and PatchMon where applicable.

### Continuity evidence

The GitHub `continuity-ledger` check is intentionally **advisory**. It may surface missing or contradictory historical provenance as warnings and summaries, but those findings are not allowed to stop the technical integration chain.

This does not make Continuity data technical truth. It remains a historical/provenance side channel. Product, security, test, artifact, revision, deployment, database, runtime, MCP, and PatchMon evidence retain their own independent gates.

### Brain maintenance

Run:

```bash
python3 scripts/sovereign_brain_projection.py check
python3 -m unittest scripts.test_sovereign_brain_projection -v
```

When a canonical source or brain page deliberately changes, review the projection and run `refresh` to re-bind the manifest hashes. A refresh changes hashes only; it never auto-promotes claims.

## timeline

Workflow history belongs to workflow files, PRs, CI runs, receipts, and Git history. The brain summarizes durable operating order without becoming another workflow engine.
