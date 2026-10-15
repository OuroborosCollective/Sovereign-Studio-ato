from __future__ import annotations

import os
import uuid
from typing import Any, Callable
from urllib.parse import urlparse

import requests

# This module is intentionally a transport adapter, not a second authority.
# Aurion remains the source of truth for OAuth claims, persisted admin role,
# tool schemas, scope checks, Plan->Confirm contracts, and all mutations.

AURION_ADMIN_MCP_PROTOCOL = "aurion.admin-mcp.v1"
AURION_ADMIN_MCP_DEFAULT_RESOURCE_URL = "https://arelogic.space/admin-mcp"
AURION_ADMIN_MCP_PATH = "/admin-mcp"

READ_SCOPE = "aurion.admin.read"
ASSET_WRITE_SCOPE = "aurion.admin.assets.write"
AUTHORING_WRITE_SCOPE = "aurion.admin.authoring.write"
ALL_SCOPES = frozenset({READ_SCOPE, ASSET_WRITE_SCOPE, AUTHORING_WRITE_SCOPE})
AURION_MAX_GLB_BASE64_CHARS = 33_554_440
AURION_SOURCE_FILE_SHA256 = {
    "AURION_ADMIN_MCP_CONTRACT.md": "183b55385593b3e17753f14a74fec6265916840b774e53b7003a9e6e80fcece4",
    "server/adminMcp.ts": "e818fa21b60b1cd6211c13f9275003e457d451dba0e14472c7585ce0995edcad",
    "server/adminMcpProtocol.ts": "173610cbc1705e3d1ad6f1e390df4a38a1c1202e0652e7d0027274c3beba4d5c",
    "shared/aurionAuthoringContract.ts": "eebcb79b0eaca0daaefaf7fa6205121ba545c9b9afaad2edfe1a3ca95c5ae432",
}

