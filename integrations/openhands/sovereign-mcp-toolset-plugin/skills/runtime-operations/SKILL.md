---
name: runtime-operations
description: Diagnose containers, deployment, queues, capacity, PatchMon, topology, and runtime dependencies through fresh readback before any protected operation.
triggers:
  - diagnose runtime
  - inspect containers
  - check PatchMon
  - plan deployment
---

# Runtime operations

Repository state and runtime state are separate evidence domains.

Begin with bounded reads such as `runtime_dependency_health_matrix`, `vps_capacity_resource_pressure_assess`, `vps_container_status`, `configuration_drift_assess`, and the appropriate PatchMon inventory/status tool. Correlate revision, immutable image digest, container identity, protocol readiness, broker readiness, queue state, topology, database health, and rollback evidence.

For a failure, classify the first causal failure family and generate a bounded runbook or diagnostic chain. Stop and re-plan if new evidence changes that family.

External mutations require exact state confirmation, owner policy satisfaction, immutable identities, and explicit rollback conditions. Do not hotpatch a production container, install dependencies on the VPS, or treat a restarted process as a verified release. Build and test through the repository/CI supply chain, deploy immutable artifacts, then read runtime and PatchMon evidence again.

This repository-only plugin performs no runtime action by itself. Its committed MCP configuration is inactive.
