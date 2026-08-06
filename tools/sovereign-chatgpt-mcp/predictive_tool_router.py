from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,79}")

_ACTION_MARKERS: dict[str, tuple[str, ...]] = {
    "resolve": ("resolve", "revision", "identity", "workspace", "head", "sha"),
    "read": ("read", "inspect", "inventory", "scan", "search", "find", "list", "status", "diff"),
    "append": ("append", "checkpoint", "ledger", "jsonl", "continuity", "end-of-file", "eof"),
    "patch": ("patch", "replace", "repair", "fix", "update", "write", "apply"),
    "mirror-verify": ("mirror", "bytegleich", "byte-identical", "parity", "identical", "gleich"),
    "validate": ("validate", "verify", "check", "test", "gate", "diagnostic", "schema"),
    "publish": ("publish", "draft", "pull-request", "pull_request", "pr", "commit", "push"),
    "merge": ("merge", "integrate"),
    "release": ("release", "deploy", "image", "artifact", "rollback"),
}

_OBJECT_MARKERS: dict[str, tuple[str, ...]] = {
    "repository": ("repository", "repo", "workspace", "git", "github"),
    "file": ("file", "path", "blob", "sha256", "content"),
    "ledger": ("ledger", "jsonl", "continuity", "checkpoint", "append-only"),
    "mirror": ("mirror", "bytegleich", "byte-identical", "parity"),
    "pull-request": ("draft", "pull-request", "pull_request", "pr", "head"),
    "ci": ("ci", "workflow", "check", "test", "gate"),
    "runtime": ("runtime", "container", "broker", "mcp"),
    "release": ("release", "deploy", "image", "digest", "artifact"),
    "database": ("database", "postgres", "migration", "schema", "sql"),
}

_ACTION_TOOL_HINTS: dict[str, tuple[str, ...]] = {
    "resolve": ("revision_resolve", "revision", "identity", "probe", "context_drift", "status"),
    "read": ("read_file", "search_text", "inventory", "status", "diff", "snapshot", "report"),
    "append": ("apply_search_replace", "hash_bound_replace", "write_new_file"),
    "patch": ("apply_search_replace", "hash_bound_replace", "restore", "materialize"),
    "mirror-verify": ("mirror_diff_report", "continuity_status", "run_check"),
    "validate": ("run_check", "schema_diagnostics", "verify", "audit", "status"),
    "publish": ("create_draft_pr", "update_pr", "pr_status"),
    "merge": ("merge_pr", "merge_pr_series"),
    "release": ("deploy_", "release", "self_update", "rollback"),
}

_OBJECT_TOOL_HINTS: dict[str, tuple[str, ...]] = {
    "repository": ("repository_", "github_", "workspace"),
    "file": ("read_file", "write_new_file", "replace", "restore", "blob"),
    "ledger": ("continuity", "ledger", "apply_search_replace", "hash_bound_replace"),
    "mirror": ("mirror_diff_report", "continuity_status", "mirror"),
    "pull-request": ("draft_pr", "pr_status", "merge_pr", "update_pr"),
    "ci": ("workflow", "run_check", "check", "ci"),
    "runtime": ("runtime", "mcp", "broker", "container"),
    "release": ("release", "deploy", "image", "rollback"),
    "database": ("postgres", "database", "migration", "schema"),
}

_MUTATING_ACTIONS = frozenset({"append", "patch", "publish", "merge", "release"})

_STAGE_TOOL_HINTS: dict[str, tuple[str, ...]] = {
    "revision-identity": ("repository_revision_resolve", "repository_revision_probe", "context_drift_watch"),
    "file-read": ("repository_read_file",),
    "ledger-write": ("repository_apply_search_replace", "repository_hash_bound_replace"),
    "mirror-verification": ("repository_mirror_diff_report",),
    "validation": ("repository_run_check", "repository_schema_diagnostics"),
    "publication": ("repository_create_draft_pr",),
    "merge": ("repository_merge_pr", "repository_merge_pr_series"),
    "release": ("deploy_verified", "mcp_self_update", "release_reconciler"),
}


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(value or "").casefold()))


def _contains_marker(text: str, tokens: set[str], marker: str) -> bool:
    marker = marker.casefold()
    if len(marker) <= 3:
        return marker in tokens
    return marker in tokens or marker in text


def _detect_nodes(text: str, marker_map: dict[str, tuple[str, ...]]) -> list[str]:
    lowered = str(text or "").casefold()
    tokens = _tokens(lowered)
    return sorted(
        node
        for node, markers in marker_map.items()
        if any(_contains_marker(lowered, tokens, marker) for marker in markers)
    )