_CORE_READ_TOOLS = (
    "aurion_admin_get_capabilities",
    "aurion_admin_get_world_overview",
    "aurion_admin_wolfram_status",
    "aurion_admin_os3a_source",
    "aurion_admin_os3a_search",
    "aurion_admin_os3a_gap_scan",
    "aurion_quest_status",
    "aurion_quest_template_list",
    "aurion_quest_template_get",
    "aurion_quest_validate",
    "aurion_quest_instance_explain",
    "aurion_quest_replay",
    "aurion_context_inspect_capsule",
    "aurion_context_replay_capsule",
    "aurion_context_expand_sources",
    "aurion_context_get_episode",
    "aurion_context_eval_summary",
    "aurion_causality_status",
    "aurion_assurance_status",
    "aurion_tick_receipt_get",
    "aurion_tick_explain",
    "aurion_tick_replay",
    "aurion_replay_range",
    "aurion_runtime_identity",
    "aurion_recovery_plan",
    "aurion_donor_ledger",
    "aurion_donor_capability_explain",
)
_WOLFRAM_TOOLS = (
    "aurion_admin_wolfram_compute",
    "aurion_admin_wolfram_hints",
    "aurion_admin_wolfram_alpha_results",
    "aurion_admin_wolfram_alpha_context",
    "aurion_admin_wolfram_canary",
)
_ASSET_WRITE_TOOLS = (
    "aurion_admin_glb_plan",
    "aurion_admin_glb_import",
    "aurion_admin_glb_catalog",
    "aurion_admin_glb_assign",
    "aurion_admin_os3a_plan",
    "aurion_admin_os3a_apply",
    "aurion_admin_os3a_gap_reconcile",
    "aurion_admin_gds_status",
    "aurion_admin_gds_plan",
    "aurion_admin_gds_apply",
    "aurion_admin_named_npc_visual_plan",
    "aurion_admin_named_npc_visual_apply",
)
AURION_TOOL_HANDLER_MAP: dict[str, str] = {
    "aurion_admin_get_capabilities": "server/adminMcp.ts::adminMcpCapabilities(actor.scopes, { wolframConfigured })",
    "aurion_admin_get_world_overview": "server/adminMcp.ts::db.getGlobalWorldAdminReadModel()",
    "aurion_admin_wolfram_status": "server/adminMcp.ts::wolframCagConfigurationStatus()",
    "aurion_admin_wolfram_compute": "server/wolframCag.ts::requireWolframCagClient().languageCompute(input)",
    "aurion_admin_wolfram_hints": "server/wolframCag.ts::requireWolframCagClient().languageHints(input)",
    "aurion_admin_wolfram_alpha_results": "server/wolframCag.ts::requireWolframCagClient().alphaResults(input)",
    "aurion_admin_wolfram_alpha_context": "server/wolframCag.ts::requireWolframCagClient().alphaContext(input)",
    "aurion_admin_wolfram_canary": "server/wolframCag.ts::runAurionWolframCagCanary(wolfram)",
    "aurion_admin_os3a_source": "server/openSource3dFallback.ts::openSource3dFallbackSource()",
    "aurion_admin_os3a_search": "server/openSource3dFallback.ts::searchOpenSource3dFallback(input)",
    "aurion_admin_os3a_gap_scan": "server/automaticGlbFallback.ts::scanAutomaticGlbFallback()",
    "aurion_admin_glb_plan": "server/glbImportPlan.ts::buildGlbImportPlan(input.contentBase64)",
    "aurion_admin_glb_import": "server/glbImportStore.ts::glbImportStore().ingest(actor.userId, input)",
    "aurion_admin_glb_catalog": "server/glbImportStore.ts::glbImportStore().catalog()",
    "aurion_admin_glb_assign": "server/glbImportStore.ts::glbImportStore().assign(actor.userId, input)",
    "aurion_admin_os3a_plan": "server/openSource3dFallback.ts::planOpenSource3dFallback(input)",
    "aurion_admin_os3a_apply": "server/openSource3dFallback.ts::applyOpenSource3dFallback(actor.userId, input)",
    "aurion_admin_os3a_gap_reconcile": "server/automaticGlbFallback.ts::reconcileAutomaticGlbFallback(actor.userId, input)",
    "aurion_admin_gds_status": "server/gameDevelopmentStudioRuntime.ts::resolveGameDevelopmentStudioRuntimeReadback()",
    "aurion_admin_gds_plan": "server/gameDevelopmentStudioProduction.ts::planGameDevelopmentStudioLiveAsset(input)",
    "aurion_admin_gds_apply": "server/gameDevelopmentStudioProduction.ts::applyGameDevelopmentStudioLiveAsset(actor.userId, input.asset, input.expectedPlanSha256)",
    "aurion_admin_named_npc_visual_plan": "server/namedNpcVisualAssignment.ts::planNamedNpcVisual(input)",
    "aurion_admin_named_npc_visual_apply": "server/namedNpcVisualAssignment.ts::applyNamedNpcVisual(actor.userId, input.binding, input.expectedPlanHash)",
    "aurion_admin_world_design_read": "server/aurionAuthoringPersistence.ts::readActiveWorldDesign()",
    "aurion_admin_world_design_plan": "server/aurionAuthoringPersistence.ts::planWorldDesign(input)",
    "aurion_admin_world_design_apply": "server/aurionAuthoringPersistence.ts::applyWorldDesign(actor.userId, input.draft, input.expectedPlanHash)",
    "aurion_admin_dungeon_design_read": "server/aurionAuthoringPersistence.ts::readActiveDungeonDesigns()",
    "aurion_admin_dungeon_design_plan": "server/aurionAuthoringPersistence.ts::planDungeonDesign(input)",
    "aurion_admin_dungeon_design_apply": "server/aurionAuthoringPersistence.ts::applyDungeonDesign(actor.userId, input.draft, input.expectedPlanHash)",
    "aurion_quest_status": "server/questCompiler/adminService.ts::questService.getStatus()",
    "aurion_quest_template_list": "server/questCompiler/adminService.ts::questService.getTemplates()",
    "aurion_quest_template_get": "server/adminMcp.ts::questService.getTemplates() -> select templateId/version",
    "aurion_quest_validate": "server/adminMcp.ts::AurionQuestTemplateSchema.safeParse + server/questCompiler/validator.ts::validateQuestGraph",
    "aurion_quest_instance_explain": "server/adminMcp.ts::questService.listInstances() -> select instanceId",
    "aurion_quest_replay": "server/questCompiler/adminService.ts::questService.replayInstance(instanceId)",
    "aurion_quest_draft_propose": "server/questCompiler/adminService.ts::questService.createDraftProposal(...)",
    "aurion_quest_publish_plan": "server/questCompiler/adminService.ts::questService.planPublishProposal(proposalId)",
    "aurion_quest_publish": "server/questCompiler/adminService.ts::questService.publishProposal(actor.userId, proposalId, expectedPlanHash)",
    "aurion_context_inspect_capsule": "server/worldContext/service.ts::aurionWorldContextService.getCapsule(capsuleId)",
    "aurion_context_replay_capsule": "server/worldContext/service.ts::aurionWorldContextService.replayCapsule({ capsule, sources: [] })",
    "aurion_context_expand_sources": "server/worldContext/service.ts::aurionWorldContextService.expandSources(input)",
    "aurion_context_get_episode": "server/worldContext/service.ts::aurionWorldContextService.getEpisode(episodeId)",
    "aurion_context_eval_summary": "server/worldContext/service.ts::aurionWorldContextService.getEvaluationSummary()",
    "aurion_causality_status": "server/chatgptCausalityBridge.ts::chatGptCausalityStatus(zoneId)",
    "aurion_assurance_status": "server/chatgptCausalityBridge.ts::chatGptAssuranceStatus()",
    "aurion_tick_receipt_get": "server/chatgptCausalityBridge.ts::chatGptTickReceipt(zoneId, tick)",
    "aurion_tick_explain": "server/chatgptCausalityBridge.ts::chatGptTickExplain(zoneId, tick)",
    "aurion_tick_replay": "server/chatgptCausalityBridge.ts::chatGptTickReplay(zoneId, tick)",
    "aurion_replay_range": "server/chatgptCausalityBridge.ts::chatGptReplayRange(zoneId, fromTick, toTick)",
    "aurion_runtime_identity": "server/chatgptCausalityBridge.ts::chatGptRuntimeIdentity()",
    "aurion_recovery_plan": "server/chatgptCausalityBridge.ts::chatGptRecoveryPlan(zoneId)",
    "aurion_donor_ledger": "server/chatgptCausalityBridge.ts::chatGptDonorLedger()",
    "aurion_donor_capability_explain": "server/chatgptCausalityBridge.ts::chatGptDonorCapability(capabilityId)",
}

