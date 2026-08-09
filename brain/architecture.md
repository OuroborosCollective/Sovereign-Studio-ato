# Sovereign Brain — Architecture

schema: sovereign.brain-projection.v1  
truth_class: DERIVED_PROJECTION  
runtime_verified: false

## compiled_truth

### Canonical ownership

- Product and contributor contract: `AGENTS.md` and `docs/SOVEREIGN_PRODUCT_TRUTH.md`.
- Canonical backend agent code: `backend/agent_runtime/`.
- Deployment mirrors, where explicitly owned as mirrors: `scripts/sovereign-backend/agent_runtime/`.
- MCP control plane: `tools/sovereign-chatgpt-mcp/`.
- Repository Intelligence is a discovery/editing side channel, not a runtime truth source.
- Continuity context/ledgers preserve provenance and history; they do not replace Git, CI, artifacts, deployment evidence, database truth, or live runtime readback.
- Existing memory surfaces such as `.agents/memory/`, durable memory, reusable memory, pattern/vector memory, and N+1 persistence remain their own bounded systems. This project brain does **not** duplicate them.

### Brain position

```text
canonical repository + owner decisions + CI/artifact/runtime evidence
                         |
                         v
               Sovereign Brain Projection
                 BRAIN.md + brain/*
                         |
              agent orientation/context
```

Information only flows upward as a projection. Editing a brain page cannot mutate or override the source system it describes.

### Truth boundary

A brain page may say where evidence should be found and may compress stable requirements. It cannot by itself prove:

- a currently deployed revision;
- a container/image digest;
- a database migration state;
- an MCP registry state;
- provider health or quota;
- passing CI on a particular head;
- PatchMon health;
- merge or release completion.

Those require their canonical target-system readbacks.

## timeline

Architecture history remains in Git commits, architecture documents, Issues/PRs, migration files, CI runs, immutable artifact metadata, deployment sessions, and PatchMon/runtime evidence. Use those records to explain when and why a boundary changed.