def _parameter_tokens(parameters: Any) -> set[str]:
    if not isinstance(parameters, dict):
        return set()
    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        return set()
    values: set[str] = set()
    for name, schema in properties.items():
        values.update(_tokens(str(name)))
        if isinstance(schema, dict):
            values.update(_tokens(str(schema.get("title") or "")))
            values.update(_tokens(str(schema.get("description") or "")))
    return values


def _tool_nodes(item: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    name = str(item.get("name") or "").casefold()
    description = str(item.get("description") or "").casefold()
    parameter_tokens = _parameter_tokens(item.get("parameters"))
    haystack = f"{name} {description} {' '.join(sorted(parameter_tokens))}"
    actions = {
        action
        for action, hints in _ACTION_TOOL_HINTS.items()
        if any(hint in haystack for hint in hints)
    }
    objects = {
        obj
        for obj, hints in _OBJECT_TOOL_HINTS.items()
        if any(hint in haystack for hint in hints)
    }
    stages = {
        stage
        for stage, hints in _STAGE_TOOL_HINTS.items()
        if any(hint in haystack for hint in hints)
    }
    return actions, objects, stages


@dataclass(frozen=True)
class MissionPerception:
    actions: tuple[str, ...]
    objects: tuple[str, ...]
    stages: tuple[str, ...]
    tokens: tuple[str, ...]
    mutation_expected: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "actions": list(self.actions),
            "objects": list(self.objects),
            "stages": list(self.stages),
            "tokens": list(self.tokens),
            "mutationExpected": self.mutation_expected,
        }


def perceive_mission(mission_summary: str, required_evidence: Iterable[str]) -> MissionPerception:
    combined = " ".join([str(mission_summary or ""), *(str(item or "") for item in required_evidence)])
    action_set = set(_detect_nodes(combined, _ACTION_MARKERS))
    object_set = set(_detect_nodes(combined, _OBJECT_MARKERS))
    if action_set & {"append", "patch", "mirror-verify"}:
        action_set.add("read")
    if action_set & {"publish", "merge", "release"}:
        action_set.update({"resolve", "validate"})
    if "ledger" in object_set:
        object_set.add("file")
    if "mirror" in object_set:
        object_set.add("file")
    stages: set[str] = set()
    if "resolve" in action_set:
        stages.add("revision-identity")
    if "read" in action_set and "file" in object_set:
        stages.add("file-read")
    if "append" in action_set and "ledger" in object_set:
        stages.add("ledger-write")
    if "mirror-verify" in action_set and "mirror" in object_set:
        stages.add("mirror-verification")
    if "validate" in action_set:
        stages.add("validation")
    if "publish" in action_set:
        stages.add("publication")
    if "merge" in action_set:
        stages.add("merge")
    if "release" in action_set:
        stages.add("release")
    actions = sorted(action_set)
    objects = sorted(object_set)
    tokens = sorted(_tokens(combined))
    return MissionPerception(
        actions=tuple(actions),
        objects=tuple(objects),
        stages=tuple(sorted(stages)),
        tokens=tuple(tokens),
        mutation_expected=bool(set(actions) & _MUTATING_ACTIONS),
    )


