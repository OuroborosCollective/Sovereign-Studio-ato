# Sovereign Operational Assurance

## Name

`sovereign-operational-assurance`

## Purpose

Extend the existing Sovereign ChatGPT MCP container with the final operational, data, memory, MCP-governance, security and supply-chain capabilities numbered 16 through 43. This skill uses the same FastMCP process, broker, database runtime, isolated workspaces and Draft-PR boundaries as the existing Sovottt operator.

## Duplicate handling

Number 29, `MCP Tool Contract Registry`, already exists as `mcp_tool_contract_registry` in the operational-governance skill. It is reused rather than duplicated. The remaining numbered capabilities add 27 distinct tools plus one assurance inventory tool.

## Installed capabilities

16. VPS Capacity & Resource Pressure Operator — `vps_capacity_resource_pressure_assess`
17. Runtime Dependency Health Matrix — `runtime_dependency_health_matrix`
18. Outbox & Queue Liveness Operator — `outbox_queue_liveness_assess`
19. Scheduled Maintenance Coordinator — `scheduled_maintenance_coordinate`
20. Runtime Topology Change Auditor — `runtime_topology_change_audit`
21. PostgreSQL Query & Index Performance Operator — `postgres_query_index_performance_assess`
22. Data Integrity Invariant Auditor — `data_integrity_invariant_audit`
23. Data Repair Planner — `data_repair_plan_build`
24. Vector Memory Consistency Operator — `vector_memory_consistency_assess`
25. Memory Poisoning & Provenance Guardian — `memory_poisoning_provenance_guard`
26. Learning Pattern Lifecycle Operator — `learning_pattern_lifecycle_preview`
27. Data Retention & Privacy Operator — `data_retention_privacy_audit`
28. Multi-Tenant Isolation Verifier — `multi_tenant_isolation_verify`
29. MCP Tool Contract Registry — existing `mcp_tool_contract_registry`
30. MCP Schema Compatibility Auditor — `mcp_schema_compatibility_audit`
31. MCP Protocol Conformance & Fuzzing — `mcp_protocol_conformance_fuzz_plan`
32. Tool Permission Minimizer — `tool_permission_minimize`
33. Dynamic Execution Containment Auditor — `dynamic_execution_containment_audit`
34. Skill Capability Coverage Mapper — `skill_capability_coverage_map`
35. Skill Lifecycle & Deprecation Operator — `skill_lifecycle_deprecation_preview`
36. Skill Regression Benchmark — `skill_regression_benchmark`
37. Tool Idempotency Verifier — `tool_idempotency_verify`
38. Owner Approval Policy Engine — `owner_approval_policy_evaluate`
39. Secret Lifecycle & Rotation Operator — `secret_lifecycle_rotation_assess`
40. Secret-Literal Triage — `secret_literal_triage`
41. SBOM, Provenance & Image Signing Operator — `sbom_provenance_image_signing_verify`
42. Dependency Vulnerability Remediation Planner — `dependency_vulnerability_remediation_plan`
43. Authentication Chaos & Negative-Test Skill — `authentication_chaos_negative_test_assess`

The suite inventory is exposed as `operational_assurance_skill_inventory`.

## Live evidence paths

`vps_capacity_resource_pressure_assess` reads a fixed host-broker action that gathers CPU count and load, memory and swap, filesystem capacity, inode pressure, Docker stats, container limits, OOM state and host-command queue age. It never mounts the Docker socket into the MCP container.

`runtime_dependency_health_matrix` executes live broker, PostgreSQL, pgvector, container and host-capacity checks. Its document and Milvus functional canaries are optional because they create temporary artifacts and collections; when requested they must clean up before success is claimed.

Other tools consume bounded structured evidence or inspect an isolated repository workspace. They do not accept arbitrary SQL, generic shell commands, secret values or unrestricted network targets.

## Safety boundaries

- Natural-language interpretation remains with the online LLM.
- Runtime routing accepts structured capabilities and tool contracts only.
- Repair, maintenance, lifecycle, retention and approval tools produce plans or decisions, not mutations.
- The dependency matrix is the only new tool allowed to run explicitly requested ephemeral canaries.
- Data tools do not return arbitrary table rows or vector values.
- Secret triage never returns matched literals; only hashes and locations are emitted.
- Secret lifecycle tools accept metadata references only.
- Owner approval evaluation cannot create or grant approval.
- No skill can merge, deploy or self-update by itself.
- Merge, deployment and MCP self-update remain separate owner-authorized Sovottt lifecycle actions.

## Verification contract

The immutable MCP image must contain this manifest and `operational_assurance_tools.py`. The VPS installer and GitHub Actions workflow must verify all callable tools, live FastMCP registration, the final registry count, the host capacity broker action, schema generation and dedicated regression tests before a merge is allowed.
