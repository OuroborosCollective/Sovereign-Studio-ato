# Sovereign Brain — Runtime Truth

schema: sovereign.brain-projection.v1  
truth_class: DERIVED_PROJECTION  
runtime_verified: false

## compiled_truth

The project brain can describe the evidence contract, but it cannot satisfy that contract.

Canonical causal sequence:

```text
action
-> result
-> persisted or bound state
-> next allowed / blocked / approval-required action
-> independent target-system readback
```

For release/deployment work the expected chain is:

```text
reviewed exact head
-> exact-head CI
-> merge
-> resolve merged main revision
-> immutable artifact/image bound to that revision
-> controlled deploy/self-update
-> revision + digest + protocol + registry + container + PatchMon readback
```

Evidence strength is scoped to the claim. Examples:

- Git blob/revision evidence proves repository content, not deployment.
- CI proves only the tested exact head and declared checks.
- Artifact digest proves artifact identity, not that it is running.
- Container liveness proves liveness, not revision parity or functional readiness.
- Runtime/API/database/MCP/PatchMon readbacks prove only what their bounded observations actually inspect.
- A contradiction between evidence lanes produces `CONTRADICTED`, not a forced green result.

No text in `BRAIN.md` or `brain/*.md` is accepted as target-system readback.

## timeline

Keep live runtime history in the systems that generated it: GitHub Actions, artifact registries, deployment receipts, database/migration evidence, MCP registry/protocol evidence, container state, provider receipts, and PatchMon. Brain pages only retain durable navigation and interpretation rules.
