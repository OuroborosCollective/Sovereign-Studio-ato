# Context Trust and Tool-Chain Guardrails Architecture Inventory

**Issue**: #1118  
**Revision**: `d7fefc4` (2026-08-07)  
**Status**: INVENTORY

## Overview

This document captures the existing Sovereign runtime surfaces that relate to context trust,
tool-chain guardrails, and deterministic policy enforcement. It serves as the prerequisite
inventory for implementing Issue #1118's three-layer architecture.

---

## 1. Existing Tool Policy Surfaces

### 1.1 `tool_policy.py` (canonical)

**Path**: `backend/agent_runtime/tool_policy.py`

**Owner**: Sovereign Agent Runtime  
**Purpose**: Hard policy enforcement for internal agent tools before execution

**Current scope**:
- `ToolPolicyResult` dataclass with `allowed`, `blockers`, `messages`
- `validate_workspace_ready()` - workspace existence check
- `validate_repo_ready()` - repo directory existence check
- `validate_tool_path()` - path safety (secret paths, forbidden prefixes)
- `resolve_repo_tool_path()` - resolved path + policy check
- `validate_shell_command()` - command allowlist and forbidden patterns

**Key constants**:
- `SECRET_PATH_NAMES` - blocked filename patterns (.env, id_rsa, etc.)
- `SECRET_PATH_SUFFIXES` - blocked extensions (.pem, .key, etc.)
- `FORBIDDEN_PATH_PREFIXES` - blocked path prefixes (.git/, node_modules/, etc.)
- `FORBIDDEN_COMMAND_PARTS` - blocked command fragments (sudo, curl|, wget|, etc.)
- `ALLOWED_COMMAND_PREFIXES` - explicit allowlist tuples

**Gaps vs #1118 requirements**:
- No Context Trust State machine
- No provenance classification of tool inputs/results
- No capability binding or effective capability reduction
- No exact tool identity resolution (name-only dispatch)
- No quarantine before result projection

### 1.2 `workspace_policy.py` (canonical)

**Path**: `backend/agent_runtime/workspace_policy.py`

**Owner**: Sovereign Agent Runtime  
**Purpose**: Workspace path safety and permission boundaries

**Current scope**:
- `workspace_root()` - configurable workspace base path
- `workspace_runtime_identity()` - uid/gid for workspace files
- `safe_workspace_path()` - path escape prevention
- `assert_safe_workspace_id()` - workspace ID validation
- `validate_workspace_relative_path()` - relative path normalization
- `validate_repo_url_for_workspace()` - GitHub URL validation (no embedded credentials)

**Gaps vs #1118 requirements**:
- No trust epoch or revision binding for workspace access
- No taint tracking when untrusted content enters workspace
- No trust-state inheritance for delegated operations

---

## 2. Receipt and Identity Surfaces

### 2.1 `agent_run_receipts.py` (canonical)

**Path**: `backend/agent_runtime/agent_run_receipts.py`

**Owner**: Sovereign Agent Runtime  
**Purpose**: Canonical, revision-bound receipts for real agent tool calls

**Current scope**:
- `McpRuntimeIdentity` - MCP revision, image digest, verification flags
- `GitWorkspaceIdentity` - repository, base commit, diff SHA256, authoritative readback
- `canonical_value()`, `canonical_bytes()`, `canonical_sha256()` - deterministic serialization
- `read_mcp_runtime_identity()` - broker socket call for MCP identity
- `read_git_workspace_identity()` - git status/diff in workspace
- `build_agent_run_receipt()` - constructs tamper-evident receipt body
- `verify_agent_run_receipt_chain()` - verifies receipt chain integrity

**Receipt schema**: `sovereign.agent-run-receipt.v1`

**Key fields**:
- sequence, repository, base_commit_sha
- mcp_revision, mcp_image_digest, mcp_revision_verified
- agent_run_id, tool_name, call_id
- evidence_gate_result (PASS/FAIL/BLOCKED)
- mutation_performed, observed_effect
- authoritative_readback_sha256
- previous_receipt_sha256 (chain)

**Gaps vs #1118 requirements**:
- No `ToolCallPolicyReceipt` or `ToolResultPolicyReceipt` schemas
- No `ContextTrustTransitionReceipt`
- No `DelegationTrustReceipt`
- No `EffectiveCapabilityReceipt`
- No `SanitizationReceipt`
- No ContextEvidenceItem schema

---

