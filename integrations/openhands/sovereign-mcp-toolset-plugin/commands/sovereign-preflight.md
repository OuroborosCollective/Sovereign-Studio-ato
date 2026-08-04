---
description: Compile and validate a bounded Sovereign MCP toolchain for the current mission without executing any node.
---

Prepare a Sovereign mission preflight for the user's current request.

- State the mission in one bounded summary.
- Identify required capabilities.
- Declare allowed effects: read, workspace-write, and/or external-write.
- List the evidence that must exist before completion can be claimed.
- Prefer the smallest eligible set of live registered tools.
- Run `sovereign_mission_preflight` and report its registry snapshot, selected contracts, findings, and first ready node.

Do not execute the proposed chain. Bind exact runtime context, revision, and owner approval separately before advancing.
