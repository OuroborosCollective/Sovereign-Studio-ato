---
name: repository-evidence
description: Inspect and change a repository through exact-revision workspaces, deterministic architecture maps, bounded patches, CI evidence, and Draft PR readback.
triggers:
  - inspect repository
  - change repository code
  - diagnose CI
  - create draft PR
---

# Repository evidence

Start repository work in an isolated workspace with `workspace_prepare`. Resolve its exact base and head before reading or changing files.

Use the architecture radar as complementary evidence:

- `deterministic_architecture_inventory` classifies production, test, persistence, effect, core, and projection surfaces.
- `repository_architecture_snapshot` maps endpoints, calls, workflows, migrations, tests, mirrors, ownership, and truth boundaries.
- `repository_architecture_drift_report` identifies static contract, parser, workflow, mirror, and LLM/tool-boundary drift candidates.
- `backend_architecture_assess` maps bounded backend/platform capabilities and scan limits.

Read exact files or search tracked content before patching. For existing files, use bounded search/replace or hash-bound mutation contracts; never reconstruct large live files from excerpts. Run relevant local checks, delegate dependency-dependent Node builds to GitHub Actions, inspect the complete diff, and build a change-impact manifest.

Before a Draft PR, update required append-only continuity records. After publication, bind conclusions to the exact PR head and its terminal checks. Do not merge, deploy, or self-update merely because a Draft PR exists.

Static repository analysis is not runtime success. Runtime assertions require separate authoritative readback.
