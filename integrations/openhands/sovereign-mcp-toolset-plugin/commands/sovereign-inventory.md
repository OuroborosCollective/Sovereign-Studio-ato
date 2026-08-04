---
description: Read the current remote Sovereign MCP registry, operational skill inventory, runtime boundaries, and exact source identities without mutation.
---

Run a read-only Sovereign inventory.

1. Read `mcp_runtime_boundaries`.
2. Read `mcp_tool_contract_registry` without schemas unless schemas are required for the mission.
3. Read `operational_skill_inventory` and the relevant specialist inventory tools.
4. Compare the live result with this package's source-revision snapshots only when drift analysis is requested.
5. Report tool count, registry snapshot hash, skill count, effect distribution, retired compatibility names, and evidence gaps.

Do not claim readiness, authorization, deployment, or runtime health from inventory alone.