## 3. Tool Execution Surfaces

### 3.1 `tool_runner.py` (canonical)

**Path**: `backend/agent_runtime/tool_runner.py`

**Owner**: Sovereign Agent Runtime  
**Purpose**: Tool execution engine with workspace scoping and event tracking

**Current scope**:
- `ToolExecution` - individual tool execution result
- `ToolRunnerResult` - aggregate session result (success/error/blocked counts)
- `ToolRunner` class with `execute()`, `execute_single()`, `execute_provider_neutral()`
- Uses `get_tool_registry()` for tool lookup
- Uses `ToolEventLog` for event tracking

**Gaps vs #1118 requirements**:
- No pre-execution policy check that can block based on trust state
- No quarantine of raw tool results before projection
- No result classification (VERIFIED_SOURCE, EXTERNAL_UNTRUSTED, etc.)
- No exact tool identity binding between policy and execution

---

## 4. MCP Integration

### 4.1 `mcp_integration.py` (canonical)

**Path**: `backend/agent_runtime/mcp_integration.py`

**Owner**: Sovereign MCP Fleet  
**Purpose**: MCP server registration, capability manifests, and runtime binding

**Current scope** (inferred from related files):
- MCP server lifecycle management
- Capability registry integration
- Tool call routing to MCP servers

**Gaps vs #1118 requirements**:
- No trust-state propagation through MCP call chain
- No capability manifest binding to trust epochs
- No exact tool identity resolution across MCP boundaries

---

## 5. Related Issues and Dependencies

| Issue | Relationship | Blocking |
|-------|--------------|----------|
| #1116 | Run Envelope and Capability Manifest | Yes - need manifest for capability reduction |
| #1113 | Durable Workflow and Permission Receipts | Yes - need permission receipts for mutations |
| #1115 | TypeScript Contract Pilot | No - provides schema patterns |
| #1100 | Actual target-system readbacks | Yes - VERIFIED requires #1100 readback |
| #1111 | Bug Evidence Lane | No - failure classification source |

---

## 6. Proposed New Canonical Surfaces

Per Issue #1118's implementation plan:

```
backend/agent_runtime/guardrails/
├── __init__.py
├── context_trust.py          # Trust state enum and transition logic
├── trust_receipts.py         # Receipt schemas (ToolCall, ToolResult, Context, Delegation)
├── tool_call_policy.py       # Pre-execution policy evaluation
├── tool_result_policy.py     # Result quarantine and classification
└── trust_state_machine.py    # Epoch management and capability reduction

backend/agent_runtime/contracts/
├── context_evidence_item.v1.schema.json
├── tool_call_policy_receipt.v1.schema.json
├── tool_result_receipt.v1.schema.json
├── context_trust_transition_receipt.v1.schema.json
├── delegation_trust_receipt.v1.schema.json
└── effective_capability_receipt.v1.schema.json
```

---

## 7. Implementation Order (per Issue #1118)

1. **This inventory** - DONE (current document)
2. **ContextEvidenceItem and Receipt schemas** - Step 2
3. **Trust State Machine without runtime changes** - Step 3
4. **Tool Result Quarantine for read-only pilot tool** - Step 4
5. **Tool Call Policy with exact tool identity binding** - Step 5
6. **DelegationTrustReceipt and inheritance tests** - Step 6
7. **Effective capability reduction with #1116 manifest** - Step 7
8. **Sanitizer status SANITIZED_UNVERIFIED** - Step 8
9. **MCP/Runtime projections and structured errors** - Step 9
10. **#1113/#1100 receipt and readback integration** - Step 10

---

## 8. Ownership and Mirror Rules

- Canonical implementation: `backend/agent_runtime/guardrails/`
- Mirror path (if deployment mirror exists): `scripts/sovereign-backend/agent_runtime/guardrails/`
- Mirror must remain byte-equivalent per AGENTS.md rules
- MCP control plane: `tools/sovereign-chatgpt-mcp/` (separate concern)

---

## 9. Licensing and Clean-Room Notes

This implementation draws from:
- Reference study: `archestra-ai/archestra` @ `654384e2f8d993f5f53c1507916a52c9be1142d9`
- Archestra code is NOT copied. Enterprise-marked files are excluded.
- All implementation is original, clean-room development.

---

*Inventory completed: 2026-08-07*  
*Issue: #1118 - Implement provenance-bound context trust and deterministic tool-chain guardrails*
