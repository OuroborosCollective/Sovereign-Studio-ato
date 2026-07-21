from __future__ import annotations

from typing import Annotated, Any, Literal, Union
import hashlib
import json

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

import operational_governance_tools


LOCAL_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

SemanticCategory = Literal[
    "system_scan",
    "code_analysis",
    "database_query",
    "log_inspection",
    "error_diagnosis",
    "code_patch",
    "deployment",
    "orchestration",
    "security",
    "learning",
    "evidence",
]
EffectClass = Literal["read", "workspace-write", "external-write"]
Capability = Literal[
    "repository",
    "ci",
    "release",
    "runtime",
    "container",
    "database",
    "migration",
    "llm",
    "agent",
    "billing",
    "backup",
    "observability",
    "configuration",
    "mcp",
    "security",
    "ownership",
    "compliance",
    "learning",
    "android",
    "document",
    "deterministic",
    "maintenance",
    "privacy",
    "performance",
    "topology",
    "queue",
    "supply-chain",
    "authentication",
    "tenant",
]
PredicateOperator = Literal[
    "exists",
    "equals",
    "matches",
    "contains",
    "is_green",
    "is_owner_approved",
    "is_exact_revision",
    "schema_valid",
]
FailureAction = Literal["stop", "replan", "rollback"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SemanticType(StrictModel):
    category: SemanticCategory
    data_type: Annotated[str, Field(min_length=1, max_length=160)]
    schema_ref: Annotated[str, Field(max_length=300)] = ""
    metadata: dict[str, Any] = {}


class SemanticPredicate(StrictModel):
    predicate_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{1,119}$")]
    subject_ref: Annotated[str, Field(min_length=1, max_length=240)]
    operator: PredicateOperator
    expected_value: Any = None
    evidence_required: bool = True
    failure_family: Annotated[str, Field(max_length=160)] = ""


class NodeOutputMapping(StrictModel):
    kind: Literal["node_output"]
    source_node_id: Annotated[str, Field(min_length=1, max_length=120)]
    output_path: Annotated[str, Field(pattern=r"^/(?:[^/~]|~[01])*(?:/(?:[^/~]|~[01])*)*$")]


class ConstantMapping(StrictModel):
    kind: Literal["constant"]
    value: Any


class RuntimeContextMapping(StrictModel):
    kind: Literal["runtime_context"]
    context_key: Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_.:-]{1,159}$")]


class EvidenceMapping(StrictModel):
    kind: Literal["evidence"]
    evidence_key: Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_.:-]{1,159}$")]


InputMapping = Annotated[
    Union[NodeOutputMapping, ConstantMapping, RuntimeContextMapping, EvidenceMapping],
    Field(discriminator="kind"),
]


class ToolExecutionNode(StrictModel):
    node_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,79}$")]
    tool_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,119}$")]
    dependencies: Annotated[list[str], Field(max_length=16)] = []
    input_mappings: dict[str, InputMapping] = {}
    preconditions: Annotated[list[SemanticPredicate], Field(max_length=32)] = []
    postconditions: Annotated[list[SemanticPredicate], Field(max_length=32)] = []
    effect: EffectClass
    is_idempotent: bool
    is_destructive: bool
    requires_owner_approval: bool
    timeout_seconds: Annotated[int, Field(ge=1, le=900)] = 120
    max_retries: Annotated[int, Field(ge=0, le=5)] = 0
    contract_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    output_semantic_type: SemanticType
    on_failure: FailureAction = "stop"
    drill_down_options: Annotated[list[str], Field(max_length=12)] = []


class McpToolChain(StrictModel):
    chain_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,119}$")]
    title: Annotated[str, Field(min_length=3, max_length=200)]
    target_goal: Annotated[str, Field(min_length=3, max_length=2000)]
    entry_node_id: Annotated[str, Field(min_length=1, max_length=80)]
    nodes: Annotated[dict[str, ToolExecutionNode], Field(min_length=1, max_length=64)]
    expected_output: SemanticType
    allowed_effects: Annotated[list[EffectClass], Field(min_length=1, max_length=3)]
    required_evidence: Annotated[list[str], Field(max_length=32)] = []
    max_iterations: Annotated[int, Field(ge=1, le=64)] = 12
    auto_execute: Literal[False] = False
    registry_snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    chain_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class IncrementalStepSuggestion(StrictModel):
    step_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,79}$")]
    description: Annotated[str, Field(min_length=3, max_length=500)]
    recommended_tool_ids: Annotated[list[str], Field(max_length=12)] = []
    drill_down_options: Annotated[list[str], Field(max_length=12)] = []