_AUTHORING_TOOLS = (
    "aurion_admin_world_design_read",
    "aurion_admin_world_design_plan",
    "aurion_admin_world_design_apply",
    "aurion_admin_dungeon_design_read",
    "aurion_admin_dungeon_design_plan",
    "aurion_admin_dungeon_design_apply",
    "aurion_quest_draft_propose",
    "aurion_quest_publish_plan",
    "aurion_quest_publish",
)
ALL_AURION_ADMIN_TOOLS = (
    "aurion_admin_get_capabilities",
    "aurion_admin_get_world_overview",
    "aurion_admin_wolfram_status",
    "aurion_admin_wolfram_compute",
    "aurion_admin_wolfram_hints",
    "aurion_admin_wolfram_alpha_results",
    "aurion_admin_wolfram_alpha_context",
    "aurion_admin_wolfram_canary",
    "aurion_admin_os3a_source",
    "aurion_admin_os3a_search",
    "aurion_admin_os3a_gap_scan",
    "aurion_admin_glb_plan",
    "aurion_admin_glb_import",
    "aurion_admin_glb_catalog",
    "aurion_admin_glb_assign",
    "aurion_admin_os3a_plan",
    "aurion_admin_os3a_apply",
    "aurion_admin_os3a_gap_reconcile",
    "aurion_admin_gds_status",
    "aurion_admin_gds_plan",
    "aurion_admin_gds_apply",
    "aurion_admin_named_npc_visual_plan",
    "aurion_admin_named_npc_visual_apply",
    "aurion_admin_world_design_read",
    "aurion_admin_world_design_plan",
    "aurion_admin_world_design_apply",
    "aurion_admin_dungeon_design_read",
    "aurion_admin_dungeon_design_plan",
    "aurion_admin_dungeon_design_apply",
    "aurion_quest_status",
    "aurion_quest_template_list",
    "aurion_quest_template_get",
    "aurion_quest_validate",
    "aurion_quest_instance_explain",
    "aurion_quest_replay",
    "aurion_quest_draft_propose",
    "aurion_quest_publish_plan",
    "aurion_quest_publish",
    "aurion_context_inspect_capsule",
    "aurion_context_replay_capsule",
    "aurion_context_expand_sources",
    "aurion_context_get_episode",
    "aurion_context_eval_summary",
    "aurion_causality_status",
    "aurion_assurance_status",
    "aurion_tick_receipt_get",
    "aurion_tick_explain",
    "aurion_tick_replay",
    "aurion_replay_range",
    "aurion_runtime_identity",
    "aurion_recovery_plan",
    "aurion_donor_ledger",
    "aurion_donor_capability_explain",
)

