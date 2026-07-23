from __future__ import annotations

from dataclasses import asdict
import functools
import hashlib
import json
from pathlib import Path
import re
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

import operational_governance_tools
import toolchain_composition


LOCAL_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

PROFILE_PATH = Path(__file__).resolve().parent / "config" / "sovereign-mcp-operating-profile.json"

_MCP: Any = None
_REGISTERED = False
_ENFORCEMENT_INSTALLED = False
_ENFORCED_TOOL_NAMES: tuple[str, ...] = ()

_EXACT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)
_EXACT_REVISION_FIELDS = (
    "expected_revision",
    "expected_head_sha",
    "confirmation_revision",
    "expected_workspace_sha",
    "expected_base_sha",
    "expected_pr_head_sha",
)
_CONFIRMATION_FIELDS = (
    "confirmation_sha256",
    "confirmation_digest",
    "confirmation_inventory_sha256",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OperatingProfileStatus(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    profileId: str
    profileVersion: str
    profileSha256: str
    registrySnapshotSha256: str
    toolCount: int
    mutableToolCount: int
    enforcementInstalled: bool
    enforcedToolCount: int
    requiredGovernanceTools: list[str]
    missingGovernanceTools: list[str]
    forbiddenToolsPresent: list[str]
    toolsWithoutOutputSchema: list[str]
    unenforcedMutableTools: list[str]
    invariants: dict[str, Any]
    findings: list[dict[str, Any]]
    paths: dict[str, str]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool


class MissionPreflightResult(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    missionSummary: str
    profileSha256: str
    registrySnapshotSha256: str
    selectedTools: list[str]
    route: dict[str, Any]
    proposal: dict[str, Any]
    validation: dict[str, Any]
    findings: list[dict[str, Any]]
    nextActions: list[str]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool
    truthNotice: str


class EnforcementInstallationResult(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    profileSha256: str
    registrySnapshotSha256: str
    mutableToolCount: int
    enforcedToolCount: int
    enforcedTools: list[str]
    findings: list[dict[str, Any]]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool


class OperatingProfileBlocked(RuntimeError):
    """Raised before a mutation when the persistent operating contract is not satisfied."""



def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)



def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()



def _load_profile() -> tuple[dict[str, Any], str]:
    raw = PROFILE_PATH.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    required = {
        "schemaVersion",
        "profileId",
        "profileVersion",
        "enforcementMode",
        "missionPreflight",
        "mutationGate",
        "truthAndCompletion",
        "routeIsolation",
        "secretPolicy",
        "persistence",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise RuntimeError(f"operating profile is missing required keys: {', '.join(missing)}")
    if payload.get("enforcementMode") != "fail-closed":
        raise RuntimeError("operating profile must remain fail-closed")
    mutation_gate = payload.get("mutationGate")
    if not isinstance(mutation_gate, dict) or not mutation_gate.get("enabled") or not mutation_gate.get("automatic"):
        raise RuntimeError("automatic mutation gate must remain enabled")
    return payload, hashlib.sha256(raw).hexdigest()



def _tools() -> list[Any]:
    if _MCP is None:
        raise RuntimeError("operating profile is not registered")
    return list(_MCP._tool_manager.list_tools())



def _is_mutable(tool: Any) -> bool:
    annotations = getattr(tool, "annotations", None)
    return not bool(getattr(annotations, "readOnlyHint", False))



def _effect(tool: Any) -> str:
    annotations = getattr(tool, "annotations", None)
    if bool(getattr(annotations, "readOnlyHint", False)):
        return "read"
    if bool(getattr(annotations, "openWorldHint", False)) or bool(getattr(annotations, "destructiveHint", False)):
        return "external-write"
    return "workspace-write"



def _status_payload() -> OperatingProfileStatus:
    profile, profile_sha256 = _load_profile()
    registry = operational_governance_tools.mcp_tool_contract_registry(include_schemas=True, max_tools=1000)
    tools = _tools()
    names = sorted(str(getattr(tool, "name", "")) for tool in tools)
    mutable = sorted(str(getattr(tool, "name", "")) for tool in tools if _is_mutable(tool))
    required_tools = sorted(set(profile["mutationGate"].get("requiredGovernanceTools") or []))
    missing_required = sorted(set(required_tools) - set(names))
    forbidden = sorted(set(profile.get("forbiddenToolNames") or []) & set(names))
    missing_output_schema = sorted(
        str(getattr(tool, "name", ""))
        for tool in tools
        if not isinstance(getattr(tool, "output_schema", None), dict)
        or not getattr(tool, "output_schema", None)
    )
    unenforced = sorted(set(mutable) - set(_ENFORCED_TOOL_NAMES)) if _ENFORCEMENT_INSTALLED else mutable
    findings: list[dict[str, Any]] = []
    if registry.truncated:
        findings.append({"severity": "P0", "family": "MCP_TOOL_REGISTRY_TRUNCATED"})
    if missing_required:
        findings.append(
            {
                "severity": "P0",
                "family": "OPERATING_PROFILE_REQUIRED_TOOL_MISSING",
                "tools": missing_required,
            }
        )
    if forbidden:
        findings.append(
            {
                "severity": "P0",
                "family": "OPERATING_PROFILE_FORBIDDEN_TOOL_REGISTERED",
                "tools": forbidden,
            }
        )
    if missing_output_schema:
        findings.append(
            {
                "severity": "P0",
                "family": "OPERATING_PROFILE_OUTPUT_SCHEMA_MISSING",
                "tools": missing_output_schema,
            }
        )
    if not _ENFORCEMENT_INSTALLED:
        findings.append({"severity": "P0", "family": "OPERATING_PROFILE_MUTATION_GATE_NOT_INSTALLED"})
    elif unenforced:
        findings.append(
            {
                "severity": "P0",
                "family": "OPERATING_PROFILE_MUTABLE_TOOL_UNENFORCED",
                "tools": unenforced,
            }
        )
    ok = not findings
    persistence = profile.get("persistence") if isinstance(profile.get("persistence"), dict) else {}
    return OperatingProfileStatus(
        schemaVersion="sovereign.mcp-operating-profile-status.v1",
        ok=ok,
        status="OPERATING_PROFILE_ENFORCED" if ok else "OPERATING_PROFILE_BLOCKED",
        profileId=str(profile["profileId"]),
        profileVersion=str(profile["profileVersion"]),
        profileSha256=profile_sha256,
        registrySnapshotSha256=registry.registrySnapshotSha256,
        toolCount=registry.toolCount,
        mutableToolCount=len(mutable),
        enforcementInstalled=_ENFORCEMENT_INSTALLED,
        enforcedToolCount=len(_ENFORCED_TOOL_NAMES),
        requiredGovernanceTools=required_tools,
        missingGovernanceTools=missing_required,
        forbiddenToolsPresent=forbidden,
        toolsWithoutOutputSchema=missing_output_schema,
        unenforcedMutableTools=unenforced,
        invariants={
            "failClosed": True,
            "automaticMutationGate": True,
            "naturalLanguageUnderstanding": "online_llm_only",
            "automaticFreeToPaidFallback": False,
            "automaticPaidToFreeFallback": False,
            "successRequiresAuthoritativeReadback": True,
            "learningRequiresProvenRuntimeOutcome": True,
            "protectedValuesAcceptedByMcpArguments": False,
        },
        findings=findings,
        paths={
            "profile": str(persistence.get("authoritativeProfilePath") or ""),
            "skill": str(persistence.get("skillPath") or ""),
            "handoff": str(persistence.get("handoffPath") or ""),
        },
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
    )



def sovereign_operating_profile_status() -> OperatingProfileStatus:
    """Use this when the persistent mission-first operating contract and automatic mutation gate must be proven live."""
    return _status_payload()



def sovereign_mission_preflight(
    mission_summary: Annotated[str, Field(min_length=3, max_length=2000)],
    required_capabilities: Annotated[
        list[operational_governance_tools.Capability],
        Field(min_length=1, max_length=12),
    ],
    allowed_effects: Annotated[
        list[operational_governance_tools.EffectClass],
        Field(min_length=1, max_length=3),
    ] = ["read"],
    required_evidence: Annotated[list[str], Field(max_length=32)] = [],
    preferred_tools: Annotated[list[str], Field(max_length=32)] = [],
    max_nodes: Annotated[int, Field(ge=1, le=16)] = 8,
) -> MissionPreflightResult:
    """Use this before multi-step or mutating work to route, compile and validate a non-executing live-registry toolchain."""
    status = _status_payload()
    if not status.ok:
        return MissionPreflightResult(
            schemaVersion="sovereign.mission-preflight.v1",
            ok=False,
            status="MISSION_PREFLIGHT_BLOCKED_BY_OPERATING_PROFILE",
            missionSummary=mission_summary,
            profileSha256=status.profileSha256,
            registrySnapshotSha256=status.registrySnapshotSha256,
            selectedTools=[],
            route={},
            proposal={},
            validation={},
            findings=list(status.findings),
            nextActions=["restore the operating profile and mutation-gate invariants before planning work"],
            mutationPerformed=False,
            runtimeVerified=True,
            secretValuesReturned=False,
            truthNotice="No mission plan is trusted while the persistent operating contract is blocked.",
        )
    route = operational_governance_tools.tool_recommend_for_mission(
        mission_summary=mission_summary,
        required_capabilities=required_capabilities,
        allowed_effects=allowed_effects,
        required_evidence=required_evidence,
        excluded_tools=[],
        max_tools=max_nodes,
    )
    proposal = toolchain_composition.mcp_toolchain_compile(
        mission_summary=mission_summary,
        required_capabilities=required_capabilities,
        desired_end_state=toolchain_composition.SemanticType(
            category="orchestration",
            data_type="MissionEvidenceResult",
            schema_ref="sovereign://mcp/mission-evidence-result/v1",
            metadata={"authoritativeReadbackRequired": True},
        ),
        allowed_effects=allowed_effects,
        required_evidence=required_evidence,
        preferred_tools=preferred_tools,
        max_nodes=max_nodes,
    )
    validation = toolchain_composition.mcp_toolchain_validate(proposal.proposal.initial_pipeline)
    selected = [
        str(item.get("name") or "")
        for item in route.evidence.get("selectedTools", [])
        if isinstance(item, dict) and item.get("name")
    ]
    findings = list(route.findings) + list(proposal.findings) + list(validation.findings)
    ok = bool(route.ok and proposal.ok and validation.ok and not any(item.get("severity") == "P0" for item in findings))
    return MissionPreflightResult(
        schemaVersion="sovereign.mission-preflight.v1",
        ok=ok,
        status="MISSION_PREFLIGHT_VALID" if ok else "MISSION_PREFLIGHT_BLOCKED",
        missionSummary=mission_summary,
        profileSha256=status.profileSha256,
        registrySnapshotSha256=validation.registrySnapshotSha256,
        selectedTools=selected,
        route=asdict(route),
        proposal=proposal.model_dump(mode="json"),
        validation=validation.model_dump(mode="json"),
        findings=findings,
        nextActions=(
            [
                "bind exact non-secret runtime context and evidence for the first node",
                "execute no node automatically",
                "verify each effect through authoritative readback before advancing",
            ]
            if ok
            else ["repair the preflight findings and compile against the fresh live registry again"]
        ),
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
        truthNotice=(
            "The online model supplies structured mission meaning. The runtime only selects registered contracts, "
            "compiles a non-executing chain and validates it against the live registry."
        ),
    )



def _contains_secret_shaped_value(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)
    if isinstance(value, dict):
        return any(_contains_secret_shaped_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_secret_shaped_value(item) for item in value)
    return False



def _validate_invocation_arguments(tool_name: str, effect: str, parameters: dict[str, Any], kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    properties = parameters.get("properties") if isinstance(parameters, dict) else {}
    properties = properties if isinstance(properties, dict) else {}
    required = set(parameters.get("required") or []) if isinstance(parameters, dict) else set()
    if effect == "external-write" and "owner_approved" in properties and kwargs.get("owner_approved") is not True:
        findings.append(
            {
                "severity": "P0",
                "family": "OPERATING_PROFILE_OWNER_APPROVAL_REQUIRED",
                "tool": tool_name,
            }
        )
    for field in _EXACT_REVISION_FIELDS:
        if field not in properties:
            continue
        value = str(kwargs.get(field) or "").strip().lower()
        if not value:
            if field in required:
                findings.append(
                    {
                        "severity": "P0",
                        "family": "OPERATING_PROFILE_EXACT_REVISION_MISSING",
                        "tool": tool_name,
                        "field": field,
                    }
                )
            continue
        if not _EXACT_SHA_RE.fullmatch(value):
            findings.append(
                {
                    "severity": "P0",
                    "family": "OPERATING_PROFILE_EXACT_REVISION_INVALID",
                    "tool": tool_name,
                    "field": field,
                }
            )
    for field in _CONFIRMATION_FIELDS:
        if field not in properties:
            continue
        value = str(kwargs.get(field) or "").strip()
        if field in required and not value:
            findings.append(
                {
                    "severity": "P0",
                    "family": "OPERATING_PROFILE_CONFIRMATION_MISSING",
                    "tool": tool_name,
                    "field": field,
                }
            )
    if _contains_secret_shaped_value(kwargs):
        findings.append(
            {
                "severity": "P0",
                "family": "OPERATING_PROFILE_SECRET_SHAPED_ARGUMENT_BLOCKED",
                "tool": tool_name,
            }
        )
    return findings



def _single_toolchain_validation(tool_name: str) -> toolchain_composition.ToolChainValidationResult:
    registry_by_name, registry_hash = toolchain_composition._registry()
    contract = registry_by_name.get(tool_name)
    if contract is None:
        raise RuntimeError(f"registered mutation tool disappeared: {tool_name}")
    preconditions, postconditions = toolchain_composition._predicates_for(contract)
    input_mappings = {
        parameter: toolchain_composition.RuntimeContextMapping(
            kind="runtime_context",
            context_key=f"tool_input.{tool_name}.{parameter}",
        )
        for parameter in toolchain_composition._required_parameters(contract)
    }
    node_id = f"gate_{tool_name[:70]}"
    annotations = contract.get("annotations") or {}
    node = toolchain_composition.ToolExecutionNode(
        node_id=node_id,
        tool_id=tool_name,
        dependencies=[],
        input_mappings=input_mappings,
        preconditions=preconditions,
        postconditions=postconditions,
        effect=contract["effect"],
        is_idempotent=bool(annotations.get("idempotentHint")),
        is_destructive=bool(annotations.get("destructiveHint")),
        requires_owner_approval=contract["effect"] == "external-write",
        timeout_seconds=120,
        max_retries=0,
        contract_sha256=contract["contractSha256"],
        output_semantic_type=toolchain_composition.SemanticType(
            category=toolchain_composition._category_for(contract),
            data_type=f"{tool_name}.result",
            schema_ref=f"mcp://tool/{tool_name}/output",
            metadata={"outputSchemaSha256": _sha256(contract.get("outputSchema") or {})},
        ),
        on_failure="stop",
        drill_down_options=["inspect profile status", "inspect exact tool contract", "stop without mutation"],
    )
    chain_payload = {
        "chain_id": f"mutation-gate.{_sha256({'tool': tool_name, 'registry': registry_hash})[:20]}",
        "title": f"Mutation gate for {tool_name}",
        "target_goal": f"Validate the exact registered contract before executing {tool_name}",
        "entry_node_id": node_id,
        "nodes": {node_id: node.model_dump(mode="json")},
        "expected_output": node.output_semantic_type.model_dump(mode="json"),
        "allowed_effects": [contract["effect"]],
        "required_evidence": ["live_registry", "output_schema", "invocation_arguments"],
        "max_iterations": 1,
        "auto_execute": False,
        "registry_snapshot_sha256": registry_hash,
        "chain_sha256": "",
    }
    chain_payload["chain_sha256"] = toolchain_composition._sha256(chain_payload)
    chain = toolchain_composition.McpToolChain.model_validate(chain_payload)
    return toolchain_composition.mcp_toolchain_validate(chain)



def _gate_or_raise(tool_name: str, effect: str, parameters: dict[str, Any], kwargs: dict[str, Any]) -> None:
    status = _status_payload()
    findings = list(status.findings)
    validation: dict[str, Any] = {}
    if status.ok:
        validated = _single_toolchain_validation(tool_name)
        validation = validated.model_dump(mode="json")
        findings.extend(validated.findings)
    findings.extend(_validate_invocation_arguments(tool_name, effect, parameters, kwargs))
    if findings:
        payload = {
            "schemaVersion": "sovereign.mutation-gate-block.v1",
            "ok": False,
            "status": "MUTATION_BLOCKED_BY_OPERATING_PROFILE",
            "failureFamily": str(findings[0].get("family") or "OPERATING_PROFILE_BLOCKED"),
            "tool": tool_name,
            "effect": effect,
            "profileSha256": status.profileSha256,
            "registrySnapshotSha256": status.registrySnapshotSha256,
            "findings": findings,
            "validation": validation,
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }
        raise OperatingProfileBlocked(_canonical(payload))



def _wrap_sync(fn: Any, *, tool_name: str, effect: str, parameters: dict[str, Any]) -> Any:
    @functools.wraps(fn)
    def wrapped(**kwargs: Any) -> Any:
        _gate_or_raise(tool_name, effect, parameters, kwargs)
        return fn(**kwargs)

    setattr(wrapped, "__sovereign_operating_profile_wrapped__", True)
    return wrapped



def _wrap_async(fn: Any, *, tool_name: str, effect: str, parameters: dict[str, Any]) -> Any:
    @functools.wraps(fn)
    async def wrapped(**kwargs: Any) -> Any:
        _gate_or_raise(tool_name, effect, parameters, kwargs)
        return await fn(**kwargs)

    setattr(wrapped, "__sovereign_operating_profile_wrapped__", True)
    return wrapped



def install_enforcement(mcp: Any) -> EnforcementInstallationResult:
    global _MCP, _ENFORCEMENT_INSTALLED, _ENFORCED_TOOL_NAMES
    _MCP = mcp
    enforced: list[str] = []
    for tool in mcp._tool_manager.list_tools():
        if not _is_mutable(tool):
            continue
        if getattr(tool.fn, "__sovereign_operating_profile_wrapped__", False):
            enforced.append(str(tool.name))
            continue
        tool_name = str(tool.name)
        effect = _effect(tool)
        parameters = dict(getattr(tool, "parameters", {}) or {})
        tool.fn = (
            _wrap_async(tool.fn, tool_name=tool_name, effect=effect, parameters=parameters)
            if bool(tool.is_async)
            else _wrap_sync(tool.fn, tool_name=tool_name, effect=effect, parameters=parameters)
        )
        tool.meta = {
            **(tool.meta or {}),
            "sovereign/operatingProfileEnforced": True,
            "sovereign/operatingProfileEffect": effect,
        }
        enforced.append(tool_name)
    _ENFORCED_TOOL_NAMES = tuple(sorted(set(enforced)))
    _ENFORCEMENT_INSTALLED = True
    status = _status_payload()
    return EnforcementInstallationResult(
        schemaVersion="sovereign.mcp-operating-profile-enforcement-install.v1",
        ok=status.ok,
        status="OPERATING_PROFILE_ENFORCEMENT_INSTALLED" if status.ok else "OPERATING_PROFILE_ENFORCEMENT_BLOCKED",
        profileSha256=status.profileSha256,
        registrySnapshotSha256=status.registrySnapshotSha256,
        mutableToolCount=status.mutableToolCount,
        enforcedToolCount=status.enforcedToolCount,
        enforcedTools=list(_ENFORCED_TOOL_NAMES),
        findings=list(status.findings),
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
    )



def register(mcp: Any) -> None:
    global _MCP, _REGISTERED
    _MCP = mcp
    if _REGISTERED:
        return
    mcp.tool(annotations=LOCAL_READ_ONLY)(sovereign_operating_profile_status)
    mcp.tool(annotations=LOCAL_READ_ONLY)(sovereign_mission_preflight)
    _REGISTERED = True
