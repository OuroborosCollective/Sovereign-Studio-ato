---
name: mcp-governance
description: Govern MCP registry identity, schema compatibility, toolchain composition, remote discovery, provider routing, and owner approval without duplicating the MCP runtime.
triggers:
  - inspect MCP registry
  - configure MCP tools
  - validate MCP schema
  - route LLM provider
---

# MCP governance

Treat the remote Sovereign MCP registry as the only executable MCP tool source. This plugin contributes guidance, not implementations.

1. Read `mcp_runtime_boundaries` and `mcp_tool_contract_registry` before relying on tool names, effects, annotations, schemas, or hashes.
2. Verify expected names or a reviewed registry snapshot with `mcp_registry_snapshot_verify`.
3. Use `mcp_schema_compatibility_audit` when published, repository, adapter, and agent-expected contracts must remain compatible.
4. Compose only non-executing chains with `mcp_toolchain_compile`; validate and advance them one node at a time.
5. Use capability routing to select the smallest eligible tool set.
6. Require owner policy evaluation for protected mutations and preserve revision/payload binding.
7. Use direct OpenRouter contracts for paid routes and `freellm_*` contracts for managed free routes.

The `litellm_*` names in the source snapshot are retired compatibility tombstones. Do not activate, document, or infer an active LiteLLM provider path from them.

Do not create local proxy tools that imitate remote success. If the remote registry cannot be read, mark the capability unavailable or unverified rather than substituting a stub.