class GoalPlanningProposal(StrictModel):
    plan_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,119}$")]
    confidence_ppm: Annotated[int, Field(ge=0, le=1_000_000)]
    initial_pipeline: McpToolChain
    next_phases: Annotated[list[IncrementalStepSuggestion], Field(max_length=24)] = []
    missing_capabilities: Annotated[list[str], Field(max_length=32)] = []


class ToolChainInventoryResult(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    semanticCategories: list[str]
    mappingKinds: list[str]
    hardLimits: dict[str, int]
    boundaries: dict[str, Any]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool


class ToolChainProposalResult(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    proposal: GoalPlanningProposal
    findings: list[dict[str, Any]]
    nextActions: list[str]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool
    truthNotice: str


class ToolChainValidationResult(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    chainSha256: str
    registrySnapshotSha256: str
    executionOrder: list[str]
    readyNodeIds: list[str]
    findings: list[dict[str, Any]]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool
    truthNotice: str


class ToolChainNextStepResult(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    chainSha256: str
    nextNode: dict[str, Any] | None
    readyNodeIds: list[str]
    missingRuntimeContextKeys: list[str]
    missingEvidenceKeys: list[str]
    ownerApprovalRequired: bool
    findings: list[dict[str, Any]]
    nextActions: list[str]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool
    truthNotice: str


_MCP: Any = None
_REGISTERED = False


_CATEGORY_BY_CAPABILITY: dict[str, SemanticCategory] = {
    "repository": "code_analysis",
    "ci": "evidence",
    "release": "deployment",
    "runtime": "system_scan",
    "container": "system_scan",
    "database": "database_query",
    "migration": "database_query",
    "llm": "orchestration",
    "agent": "orchestration",
    "billing": "evidence",
    "backup": "system_scan",
    "observability": "log_inspection",
    "configuration": "system_scan",
    "mcp": "orchestration",
    "security": "security",
    "ownership": "security",
    "compliance": "evidence",
    "learning": "learning",
    "android": "code_analysis",
    "document": "code_analysis",
    "deterministic": "code_analysis",
    "maintenance": "orchestration",
    "privacy": "security",
    "performance": "system_scan",
    "topology": "system_scan",
    "queue": "system_scan",
    "supply-chain": "security",
    "authentication": "security",
    "tenant": "security",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _chain_hash_payload(chain: McpToolChain | dict[str, Any]) -> dict[str, Any]:
    payload = chain.model_dump(mode="json") if isinstance(chain, McpToolChain) else dict(chain)
    payload["chain_sha256"] = ""
    return payload


def _category_for(tool: dict[str, Any]) -> SemanticCategory:
    capabilities = list(tool.get("capabilities") or [])
    for capability in capabilities:
        category = _CATEGORY_BY_CAPABILITY.get(str(capability))
        if category:
            if tool.get("effect") == "workspace-write":
                return "code_patch"
            if tool.get("effect") == "external-write" and category != "security":
                return "deployment"
            return category
    return "orchestration"


def _required_parameters(tool: dict[str, Any]) -> list[str]:
    schema = tool.get("parameters") or {}
    required = schema.get("required") if isinstance(schema, dict) else []
    return [str(item) for item in required or [] if str(item)]


def _predicates_for(tool: dict[str, Any]) -> tuple[list[SemanticPredicate], list[SemanticPredicate]]:
    name = str(tool["name"])
    effect = str(tool["effect"])
    preconditions = [
        SemanticPredicate(
            predicate_id=f"{name}.registered_contract",
            subject_ref=f"tool:{name}",
            operator="exists",
            expected_value=tool["contractSha256"],
            evidence_required=True,
            failure_family="MCP_TOOL_CONTRACT_MISSING",
        ),
        SemanticPredicate(
            predicate_id=f"{name}.output_schema",
            subject_ref=f"tool:{name}:outputSchema",
            operator="schema_valid",
            expected_value=True,
            evidence_required=True,
            failure_family="MCP_TOOL_OUTPUT_SCHEMA_MISSING",
        ),
    ]
    if effect != "read":
        preconditions.append(
            SemanticPredicate(
                predicate_id=f"{name}.exact_revision",
                subject_ref="runtime:exactRevision",
                operator="is_exact_revision",
                expected_value=True,
                evidence_required=True,
                failure_family="EXACT_REVISION_REQUIRED",
            )
        )
    if effect == "external-write":
        preconditions.append(
            SemanticPredicate(
                predicate_id=f"{name}.owner_approval",
                subject_ref=f"approval:{name}",
                operator="is_owner_approved",
                expected_value=True,
                evidence_required=True,
                failure_family="OWNER_APPROVAL_REQUIRED",
            )
        )
    postconditions = [
        SemanticPredicate(
            predicate_id=f"{name}.result_schema",
            subject_ref=f"result:{name}",
            operator="schema_valid",
            expected_value=True,
            evidence_required=True,
            failure_family="TOOL_OUTPUT_SCHEMA_VIOLATION",
        ),
        SemanticPredicate(
            predicate_id=f"{name}.evidence_recorded",
            subject_ref=f"evidence:{name}",
            operator="exists",
            expected_value=True,
            evidence_required=True,
            failure_family="TOOL_EXECUTION_EVIDENCE_MISSING",
        ),
    ]
    return preconditions, postconditions


def _registry() -> tuple[dict[str, dict[str, Any]], str]:
    registry = operational_governance_tools.mcp_tool_contract_registry(
        include_schemas=True,
        max_tools=1000,
    )
    return {item["name"]: item for item in registry.tools}, registry.registrySnapshotSha256


def _execution_order(nodes: dict[str, ToolExecutionNode]) -> tuple[list[str], list[dict[str, Any]]]:
    indegree = {node_id: 0 for node_id in nodes}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    findings: list[dict[str, Any]] = []
    for node_id, node in nodes.items():
        for dependency in node.dependencies:
            if dependency not in nodes:
                findings.append(
                    {
                        "severity": "P0",
                        "family": "TOOLCHAIN_DEPENDENCY_MISSING",
                        "nodeId": node_id,
                        "dependency": dependency,
                    }
                )
                continue
            if dependency == node_id:
                findings.append(
                    {
                        "severity": "P0",
                        "family": "TOOLCHAIN_SELF_DEPENDENCY",
                        "nodeId": node_id,
                    }
                )
                continue
            indegree[node_id] += 1
            outgoing[dependency].append(node_id)
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for target in sorted(outgoing[node_id]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    if len(order) != len(nodes):
        findings.append(
            {
                "severity": "P0",
                "family": "TOOLCHAIN_CYCLE_DETECTED",
                "unresolvedNodeIds": sorted(set(nodes) - set(order)),
            }
        )
    return order, findings


def mcp_toolchain_contract_inventory() -> ToolChainInventoryResult:
    """Describe the bounded ToolChain IR and its non-executing safety boundaries."""
    return ToolChainInventoryResult(
        schemaVersion="sovereign.mcp-toolchain-inventory.v1",
        ok=True,
        status="MCP_TOOLCHAIN_IR_READY",
        semanticCategories=list(SemanticCategory.__args__),
        mappingKinds=["node_output", "constant", "runtime_context", "evidence"],
        hardLimits={
            "maxNodes": 64,
            "maxDependenciesPerNode": 16,
            "maxPredicatesPerSide": 32,
            "maxIterations": 64,
            "maxRetriesPerNode": 5,
        },
        boundaries={
            "naturalLanguageUnderstanding": "online_llm_only",
            "planCompilation": "deterministic_registered_tool_contracts",
            "automaticExecution": False,
            "hardPoliciesRemainExternal": True,
            "ownerApprovalCanBeInferred": False,
            "secretsAccepted": False,
            "toolOutputsRequireSchema": True,
        },
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
    )


def mcp_toolchain_compile(
    mission_summary: Annotated[str, Field(min_length=3, max_length=2000)],
    required_capabilities: Annotated[list[Capability], Field(min_length=1, max_length=12)],
    desired_end_state: SemanticType,
    start_state: Annotated[list[SemanticType], Field(max_length=32)] = [],
    allowed_effects: Annotated[list[EffectClass], Field(min_length=1, max_length=3)] = ["read"],
    required_evidence: Annotated[list[str], Field(max_length=32)] = [],
    preferred_tools: Annotated[list[str], Field(max_length=32)] = [],
    max_nodes: Annotated[int, Field(ge=1, le=16)] = 8,
) -> ToolChainProposalResult:
    """Compile an LLM-understood mission into a typed, non-executing ToolChain proposal."""
    registry_by_name, registry_hash = _registry()
    allowed = set(allowed_effects)
    findings: list[dict[str, Any]] = []
    selected_names: list[str] = []

    for name in preferred_tools:
        tool = registry_by_name.get(name)
        if tool is None:
            findings.append({"severity": "P1", "family": "PREFERRED_TOOL_NOT_REGISTERED", "tool": name})
            continue
        if tool["effect"] not in allowed:
            findings.append(
                {
                    "severity": "P0",
                    "family": "PREFERRED_TOOL_EFFECT_NOT_ALLOWED",
                    "tool": name,
                    "effect": tool["effect"],
                }
            )
            continue
        if name not in selected_names:
            selected_names.append(name)

    route = operational_governance_tools.tool_recommend_for_mission(
        mission_summary=mission_summary,
        required_capabilities=required_capabilities,
        allowed_effects=allowed_effects,
        required_evidence=required_evidence,
        excluded_tools=selected_names + [
            "mcp_toolchain_compile",
            "mcp_toolchain_validate",
            "mcp_toolchain_next_step",
            "mcp_diagnostic_chain_plan",
        ],
        max_tools=max_nodes,
    )
    for candidate in route.evidence.get("selectedTools") or []:
        name = str(candidate.get("name") or "")
        if name and name in registry_by_name and name not in selected_names:
            selected_names.append(name)
        if len(selected_names) >= max_nodes:
            break

    missing_capabilities = list(route.evidence.get("missingCapabilities") or [])
    findings.extend(route.findings)
    if not selected_names:
        selected_names = ["mcp_tool_contract_registry"]
        findings.append(
            {
                "severity": "P1",
                "family": "TOOLCHAIN_FALLBACK_TO_REGISTRY_INSPECTION",
            }
        )

    nodes: dict[str, ToolExecutionNode] = {}
    previous_node_id = ""
    for index, name in enumerate(selected_names[:max_nodes], 1):
        tool = registry_by_name[name]
        node_id = f"step_{index:02d}_{name[:48]}"
        preconditions, postconditions = _predicates_for(tool)
        input_mappings: dict[str, InputMapping] = {}
        for parameter in _required_parameters(tool):
            input_mappings[parameter] = RuntimeContextMapping(
                kind="runtime_context",
                context_key=f"tool_input.{name}.{parameter}",
            )
        annotations = tool.get("annotations") or {}
        node = ToolExecutionNode(
            node_id=node_id,
            tool_id=name,
            dependencies=[previous_node_id] if previous_node_id else [],
            input_mappings=input_mappings,
            preconditions=preconditions,
            postconditions=postconditions,
            effect=tool["effect"],
            is_idempotent=bool(annotations.get("idempotentHint")),
            is_destructive=bool(annotations.get("destructiveHint")),
            requires_owner_approval=tool["effect"] == "external-write",
            timeout_seconds=120,
            max_retries=1 if annotations.get("idempotentHint") else 0,
            contract_sha256=tool["contractSha256"],
            output_semantic_type=SemanticType(
                category=_category_for(tool),
                data_type=f"{name}.result",
                schema_ref=f"mcp://tool/{name}/output",
                metadata={"outputSchemaSha256": _sha256(tool.get("outputSchema") or {})},
            ),
            on_failure="replan" if tool["effect"] == "read" else "stop",
            drill_down_options=[
                "inspect exact tool contract",
                "request alternative registered tool",
                "stop and collect missing evidence",
            ],
        )
        nodes[node_id] = node
        previous_node_id = node_id

    chain_id = f"toolchain.{_sha256({'mission': mission_summary, 'tools': selected_names})[:20]}"
    chain_payload = {
        "chain_id": chain_id,
        "title": f"Toolchain: {mission_summary[:120]}",
        "target_goal": mission_summary,
        "entry_node_id": next(iter(nodes)),
        "nodes": {key: node.model_dump(mode="json") for key, node in nodes.items()},
        "expected_output": desired_end_state.model_dump(mode="json"),
        "allowed_effects": list(dict.fromkeys(allowed_effects)),
        "required_evidence": list(dict.fromkeys(required_evidence)),
        "max_iterations": min(64, max(4, len(nodes) * 2)),
        "auto_execute": False,
        "registry_snapshot_sha256": registry_hash,
        "chain_sha256": "",
    }
    chain_payload["chain_sha256"] = _sha256(chain_payload)
    chain = McpToolChain.model_validate(chain_payload)

    covered = set(route.evidence.get("coveredCapabilities") or [])
    required = set(required_capabilities)
    coverage_ppm = len(covered & required) * 1_000_000 // max(1, len(required))
    contract_ppm = sum(
        1 for node in nodes.values() if node.contract_sha256 and node.output_semantic_type.schema_ref
    ) * 1_000_000 // max(1, len(nodes))
    confidence_ppm = min(1_000_000, (coverage_ppm * 3 + contract_ppm) // 4)

    next_phases = [
        IncrementalStepSuggestion(
            step_id="validate_chain",
            description="Validate graph, contracts, effects, mappings and current registry hashes.",
            recommended_tool_ids=["mcp_toolchain_validate"],
            drill_down_options=["inspect findings", "replace one tool", "reduce allowed effects"],
        ),
        IncrementalStepSuggestion(
            step_id="bind_runtime_context",
            description="Bind required parameters from explicit runtime context or evidence without secrets.",
            recommended_tool_ids=["mcp_toolchain_next_step"],
            drill_down_options=["supply exact revision", "supply owner approval", "collect missing evidence"],
        ),
    ]
    if missing_capabilities:
        next_phases.append(
            IncrementalStepSuggestion(
                step_id="resolve_capability_gaps",
                description="Resolve missing capabilities before extending or executing the plan.",
                recommended_tool_ids=["skill_capability_coverage_map", "mcp_tool_contract_registry"],
                drill_down_options=missing_capabilities[:12],
            )
        )

    ok = not any(item.get("severity") == "P0" for item in findings) and not missing_capabilities
    proposal = GoalPlanningProposal(
        plan_id=chain_id.replace("toolchain", "plan", 1),
        confidence_ppm=confidence_ppm,
        initial_pipeline=chain,
        next_phases=next_phases,
        missing_capabilities=missing_capabilities,
    )
    return ToolChainProposalResult(
        schemaVersion="sovereign.mcp-toolchain-proposal.v1",
        ok=ok,
        status="MCP_TOOLCHAIN_PROPOSED" if ok else "MCP_TOOLCHAIN_PROPOSAL_INCOMPLETE",
        proposal=proposal,
        findings=findings,
        nextActions=[
            "validate the proposal against the live registry",
            "bind required runtime-context and evidence keys explicitly",
            "execute no tool automatically; request the next safe node only",
        ],
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
        truthNotice=(
            "The online model interprets the mission. This compiler only combines currently registered "
            "tool contracts and never executes the resulting chain."
        ),
    )


def mcp_toolchain_validate(chain: McpToolChain) -> ToolChainValidationResult:
    """Validate one ToolChain against the live registry without executing any node."""
    registry_by_name, registry_hash = _registry()
    findings: list[dict[str, Any]] = []
    order, graph_findings = _execution_order(chain.nodes)
    findings.extend(graph_findings)

    if chain.entry_node_id not in chain.nodes:
        findings.append(
            {
                "severity": "P0",
                "family": "TOOLCHAIN_ENTRY_NODE_MISSING",
                "entryNodeId": chain.entry_node_id,
            }
        )
    elif chain.nodes[chain.entry_node_id].dependencies:
        findings.append(
            {
                "severity": "P0",
                "family": "TOOLCHAIN_ENTRY_NODE_HAS_DEPENDENCIES",
                "entryNodeId": chain.entry_node_id,
            }
        )
    if chain.registry_snapshot_sha256 != registry_hash:
        findings.append(
            {
                "severity": "P0",
                "family": "TOOLCHAIN_REGISTRY_SNAPSHOT_DRIFT",
                "expected": chain.registry_snapshot_sha256,
                "actual": registry_hash,
            }
        )
    actual_chain_hash = _sha256(_chain_hash_payload(chain))
    if actual_chain_hash != chain.chain_sha256:
        findings.append(
            {
                "severity": "P0",
                "family": "TOOLCHAIN_HASH_MISMATCH",
                "expected": chain.chain_sha256,
                "actual": actual_chain_hash,
            }
        )

    allowed = set(chain.allowed_effects)
    for node_id, node in chain.nodes.items():
        tool = registry_by_name.get(node.tool_id)
        if tool is None:
            findings.append(
                {"severity": "P0", "family": "TOOLCHAIN_TOOL_NOT_REGISTERED", "nodeId": node_id, "tool": node.tool_id}
            )
            continue
        if tool["contractSha256"] != node.contract_sha256:
            findings.append(
                {
                    "severity": "P0",
                    "family": "TOOLCHAIN_TOOL_CONTRACT_DRIFT",
                    "nodeId": node_id,
                    "tool": node.tool_id,
                    "expected": node.contract_sha256,
                    "actual": tool["contractSha256"],
                }
            )
        if tool["effect"] != node.effect:
            findings.append(
                {
                    "severity": "P0",
                    "family": "TOOLCHAIN_EFFECT_MISMATCH",
                    "nodeId": node_id,
                    "declared": node.effect,
                    "actual": tool["effect"],
                }
            )
        if node.effect not in allowed:
            findings.append(
                {
                    "severity": "P0",
                    "family": "TOOLCHAIN_EFFECT_NOT_ALLOWED",
                    "nodeId": node_id,
                    "effect": node.effect,
                }
            )
        if not tool.get("outputSchema"):
            findings.append(
                {
                    "severity": "P0",
                    "family": "TOOLCHAIN_OUTPUT_SCHEMA_MISSING",
                    "nodeId": node_id,
                    "tool": node.tool_id,
                }
            )
        if node.effect == "external-write" and not node.requires_owner_approval:
            findings.append(
                {
                    "severity": "P0",
                    "family": "TOOLCHAIN_EXTERNAL_WRITE_WITHOUT_OWNER_GATE",
                    "nodeId": node_id,
                }
            )
        required_parameters = set(_required_parameters(tool))
        missing_mappings = sorted(required_parameters - set(node.input_mappings))
        if missing_mappings:
            findings.append(
                {
                    "severity": "P0",
                    "family": "TOOLCHAIN_REQUIRED_INPUT_MAPPING_MISSING",
                    "nodeId": node_id,
                    "parameters": missing_mappings,
                }
            )
        for parameter, mapping in node.input_mappings.items():
            if isinstance(mapping, NodeOutputMapping):
                if mapping.source_node_id not in chain.nodes:
                    findings.append(
                        {
                            "severity": "P0",
                            "family": "TOOLCHAIN_MAPPING_SOURCE_MISSING",
                            "nodeId": node_id,
                            "parameter": parameter,
                            "sourceNodeId": mapping.source_node_id,
                        }
                    )
                elif mapping.source_node_id not in node.dependencies:
                    findings.append(
                        {
                            "severity": "P1",
                            "family": "TOOLCHAIN_MAPPING_SOURCE_NOT_DIRECT_DEPENDENCY",
                            "nodeId": node_id,
                            "parameter": parameter,
                            "sourceNodeId": mapping.source_node_id,
                        }
                    )

    ready = [node_id for node_id in order if not chain.nodes[node_id].dependencies]
    ok = not any(item.get("severity") == "P0" for item in findings)
    return ToolChainValidationResult(
        schemaVersion="sovereign.mcp-toolchain-validation.v1",
        ok=ok,
        status="MCP_TOOLCHAIN_VALID" if ok else "MCP_TOOLCHAIN_BLOCKED",
        chainSha256=actual_chain_hash,
        registrySnapshotSha256=registry_hash,
        executionOrder=order,
        readyNodeIds=ready,
        findings=findings,
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
        truthNotice="Validation checks the live registry, schemas, graph and declared effects. It executes no tool and grants no approval.",
    )


def mcp_toolchain_next_step(
    chain: McpToolChain,
    completed_node_ids: Annotated[list[str], Field(max_length=64)] = [],
    approved_node_ids: Annotated[list[str], Field(max_length=64)] = [],
    available_runtime_context_keys: Annotated[list[str], Field(max_length=256)] = [],
    available_evidence_keys: Annotated[list[str], Field(max_length=256)] = [],
    failed_node_id: Annotated[str, Field(max_length=80)] = "",
    failure_family: Annotated[str, Field(max_length=160)] = "",
) -> ToolChainNextStepResult:
    """Return the next safe ToolChain node or a bounded stop/replan decision; never execute it."""
    validation = mcp_toolchain_validate(chain)
    findings = list(validation.findings)
    completed = set(completed_node_ids)
    approved = set(approved_node_ids)
    runtime_keys = set(available_runtime_context_keys)
    evidence_keys = set(available_evidence_keys)

    unknown_completed = sorted(completed - set(chain.nodes))
    if unknown_completed:
        findings.append(
            {
                "severity": "P0",
                "family": "TOOLCHAIN_COMPLETED_NODE_UNKNOWN",
                "nodeIds": unknown_completed,
            }
        )
    if failed_node_id:
        if failed_node_id not in chain.nodes:
            findings.append(
                {"severity": "P0", "family": "TOOLCHAIN_FAILED_NODE_UNKNOWN", "nodeId": failed_node_id}
            )
        return ToolChainNextStepResult(
            schemaVersion="sovereign.mcp-toolchain-next-step.v1",
            ok=False,
            status="MCP_TOOLCHAIN_REPLAN_REQUIRED",
            chainSha256=validation.chainSha256,
            nextNode=None,
            readyNodeIds=[],
            missingRuntimeContextKeys=[],
            missingEvidenceKeys=[],
            ownerApprovalRequired=False,
            findings=findings
            + [
                {
                    "severity": "P1",
                    "family": failure_family or "TOOLCHAIN_NODE_FAILED",
                    "nodeId": failed_node_id,
                    "decision": "stop_and_replan_with_new_evidence",
                }
            ],
            nextActions=[
                "classify the exact failure family",
                "collect new evidence before retry",
                "compile or validate a revised chain; do not retry automatically",
            ],
            mutationPerformed=False,
            runtimeVerified=True,
            secretValuesReturned=False,
            truthNotice="A failed node always stops this advisory chain. No recursive retry is executed automatically.",
        )

    if not validation.ok:
        return ToolChainNextStepResult(
            schemaVersion="sovereign.mcp-toolchain-next-step.v1",
            ok=False,
            status="MCP_TOOLCHAIN_BLOCKED",
            chainSha256=validation.chainSha256,
            nextNode=None,
            readyNodeIds=[],
            missingRuntimeContextKeys=[],
            missingEvidenceKeys=[],
            ownerApprovalRequired=False,
            findings=findings,
            nextActions=["repair the validation findings", "recalculate the chain hash", "validate again"],
            mutationPerformed=False,
            runtimeVerified=True,
            secretValuesReturned=False,
            truthNotice="No next node is returned while the chain or registry contract is invalid.",
        )

    ready = [
        node_id
        for node_id in validation.executionOrder
        if node_id not in completed and set(chain.nodes[node_id].dependencies) <= completed
    ]
    if not ready:
        all_complete = set(chain.nodes) <= completed
        return ToolChainNextStepResult(
            schemaVersion="sovereign.mcp-toolchain-next-step.v1",
            ok=all_complete,
            status="MCP_TOOLCHAIN_COMPLETE" if all_complete else "MCP_TOOLCHAIN_WAITING_FOR_DEPENDENCIES",
            chainSha256=validation.chainSha256,
            nextNode=None,
            readyNodeIds=[],
            missingRuntimeContextKeys=[],
            missingEvidenceKeys=[],
            ownerApprovalRequired=False,
            findings=findings,
            nextActions=["verify expected output and evidence ledger"] if all_complete else ["complete prerequisite nodes"],
            mutationPerformed=False,
            runtimeVerified=True,
            secretValuesReturned=False,
            truthNotice="Completion means all declared nodes were reported complete; it is not independent proof of their effects.",
        )

    node_id = ready[0]
    node = chain.nodes[node_id]
    missing_runtime = sorted(
        mapping.context_key
        for mapping in node.input_mappings.values()
        if isinstance(mapping, RuntimeContextMapping) and mapping.context_key not in runtime_keys
    )
    missing_evidence = sorted(
        mapping.evidence_key
        for mapping in node.input_mappings.values()
        if isinstance(mapping, EvidenceMapping) and mapping.evidence_key not in evidence_keys
    )
    owner_required = node.requires_owner_approval and node_id not in approved
    blocked = bool(missing_runtime or missing_evidence or owner_required)
    status = "MCP_TOOLCHAIN_NODE_READY"
    if owner_required:
        status = "MCP_TOOLCHAIN_WAITING_FOR_OWNER"
    elif missing_runtime or missing_evidence:
        status = "MCP_TOOLCHAIN_WAITING_FOR_BINDINGS"

    next_node = {
        "nodeId": node_id,
        "toolId": node.tool_id,
        "effect": node.effect,
        "contractSha256": node.contract_sha256,
        "inputMappings": node.model_dump(mode="json")["input_mappings"],
        "preconditions": [item.model_dump(mode="json") for item in node.preconditions],
        "postconditions": [item.model_dump(mode="json") for item in node.postconditions],
        "executeAutomatically": False,
    }
    return ToolChainNextStepResult(
        schemaVersion="sovereign.mcp-toolchain-next-step.v1",
        ok=not blocked,
        status=status,
        chainSha256=validation.chainSha256,
        nextNode=next_node,
        readyNodeIds=ready,
        missingRuntimeContextKeys=missing_runtime,
        missingEvidenceKeys=missing_evidence,
        ownerApprovalRequired=owner_required,
        findings=findings,
        nextActions=(
            ["request explicit owner approval bound to this node and payload"]
            if owner_required
            else ["bind the missing non-secret values and re-evaluate"]
            if blocked
            else ["present the node for explicit execution", "validate its structured output before advancing"]
        ),
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
        truthNotice="This result only identifies the next eligible node. Calling the underlying tool remains a separate governed action.",
    )


def mcp_diagnostic_chain_plan(
    failure_family: Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9_:-]{1,159}$")],
    capabilities: Annotated[list[Capability], Field(min_length=1, max_length=10)],
    evidence_summary: Annotated[str, Field(min_length=3, max_length=2000)],
    allowed_effects: Annotated[list[EffectClass], Field(min_length=1, max_length=3)] = ["read"],
    max_nodes: Annotated[int, Field(ge=1, le=12)] = 6,
) -> ToolChainProposalResult:
    """Compile a bounded diagnostic chain that stops and replans on failure-family changes."""
    return mcp_toolchain_compile(
        mission_summary=f"Diagnose {failure_family}: {evidence_summary}",
        required_capabilities=capabilities,
        desired_end_state=SemanticType(
            category="error_diagnosis",
            data_type="DiagnosticResolutionProposal",
            schema_ref="sovereign://mcp/toolchain/diagnostic-resolution/v1",
            metadata={
                "failureFamily": failure_family,
                "maxRepeatedFailureCount": 2,
                "stopOnFailureFamilyChange": True,
                "requireNewEvidenceForRetry": True,
                "allowAutomaticFix": False,
            },
        ),
        start_state=[
            SemanticType(
                category="error_diagnosis",
                data_type="DiagnosticContext",
                schema_ref="sovereign://mcp/toolchain/diagnostic-context/v1",
                metadata={"failureFamily": failure_family, "evidenceSummary": evidence_summary[:1000]},
            )
        ],
        allowed_effects=allowed_effects,
        required_evidence=[failure_family, "exact_revision", "structured_output", "new_evidence_before_retry"],
        max_nodes=max_nodes,
    )


def register(mcp: Any) -> None:
    global _MCP, _REGISTERED
    _MCP = mcp
    if _REGISTERED:
        return
    for tool in (
        mcp_toolchain_contract_inventory,
        mcp_toolchain_compile,
        mcp_toolchain_validate,
        mcp_toolchain_next_step,
        mcp_diagnostic_chain_plan,
    ):
        mcp.tool(annotations=LOCAL_READ_ONLY)(tool)
    _REGISTERED = True
