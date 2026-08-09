# Sovereign Brain — Durable Decisions

schema: sovereign.brain-projection.v1  
truth_class: DERIVED_PROJECTION  
runtime_verified: false

## compiled_truth

These are compact projections of durable repository decisions. The canonical source must still be read before mutation.

- **Truth is causal and evidence-bound.** Tool success, UI state, model output, telemetry, liveness, or a historical ledger entry cannot independently establish runtime success.
- **No fake live path.** Mocks, stubs, facades, generated snapshots, or hardcoded green states cannot stand in for product/runtime evidence.
- **Repository and deployment are distinct.** Code in Git does not prove the deployed image, MCP registry, database, provider state, or live container matches it.
- **Merge is owner-scoped and exact-head-bound.** Authority does not erase revision, mergeability, or required technical evidence.
- **Draft PR is the normal agent review boundary.** A plan without a real diff is not an implementation PR.
- **Provider architecture:** direct OpenRouter for paid execution; direct FreeLLM/Revolver for free execution; LiteLLM is not an active or rollback transport.
- **Secrets stay outside tracked/user-visible evidence.** No tokens, credentials, private keys, or secret-shaped real values in brain pages, docs, chat, PRs, Issues, tests, telemetry, or ledgers.
- **Sovereign Studio ATO and Arelorian Wasd are distinct systems.** No shared runtime, database, container, migration, or deterministic truth is implied.
- **Continuity is provenance, not GitHub integration authority.** The Continuity workflow may record historical evidence but must not block PR, merge, release, artifact, deployment, or runtime lanes.
- **The brain is a projection, not memory ownership.** Existing durable memory, knowledge, pattern, Continuity, and N+1 stores keep their canonical responsibilities.

## timeline

For when/why a decision changed, follow Git history, PR discussion, owner decisions, architecture documents, CI runs, and target-system receipts. Do not add a new decision here without also updating or citing the canonical source that owns it.