TOOL_DESCRIPTIONS: dict[str, str] = {
    "aurion_admin_get_capabilities": "Lists the current safe capabilities and boundaries.",
    "aurion_admin_get_world_overview": "Reads the confirmed global world descriptor without advancing an epoch.",
    "aurion_admin_wolfram_status": "Reports secret-free Wolfram CAG runtime configuration without making a provider request.",
    "aurion_admin_os3a_source": "Read the pinned local OS3A CC0 fallback source identity; no upstream call or mutation.",
    "aurion_admin_os3a_search": "Search the pinned local OS3A metadata snapshot; candidates remain unclassified until byte-plan.",
    "aurion_admin_os3a_gap_scan": "Detects missing safe visual categories and previews deterministic pinned OS3A candidates; no mutation.",
    "aurion_admin_wolfram_compute": "Evaluates bounded Wolfram Language code as external evidence only.",
    "aurion_admin_wolfram_hints": "Retrieves bounded Wolfram Language hints as external evidence only.",
    "aurion_admin_wolfram_alpha_results": "Retrieves bounded Wolfram Alpha results as external evidence only.",
    "aurion_admin_wolfram_alpha_context": "Retrieves bounded Wolfram Alpha factual context.",
    "aurion_admin_wolfram_canary": "Runs the fixed exact Wolfram CAG computation canary.",
    "aurion_admin_glb_plan": "Validate supplied GLB bytes and derive the versioned target plan.",
    "aurion_admin_glb_import": "Persist one separately authorized visual GLB; no gameplay mutation.",
    "aurion_admin_glb_catalog": "Read approved persistent GLB catalog and visual assignments.",
    "aurion_admin_glb_assign": "Compare-and-set one visual assignment; no gameplay semantics.",
    "aurion_admin_os3a_plan": "Fetch one SHA-pinned candidate, apply Aurion budgets and run GDS inspect/validate; no live write.",
    "aurion_admin_os3a_apply": "Admit one exact OS3A plan through GDS and persist source provenance after explicit confirmation.",
    "aurion_admin_os3a_gap_reconcile": "Batch-fills only missing reversible visual fallback categories after exact batch confirmation; never replaces existing assignments.",
    "aurion_admin_gds_status": "Read the pinned server-side Game Development Studio runtime status.",
    "aurion_admin_gds_plan": "Run server-side GDS inspect/validate and return a human-confirmed plan.",
    "aurion_admin_gds_apply": "Run GDS package/verify/vendor and ingest verified bytes after exact plan confirmation.",
    "aurion_admin_named_npc_visual_plan": "Plan one approved named-NPC visual binding.",
    "aurion_admin_named_npc_visual_apply": "Apply one named-NPC visual binding after exact plan confirmation.",
    "aurion_admin_world_design_read": "Read the active Aurion world-design manifest.",
    "aurion_admin_world_design_plan": "Validate and hash one world-design draft.",
    "aurion_admin_world_design_apply": "Apply one exact world-design plan after explicit confirmation.",
    "aurion_admin_dungeon_design_read": "Read active authored Aurion dungeons.",
    "aurion_admin_dungeon_design_plan": "Validate and hash one dungeon-design draft.",
    "aurion_admin_dungeon_design_apply": "Publish one exact dungeon-design plan after explicit confirmation.",
    "aurion_quest_status": "Reads compiler version, schema, template-set hash and metrics.",
    "aurion_quest_template_list": "Lists canonical active quest templates.",
    "aurion_quest_template_get": "Reads a quest template by ID/version.",
    "aurion_quest_validate": "Fail-closed validation without storing it.",
    "aurion_quest_instance_explain": "Reads objective progress and hash chain for a live quest instance.",
    "aurion_quest_replay": "Re-evaluates deterministic quest composition.",
    "aurion_quest_draft_propose": "Persist a bounded quest draft proposal only; no publish.",
    "aurion_quest_publish_plan": "Validate one quest proposal and return its exact publish plan.",
    "aurion_quest_publish": "Publish one quest template only for the exact confirmed plan.",
    "aurion_context_inspect_capsule": "Reads immutable context-capsule evidence.",
    "aurion_context_replay_capsule": "Re-executes context assembly and reports divergence.",
    "aurion_context_expand_sources": "Reversibly reads requested canonical sources from a capsule receipt.",
    "aurion_context_get_episode": "Reads an immutable structured historical episode.",
    "aurion_context_eval_summary": "Reads the standard context evaluation summary.",
    "aurion_causality_status": "Reads causal chain, persistence and replay coverage. Never mutates gameplay.",
    "aurion_assurance_status": "Reads sealed assurance observations and a recovery plan. It cannot mutate gameplay or execute recovery.",
    "aurion_tick_receipt_get": "Reads an in-memory or persisted causal tick receipt.",
    "aurion_tick_explain": "Explains only evidence actually available for one tick.",
    "aurion_tick_replay": "Runs a side-effect-free replay.",
    "aurion_replay_range": "Runs bounded side-effect-free replay over at most 250 ticks.",
    "aurion_runtime_identity": "Reads runtime identity together with provenance status.",
    "aurion_recovery_plan": "Returns a reconciled checkpoint candidate with mutationAuthority=none.",
    "aurion_donor_ledger": "Reads the WASD/AX1 donor migration ledger.",
    "aurion_donor_capability_explain": "Reads one donor capability record without upgrading its evidence status.",
}

def _hex64() -> dict[str, Any]:
    return {"type": "string", "pattern": r"^[a-f0-9]{64}$"}

