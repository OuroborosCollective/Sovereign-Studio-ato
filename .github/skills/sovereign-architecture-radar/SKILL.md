---
name: sovereign-architecture-radar
description: Inspect Sovereign Studio ATO architecture with the canonical four-sensor radar, classify static candidates correctly, identify mirrors and truth boundaries, and define the evidence needed before mutation.
---

# Sovereign Architecture Radar

Use this skill before architecture-affecting changes and when ownership or drift is uncertain.

Prefer the available canonical radar quartet:

- `deterministic_architecture_inventory`
- `repository_architecture_snapshot`
- `repository_architecture_drift_report`
- `backend_architecture_assess`

The sensors complement each other. Inventory classifies production/test/persistence/effect/core/runtime-projection surfaces. Snapshot maps endpoints, calls, workflows, migrations, tests, MCP components, mirrors, owners and truth boundaries. Drift reports static contract/workflow/parser/mirror/LLM-tool-boundary candidates. Backend assessment maps backend/platform technologies and risks and must disclose truncation/scope limits.

Rules:

- bind every radar result to the exact repository/workspace revision;
- a static finding is not a proven runtime defect;
- a clean static scan is not proof of runtime health;
- record truncation and unscanned surfaces;
- find the canonical owner before proposing new files or layers;
- preserve required byte-equivalent mirrors;
- define tests and target-system readback required to close each material finding.

If a radar tool is not available, do not invent its output. Perform bounded repository inspection and label the missing sensor evidence explicitly.