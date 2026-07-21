# Sovereign Operational Governance

## Name

`sovereign-operational-governance`

## Purpose

Provide the existing Sovereign ChatGPT MCP container with one bounded capability-routing and operational-governance layer. The skill does not create a second control plane. It registers its tools in the same FastMCP instance through `launcher.py` and preserves the existing repository, broker, owner-input, database and Draft-PR boundaries.

## Core rule

The online LLM interprets natural language and maps the mission to structured capability values. Deterministic runtime code may rank only currently registered tools by capability, effect class and contract metadata. A recommendation is never executed automatically.

## Installed base skill families

This manifest owns 16 governance families. The companion `sovereign-operational-assurance` manifest adds 27 distinct families and reuses the registry family rather than duplicating it. The combined routing inventory therefore exposes 43 unique skill families and 48 unique profile tool identities.

1. `sovereign-tool-capability-router`
2. `sovereign-mcp-registry-verifier`
3. `sovereign-evidence-graph-operator`
4. `sovereign-schema-ownership-reconciler`
5. `sovereign-llm-route-sre`
6. `sovereign-agent-run-recovery`
7. `sovereign-semantic-intent-boundary-guardian`
8. `sovereign-cost-credit-settlement-reconciler`
9. `sovereign-backup-restore-verifier`
10. `sovereign-slo-error-budget-operator`
11. `sovereign-configuration-drift-operator`
12. `sovereign-mcp-tool-contract-registry`
13. `sovereign-runtime-runbook-generator`
14. `sovereign-ownership-codeowners-guardian`
15. `sovereign-compliance-evidence-exporter`
16. `sovereign-mcp-toolchain-composer`

## Registered base MCP tools

The following 16 tools are implemented by `operational_governance_tools.py`. `toolchain_composition.py` adds five typed, non-executing composition tools. The assurance module registers 28 additional callable tools, including its inventory, and reuses `mcp_tool_contract_registry` rather than duplicating it.

- `operational_skill_inventory`
- `mcp_tool_contract_registry`
- `tool_recommend_for_mission`
- `mcp_registry_snapshot_verify`
- `evidence_graph_build`
- `schema_migration_reconcile`
- `llm_route_reliability_assess`
- `agent_run_liveness_assess`
- `semantic_intent_boundary_audit`
- `cost_credit_settlement_reconcile`
- `backup_restore_evidence_verify`
- `slo_error_budget_assess`
- `configuration_drift_assess`
- `runtime_runbook_generate`
- `ownership_codeowners_guard`
- `compliance_evidence_export`
- `mcp_toolchain_contract_inventory`
- `mcp_toolchain_compile`
- `mcp_toolchain_validate`
- `mcp_toolchain_next_step`
- `mcp_diagnostic_chain_plan`

## Recommended workflow

1. Read `operational_skill_inventory`.
2. Convert the mission into structured capabilities and allowed effects.
3. Call `tool_recommend_for_mission`.
4. Load full contracts only for the selected tools through `mcp_tool_contract_registry`.
5. For multi-step work, compile and validate one bounded ToolChain DAG, then request only the next safe node.
6. Resolve exact repository, PR, CI and installed revision identities.
7. Collect authoritative evidence without inferring missing success.
8. Generate a bounded runbook or diagnostic ToolChain when a failure family is known.
9. Apply changes only through the existing authorized repository or host paths.
10. Verify the original failure family and adjacent contracts.
11. End code work at one Draft PR unless the owner separately authorizes a later lifecycle action.

## Runtime boundaries

- No generic shell.
- No arbitrary SQL.
- No raw database rows from the schema reconciler.
- No secret or owner-protected value accepted as a tool argument.
- No tool recommendation or ToolChain node is automatically executed.
- ToolChain graphs are hash-bound to the live registry and output schemas.
- A failed ToolChain node stops and requires new evidence before replanning.
- No merge or deployment is performed by this skill.
- Host mutation remains queue-only.
- Repository mutations remain workspace-bound and end at Draft PR by default.
- Compliance exports are evidence packages, not certifications.
- Static semantic-boundary findings are candidates until active callers and runtime paths are proven.
- Backup creation alone never proves recoverability; an isolated restore and digest verification are required.
- LLM route readiness requires current model inventory, active alias, verified price, healthy canary and usable quota evidence.

## Failure handling

Stop rather than guess when any of these conditions occurs:

- exact revision identity is unresolved or changes during work;
- a required registered tool is absent from the live registry;
- the approved registry snapshot does not match;
- a new failure family replaces the original one;
- required owner approval or protected input is missing;
- evidence belongs to another revision;
- restore, settlement, schema, SLO or provider-route evidence is incomplete;
- a proposed action exceeds the tool's declared effect boundary.

## Verification contract

The immutable MCP image must contain this file, `operational_governance_tools.py`, `toolchain_composition.py`, the companion assurance manifest and `operational_assurance_tools.py`. CI and the VPS installer must compile/import all modules, verify their callables, inspect the combined live FastMCP registry and run the dedicated regression tests. A repository file or successful import alone is not a production installation claim.