def _string(min_length: int | None = None, max_length: int | None = None, pattern: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if min_length is not None:
        schema["minLength"] = min_length
    if max_length is not None:
        schema["maxLength"] = max_length
    if pattern is not None:
        schema["pattern"] = pattern
    return schema

def _integer(minimum: int | None = None, maximum: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer"}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return schema

def _object(properties: dict[str, Any], required: list[str] | None = None, *, additional: bool = False) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": additional,
    }

def _array(items: dict[str, Any], minimum: int | None = None, maximum: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if minimum is not None:
        schema["minItems"] = minimum
    if maximum is not None:
        schema["maxItems"] = maximum
    return schema

def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    copy = dict(schema)
    copy["type"] = [str(schema.get("type", "object")), "null"]
    return copy

_CANONICAL_ID = _string(3, 96, r"^[a-z][a-z0-9._:-]{2,95}$")
_ASSET_ID = _string(8, 64)
_SHA256 = _hex64()
_PLAN_PURPOSE = {"type": "string", "enum": ["npc-fallback", "enemy-fallback", "world-environment", "world-nature", "player-public", "equipment"]}
_TIER = {"type": "string", "enum": ["phone", "tablet", "desktop"]}

WORLD_PLACEMENT = _object({
    "placementKey": _CANONICAL_ID,
    "assetId": _string(8, 96, r"^glb_[a-z0-9._:-]{4,91}$"),
    "chunkX": _integer(-100000, 100000),
    "chunkZ": _integer(-100000, 100000),
    "xMm": _integer(0, 63999),
    "zMm": _integer(0, 63999),
    "rotationQuarterTurns": {"type": "integer", "enum": [0, 1, 2, 3]},
    "scalePermille": {**_integer(250, 4000), "default": 1000},
}, ["placementKey", "assetId", "chunkX", "chunkZ", "xMm", "zMm", "rotationQuarterTurns"], additional=False)

WORLD_DESIGN_DRAFT = _object({
    "schemaVersion": {"type": "string", "const": "aurion.world-design.v1", "default": "aurion.world-design.v1"},
    "designKey": _CANONICAL_ID,
    "version": _integer(1, 1000000),
    "title": _string(3, 160),
    "expectedCatalogRevision": _SHA256,
    "placements": _array(WORLD_PLACEMENT, 1, 256),
}, ["designKey", "version", "title", "expectedCatalogRevision", "placements"], additional=False)

DUNGEON_OBJECTIVE = _object({
    "kind": {"type": "string", "enum": ["defeat", "interact", "collect", "survive", "reach"]},
    "targetId": _CANONICAL_ID,
    "targetValue": _integer(1, 100000),
    "description": _string(3, 240),
}, ["kind", "targetId", "targetValue", "description"])

DUNGEON_ROOM = _object({
    "roomKey": _CANONICAL_ID,
    "kind": {"type": "string", "enum": ["entrance", "combat", "puzzle", "objective", "treasure", "rest", "boss", "exit"]},
    "title": _string(2, 120),
    "xMm": _integer(-1000000, 1000000),
    "zMm": _integer(-1000000, 1000000),
    "assetId": {**_nullable(_string(8, 96, r"^glb_[a-z0-9._:-]{4,91}$")), "default": None},
    "objective": {**_nullable(DUNGEON_OBJECTIVE), "default": None},
}, ["roomKey", "kind", "title", "xMm", "zMm"])

DUNGEON_CONNECTION = _object({
    "fromRoomKey": _CANONICAL_ID,
    "toRoomKey": _CANONICAL_ID,
    "label": {**_nullable(_string(1, 80)), "default": None},
}, ["fromRoomKey", "toRoomKey"])

DUNGEON_BOSS = _object({
    "bossId": _CANONICAL_ID,
    "label": _string(2, 120),
    "roomKey": _CANONICAL_ID,
    "assetId": {**_nullable(_string(8, 96, r"^glb_[a-z0-9._:-]{4,91}$")), "default": None},
}, ["bossId", "label", "roomKey"])

DUNGEON_DESIGN_DRAFT = _object({
    "schemaVersion": {"type": "string", "const": "aurion.dungeon-design.v1", "default": "aurion.dungeon-design.v1"},
    "dungeonId": _string(11, 90, r"^dungeon_[a-z0-9][a-z0-9_]{2,79}$"),
    "version": _integer(1, 1000000),
    "label": _string(3, 160),
    "zone": _CANONICAL_ID,
    "expectedCatalogRevision": _SHA256,
    "rooms": _array(DUNGEON_ROOM, 4, 9),
    "connections": _array(DUNGEON_CONNECTION, 3, 24),
    "bosses": _array(DUNGEON_BOSS, 2, 4),
    "partyCapabilities": {
        "type": "array",
        "default": [1, 1, 3],
        "prefixItems": [
            {"type": "integer", "const": 1},
            {"type": "integer", "const": 1},
            {"type": "integer", "const": 3},
        ],
        "minItems": 3,
        "maxItems": 3,
    },
}, ["dungeonId", "version", "label", "zone", "expectedCatalogRevision", "rooms", "connections", "bosses"])

GDS_ASSET = _object({
    "displayName": _string(3, 120, r"^(?!.*[<>]).*$"),
    "fileName": _string(5, 120, r"(?i)^[A-Za-z0-9][A-Za-z0-9._ -]*\.glb$"),
    "contentBase64": _string(16, AURION_MAX_GLB_BASE64_CHARS),
    "purpose": _PLAN_PURPOSE,
    "packageVersion": {**_string(None, None, r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$"), "default": "1.0.0"},
    "rightsBasis": {"type": "string", "enum": ["owner-created-private", "licensed"], "default": "licensed"},
    "license": _string(1, 128),
    "designWorkOrderSha256": _SHA256,
}, ["displayName", "fileName", "contentBase64", "purpose"])

CONTRACTS: dict[str, dict[str, Any]] = {}

def _empty() -> dict[str, Any]:
    return _object({})

for name in (
    "aurion_admin_get_capabilities",
    "aurion_admin_get_world_overview",
    "aurion_admin_wolfram_status",
    "aurion_admin_wolfram_canary",
    "aurion_admin_os3a_source",
    "aurion_admin_os3a_gap_scan",
    "aurion_admin_glb_catalog",
    "aurion_admin_gds_status",
    "aurion_admin_world_design_read",
    "aurion_admin_dungeon_design_read",
    "aurion_quest_status",
    "aurion_quest_template_list",
    "aurion_quest_publish_plan",  # overwritten below with required proposalId
    "aurion_context_eval_summary",
    "aurion_causality_status",  # overwritten below with optional zoneId
    "aurion_assurance_status",
    "aurion_runtime_identity",
    "aurion_donor_ledger",
    "aurion_admin_named_npc_visual_plan",  # overwritten below
):
    CONTRACTS[name] = _empty()

def exposed_tool_names(scopes: frozenset[str], *, wolfram_enabled: bool) -> tuple[str, ...]:
    return tuple(
        name for name in ALL_AURION_ADMIN_TOOLS
        if required_scope_for_tool(name) in scopes
        and (wolfram_enabled or name not in _WOLFRAM_TOOLS)
    )

CONTRACTS.update({
    "aurion_causality_status": _object({"zoneId": _string(1)}, additional=False),
    "aurion_tick_receipt_get": _object({"zoneId": _string(1), "tick": _integer(0)}, ["zoneId", "tick"]),
    "aurion_tick_explain": _object({"zoneId": _string(1), "tick": _integer(0)}, ["zoneId", "tick"]),
    "aurion_tick_replay": _object({"zoneId": _string(1), "tick": _integer(0)}, ["zoneId", "tick"]),
    "aurion_replay_range": _object({"zoneId": _string(1), "fromTick": _integer(0), "toTick": _integer(0)}, ["zoneId", "fromTick", "toTick"]),
    "aurion_recovery_plan": _object({"zoneId": _string(1)}, ["zoneId"]),
    "aurion_donor_capability_explain": _object({"capabilityId": _string(1)}, ["capabilityId"]),
    "aurion_admin_os3a_search": _object({"query": _string(2, 120), "tier": {**_TIER, "default": "phone"}, "limit": {**_integer(1, 24), "default": 12}}, ["query"]),
    "aurion_admin_wolfram_compute": _object({"code": _string(1, 20000), "timeConstraint": _integer(1, 60), "maxChars": _integer(1, 20000)}, ["code"]),
    "aurion_admin_wolfram_hints": _object({"context": _string(1, 20000)}, ["context"]),
    "aurion_admin_wolfram_alpha_results": _object({"input": _string(1, 20000)}, ["input"]),
    "aurion_admin_wolfram_alpha_context": _object({"context": _string(1, 20000), "count": _integer(1, 10)}, ["context"]),
    "aurion_admin_glb_plan": _object({"contentBase64": _string(16, AURION_MAX_GLB_BASE64_CHARS)}, ["contentBase64"]),
    "aurion_admin_glb_import": _object({"displayName": _string(3, 120), "contentBase64": _string(16, AURION_MAX_GLB_BASE64_CHARS), "expectedPlanSha256": _SHA256}, ["displayName", "contentBase64", "expectedPlanSha256"]),
    "aurion_admin_glb_assign": _object({
        "assetId": _string(8, 64),
        "targetType": {"type": "string", "enum": ["character", "enemy", "weapon", "armor", "arena"]},
        "targetKey": _string(2, 120),
        "expectedActiveAssetId": _nullable(_string(8, 64)),
    }, ["assetId", "targetType", "targetKey", "expectedActiveAssetId"]),
    "aurion_admin_os3a_plan": _object({"sourceAssetId": _string(3, 96, r"^[a-z0-9][a-z0-9-]{2,95}$"), "purpose": _PLAN_PURPOSE, "tier": {**_TIER, "default": "phone"}}, ["sourceAssetId", "purpose"]),
    "aurion_admin_os3a_apply": _object({"sourceAssetId": _string(3, 96, r"^[a-z0-9][a-z0-9-]{2,95}$"), "purpose": _PLAN_PURPOSE, "tier": {**_TIER, "default": "phone"}, "expectedPlanSha256": _SHA256, "confirmation": {"type": "string", "const": "ADMIT_OS3A_FALLBACK"}}, ["sourceAssetId", "purpose", "expectedPlanSha256", "confirmation"]),
    "aurion_admin_os3a_gap_reconcile": _object({"confirmation": {"type": "string", "const": "RECONCILE_MISSING_VISUAL_FALLBACKS"}}, ["confirmation"]),
    "aurion_admin_gds_plan": GDS_ASSET,
    "aurion_admin_gds_apply": _object({"asset": GDS_ASSET, "expectedPlanSha256": _SHA256, "confirmation": {"type": "string", "const": "APPLY_TO_LIVE_AURION"}}, ["asset", "expectedPlanSha256", "confirmation"]),
    "aurion_admin_named_npc_visual_plan": _object({"assetId": _string(8, 64), "npcId": _string(1, 96, r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")}, ["assetId", "npcId"]),
    "aurion_admin_named_npc_visual_apply": _object({
        "binding": _object({"assetId": _string(8, 64), "npcId": _string(1, 96, r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")}, ["assetId", "npcId"]),
        "expectedPlanHash": _SHA256,
        "confirmation": {"type": "string", "const": "APPLY_NAMED_NPC_VISUAL"},
    }, ["binding", "expectedPlanHash", "confirmation"]),
    "aurion_admin_world_design_plan": WORLD_DESIGN_DRAFT,
    "aurion_admin_world_design_apply": _object({"draft": WORLD_DESIGN_DRAFT, "expectedPlanHash": _SHA256, "confirmation": {"type": "string", "const": "APPLY_WORLD_DESIGN"}}, ["draft", "expectedPlanHash", "confirmation"]),
    "aurion_admin_dungeon_design_plan": DUNGEON_DESIGN_DRAFT,
    "aurion_admin_dungeon_design_apply": _object({"draft": DUNGEON_DESIGN_DRAFT, "expectedPlanHash": _SHA256, "confirmation": {"type": "string", "const": "PUBLISH_DUNGEON"}}, ["draft", "expectedPlanHash", "confirmation"]),
    "aurion_quest_template_get": _object({"templateId": _string(1), "version": {"type": "integer"}}),
    "aurion_quest_validate": _object({"templateJson": {"type": "string"}}, ["templateJson"]),
    "aurion_quest_instance_explain": _object({"instanceId": _string(1)}, ["instanceId"]),
    "aurion_quest_replay": _object({"instanceId": _string(1)}, ["instanceId"]),
    "aurion_quest_draft_propose": _object({"templateId": _string(3, 96), "templateVersion": _integer(1), "proposedDataJson": _string(2, 120000)}, ["templateId", "templateVersion", "proposedDataJson"]),
    "aurion_quest_publish_plan": _object({"proposalId": _string(8, 128)}, ["proposalId"]),
    "aurion_quest_publish": _object({"proposalId": _string(8, 128), "expectedPlanHash": _SHA256, "confirmation": {"type": "string", "const": "PUBLISH_QUEST_TEMPLATE"}}, ["proposalId", "expectedPlanHash", "confirmation"]),
    "aurion_context_inspect_capsule": _object({"capsuleId": {"type": "string"}}, ["capsuleId"]),
    "aurion_context_replay_capsule": _object({"capsuleId": {"type": "string"}}, ["capsuleId"]),
    "aurion_context_expand_sources": _object({"capsuleId": {"type": "string"}, "requestedSourceIds": _array({"type": "string"}), "expectedCapsuleHash": {"type": "string"}}, ["capsuleId", "requestedSourceIds", "expectedCapsuleHash"]),
    "aurion_context_get_episode": _object({"episodeId": {"type": "string"}}, ["episodeId"]),
})

# The Aurion implementation uses these tool classes:
# - read: safe evidence/read-model handlers
# - asset-write: GLB/OS3A/GDS/NPC visual handlers behind aurion.admin.assets.write
# - authoring-write: world/dungeon/quest authoring behind aurion.admin.authoring.write
# The final authority is always the existing Aurion /admin-mcp resource server.

TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "read": _CORE_READ_TOOLS,
    "wolfram": _WOLFRAM_TOOLS,
    "assets_write": _ASSET_WRITE_TOOLS,
    "authoring": _AUTHORING_TOOLS,
}

def required_scope_for_tool(tool_name: str) -> str:
    if tool_name in _ASSET_WRITE_TOOLS:
        return ASSET_WRITE_SCOPE
    if tool_name in _AUTHORING_TOOLS and tool_name not in {"aurion_admin_world_design_read", "aurion_admin_dungeon_design_read", "aurion_quest_publish_plan"}:
        return AUTHORING_WRITE_SCOPE
    return READ_SCOPE

def tool_mode(tool_name: str) -> str:
    if tool_name in {"aurion_admin_glb_import", "aurion_admin_glb_assign", "aurion_admin_os3a_apply", "aurion_admin_os3a_gap_reconcile", "aurion_admin_gds_apply", "aurion_admin_named_npc_visual_apply", "aurion_admin_world_design_apply", "aurion_admin_dungeon_design_apply", "aurion_quest_draft_propose", "aurion_quest_publish"}:
        return "write"
    return "read"

class AurionAdminMcpRuntime:
    def __init__(self, *, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def _resource_url(self) -> str:
        value = os.getenv("AURION_ADMIN_MCP_RESOURCE_URL", AURION_ADMIN_MCP_DEFAULT_RESOURCE_URL).strip()
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != "arelogic.space" or parsed.path.rstrip("/") != AURION_ADMIN_MCP_PATH:
            raise RuntimeError("AURION_ADMIN_MCP_RESOURCE_URL must be exactly the existing HTTPS arelogic.space /admin-mcp resource")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError("AURION_ADMIN_MCP_RESOURCE_URL must not contain credentials, query or fragment")
        return value.rstrip("/")

    def _token(self) -> str:
        token_file = os.getenv("AURION_ADMIN_MCP_ACCESS_TOKEN_FILE", "").strip()
        if token_file:
            try:
                token = open(token_file, "r", encoding="utf-8").read().strip()
            except OSError as exc:
                raise RuntimeError("AURION_ADMIN_ACCESS_TOKEN_FILE_UNREADABLE") from exc
            if token:
                return token
        token = os.getenv("AURION_ADMIN_MCP_ACCESS_TOKEN", "").strip()
        if not token:
            raise RuntimeError("AURION_ADMIN_ACCESS_TOKEN_MISSING")
        return token

    def _local_allowed_scopes(self) -> frozenset[str]:
        raw = os.getenv("AURION_ADMIN_MCP_SCOPES", READ_SCOPE)
        scopes = frozenset(item.strip() for item in raw.split() if item.strip())
        invalid = scopes - ALL_SCOPES
        if invalid:
            raise RuntimeError("AURION_ADMIN_MCP_SCOPES_INVALID")
        if not scopes:
            return frozenset({READ_SCOPE})
        return scopes

    def contract(self) -> dict[str, Any]:
        configured_scopes = self._local_allowed_scopes()
        tools = []
        for name in exposed_tool_names(
            configured_scopes,
            wolfram_enabled=os.getenv("AURION_ADMIN_MCP_WOLFRAM_ENABLED", "0").strip() == "1",
        ):
            required_scope = required_scope_for_tool(name)
            tools.append({
                "name": name,
                "mode": tool_mode(name),
                "requiredScope": required_scope,
                "description": TOOL_DESCRIPTIONS.get(name, ""),
                "inputSchema": CONTRACTS.get(name, _empty()),
                "endpoint": AURION_ADMIN_MCP_PATH,
                "handler": AURION_TOOL_HANDLER_MAP[name],
                "transport": "MCP tools/call over existing HTTPS resource",
            })
        return {
            "protocol": AURION_ADMIN_MCP_PROTOCOL,
            "resource": self._resource_url(),
            "tools": tools,
            "scopePolicy": {
                "configured": sorted(configured_scopes),
                "actualAuthority": "Aurion OAuth/OIDC token + JWKS/issuer/audience/expiry + persisted users.role=admin",
                "read": READ_SCOPE,
                "assetsWrite": ASSET_WRITE_SCOPE,
                "authoringWrite": AUTHORING_WRITE_SCOPE,
            },
            "unavailable": [
                "raw_world_delta_write",
                "raw_object_placement",
                "npc_reward_mutation",
                "causal_rollback",
                "database_access",
                "shell_access",
                "git_or_vps_access",
            ],
        }

    def call(self, *, tool_name: str, arguments: dict[str, Any], require_write: bool) -> dict[str, Any]:
        if tool_name not in ALL_AURION_ADMIN_TOOLS:
            return self._blocked("AURION_TOOL_NOT_ALLOWLISTED")
        actual_mode = tool_mode(tool_name)
        expected_mode = "write" if require_write else "read"
        if actual_mode != expected_mode:
            return self._blocked("AURION_BROKER_PATH_MISMATCH", expectedMode=expected_mode, actualMode=actual_mode)
        required_scope = required_scope_for_tool(tool_name)
        try:
            allowed_scopes = self._local_allowed_scopes()
            if required_scope not in allowed_scopes:
                return self._blocked("AURION_SCOPE_NOT_ENABLED_LOCALLY", requiredScope=required_scope)
            if actual_mode == "write" and os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() != "1":
                return self._blocked("SOVEREIGN_OWNER_MODE_REQUIRED")
            url = self._resource_url()
            token = self._token()
        except RuntimeError as exc:
            return self._blocked(str(exc))
        payload = {
            "jsonrpc": "2.0",
            "id": f"sovereign-aurion-{uuid.uuid4().hex}",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": dict(arguments)},
        }
        try:
            response = self._session.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(10, 180 if actual_mode == "write" else 90),
            )
        except requests.RequestException as exc:
            return self._blocked("AURION_ADMIN_HTTP_UNAVAILABLE", errorType=type(exc).__name__)
        if response.status_code == 401:
            return self._blocked("AURION_ADMIN_OAUTH_REJECTED", httpStatus=401)
        if response.status_code >= 400:
            return self._blocked("AURION_ADMIN_HTTP_REJECTED", httpStatus=response.status_code)
        try:
            body = response.json()
        except ValueError:
            return self._blocked("AURION_ADMIN_RESPONSE_NOT_JSON", httpStatus=response.status_code)
        if not isinstance(body, dict):
            return self._blocked("AURION_ADMIN_RESPONSE_INVALID")
        if isinstance(body.get("error"), dict):
            err = body["error"]
            return self._blocked(
                "AURION_ADMIN_REMOTE_ERROR",
                remoteErrorCode=err.get("code"),
                remoteErrorMessage=str(err.get("message") or "")[:320],
            )
        result = body.get("result")
        if not isinstance(result, dict):
            return self._blocked("AURION_ADMIN_RESULT_MISSING")
        output = result.get("structuredContent")
        if output is None:
            output = result.get("content")
        return {
            "ok": True,
            "status": "AURION_ADMIN_MCP_REMOTE_VERIFIED",
            "protocol": AURION_ADMIN_MCP_PROTOCOL,
            "tool": tool_name,
            "mode": actual_mode,
            "requiredScope": required_scope,
            "resource": self._resource_url(),
            "result": output,
            "mutationPerformed": actual_mode == "write",
            "secretValuesReturned": False,
        }

    @staticmethod
    def _blocked(blocker: str, **extra: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "AURION_ADMIN_MCP_BLOCKED",
            "failureFamily": blocker,
            "blocker": blocker,
            "mutationPerformed": False,
            "secretValuesReturned": False,
            **extra,
        }

def make_tool_handler(runtime: AurionAdminMcpRuntime, tool_name: str) -> Callable[..., dict[str, Any]]:
    def handler(**kwargs: Any) -> dict[str, Any]:
        # Aurion is the final JSON-schema validator. This adapter deliberately
        # does not reimplement the Zod semantics and therefore cannot become a
        # divergent second authority.
        return runtime.call(tool_name=tool_name, arguments=dict(kwargs), require_write=tool_mode(tool_name) == "write")
    handler.__name__ = tool_name
    handler.__doc__ = TOOL_DESCRIPTIONS.get(tool_name, tool_name)
    return handler