def predict_tool_route(
    *,
    catalog: list[dict[str, Any]],
    mission_summary: str,
    required_capabilities: set[str],
    allowed_effects: set[str],
    required_evidence: list[str],
    excluded_tools: set[str],
    max_tools: int,
    historical_bonuses: dict[str, int] | None = None,
) -> dict[str, Any]:
    perception = perceive_mission(mission_summary, required_evidence)
    mission_tokens = set(perception.tokens)
    required_actions = set(perception.actions)
    perceived_objects = set(perception.objects)
    required_stages = set(perception.stages)
    required_objects: set[str] = set()
    if "repository" in perceived_objects:
        required_objects.add("repository")
    if required_stages & {"file-read", "ledger-write", "mirror-verification"}:
        required_objects.add("file")
    if "ledger-write" in required_stages:
        required_objects.add("ledger")
    if "mirror-verification" in required_stages:
        required_objects.add("mirror")
    if required_stages & {"publication", "merge"}:
        required_objects.add("pull-request")
    if required_stages & {"revision-identity", "validation"} and "ci" in perceived_objects:
        required_objects.add("ci")
    if "release" in required_stages:
        required_objects.add("release")
        if "runtime" in perceived_objects:
            required_objects.add("runtime")
    scored: list[dict[str, Any]] = []
    bonuses = historical_bonuses or {}

    for item in catalog:
        name = str(item.get("name") or "")
        if not name or name in excluded_tools or name == "tool_recommend_for_mission":
            continue
        effect = str(item.get("effect") or "")
        if effect not in allowed_effects:
            continue
        capabilities = set(item.get("capabilities") or [])
        matched_capabilities = sorted(required_capabilities & capabilities)
        tool_actions, tool_objects, tool_stages = _tool_nodes(item)
        matched_actions = sorted(required_actions & tool_actions)
        matched_objects = sorted(required_objects & tool_objects)
        matched_stages = sorted(required_stages & tool_stages)
        text_tokens = _tokens(f"{name} {item.get('description') or ''}") | _parameter_tokens(item.get("parameters"))
        matched_terms = sorted(mission_tokens & text_tokens)

        if not matched_capabilities and not matched_actions and not matched_objects and not matched_stages:
            continue

        score = (
            len(matched_capabilities) * 90
            + len(matched_actions) * 160
            + len(matched_objects) * 80
            + len(matched_stages) * 220
            + len(matched_terms) * 8
        )
        if perception.mutation_expected:
            if effect in {"workspace-write", "external-write"} and matched_actions:
                score += 35
            elif effect == "read" and set(matched_actions) & _MUTATING_ACTIONS:
                score -= 80
        elif effect == "read":
            score += 15
        annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
        if annotations.get("idempotentHint"):
            score += 6
        if annotations.get("destructiveHint"):
            score -= 120
        success_bonus = max(0, min(int(bonuses.get(name, 0)), 80)) if matched_stages or matched_actions or matched_objects else 0
        score += success_bonus

        scored.append(
            {
                "name": name,
                "score": score,
                "matchedCapabilities": matched_capabilities,
                "matchedFunctionalActions": matched_actions,
                "matchedFunctionalObjects": matched_objects,
                "matchedFunctionalStages": matched_stages,
                "matchedMissionTerms": matched_terms,
                "effect": effect,
                "contractSha256": item.get("contractSha256"),
                "historicalSuccessBonus": success_bonus,
                "reason": {
                    "capabilityMatches": matched_capabilities,
                    "actionMatches": matched_actions,
                    "objectMatches": matched_objects,
                    "stageMatches": matched_stages,
                    "missionTermMatches": matched_terms,
                    "historicalSuccessBonus": success_bonus,
                },
            }
        )

    scored.sort(key=lambda item: (-int(item["score"]), str(item["name"])))
    selected: list[dict[str, Any]] = []
    covered_capabilities: set[str] = set()
    covered_actions: set[str] = set()
    covered_objects: set[str] = set()
    covered_stages: set[str] = set()

    for candidate in scored:
        candidate_capabilities = set(candidate["matchedCapabilities"])
        candidate_actions = set(candidate["matchedFunctionalActions"])
        candidate_objects = set(candidate["matchedFunctionalObjects"])
        candidate_stages = set(candidate["matchedFunctionalStages"])
        useful = bool(
            candidate_capabilities - covered_capabilities
            or candidate_actions - covered_actions
            or candidate_objects - covered_objects
            or candidate_stages - covered_stages
        )
        if useful or len(selected) < min(2, max_tools):
            selected.append(candidate)
            covered_capabilities.update(candidate_capabilities)
            covered_actions.update(candidate_actions)
            covered_objects.update(candidate_objects)
            covered_stages.update(candidate_stages)
        if len(selected) >= max_tools:
            break
        if (
            covered_capabilities >= required_capabilities
            and covered_actions >= required_actions
            and covered_objects >= required_objects
            and covered_stages >= required_stages
        ):
            break

    missing_capabilities = sorted(required_capabilities - covered_capabilities)
    missing_actions = sorted(required_actions - covered_actions)
    missing_objects = sorted(required_objects - covered_objects)
    missing_stages = sorted(required_stages - covered_stages)
    top_score = int(scored[0]["score"]) if scored else 0
    runner_up = int(scored[1]["score"]) if len(scored) > 1 else 0
    confidence_margin = top_score - runner_up
    route_complete = not missing_capabilities and not missing_actions and not missing_objects and not missing_stages
    confidence = "high" if route_complete and confidence_margin >= 80 else "medium" if route_complete else "low"

    return {
        "perception": perception.as_dict(),
        "selectedTools": selected,
        "coveredCapabilities": sorted(covered_capabilities),
        "coveredFunctionalActions": sorted(covered_actions),
        "coveredFunctionalObjects": sorted(covered_objects),
        "coveredFunctionalStages": sorted(covered_stages),
        "missingCapabilities": missing_capabilities,
        "missingFunctionalActions": missing_actions,
        "missingFunctionalObjects": missing_objects,
        "missingFunctionalStages": missing_stages,
        "routeComplete": route_complete,
        "confidence": confidence,
        "confidenceMargin": confidence_margin,
        "candidateCount": len(scored),
        "predictiveAdvisoryOnly": True,
        "deterministicGatesRequired": True,
    }
