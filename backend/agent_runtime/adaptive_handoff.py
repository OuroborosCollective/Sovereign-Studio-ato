"""Adaptive, evidence-bounded handoff projections for the existing Sovereign runtime.

This module does not execute tools, choose permissions, call model providers or create
repository truth. It only derives bounded context from the live in-process tool
registry and low-risk process observations before the existing Sovereign Agent
workspace takes over.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
from typing import Any, Iterable

from .tools.base import get_tool_registry

ADAPTIVE_HANDOFF_VERSION = "1.0.0"
MAX_PROJECTED_TOOLS = 6
_MAX_MISSION_CHARS = 20_000

_MUTATION_TERMS = (
    "fix", "repair", "implement", "build", "change", "modify", "patch",
    "write", "edit", "refactor", "draft pr", "pull request", "test", "deploy",
    "beheb", "repar", "implement", "änder", "aender", "patch", "schreib",
    "entfern", "bau ", "draft-pr", "testen",
)

_INTENT_TERMS: dict[str, tuple[str, ...]] = {
    "filesystem": ("file", "path", "datei", "ordner", "filesystem"),
    "git": ("git", "branch", "commit", "diff", "repository", "repo", "draft pr", "pull request"),
    "repository": ("repository", "repo", "code", "source", "frontend", "backend", "runtime"),
    "test": ("test", "pytest", "vitest", "check", "ci", "workflow", "smoke"),
    "shell": ("command", "shell", "script", "cli"),
}

_READ_BASELINE = ("file_read", "git_status", "git_diff")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_hash(value: Any) -> str:
    return _sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _bounded_mission(mission: str) -> str:
    return str(mission or "")[:_MAX_MISSION_CHARS].strip()


def _read_mem_total_bytes() -> int | None:
    path = Path("/proc/meminfo")
    if not path.is_file():
        return None
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                match = re.search(r"(\d+)", line)
                return int(match.group(1)) * 1024 if match else None
    except OSError:
        return None
    return None


def runtime_environment_readback() -> dict[str, Any]:
    """Return bounded process/host observations without claiming target health."""
    observations = {
        "os": platform.system() or "unknown",
        "architecture": platform.machine() or "unknown",
        "cpuCount": os.cpu_count(),
        "memoryBytes": _read_mem_total_bytes(),
        "deviceVisibility": {
            "nvidiaControl": Path("/dev/nvidiactl").exists(),
            "drm": Path("/dev/dri").exists(),
        },
    }
    sources = ["python-platform", "os.cpu_count", "device-node-presence"]
    if observations["memoryBytes"] is not None:
        sources.append("/proc/meminfo")
    payload = {
        "status": "OBSERVED_UNVERIFIED",
        "runtimeVerified": False,
        "scope": "backend-process-observation",
        "observations": observations,
        "sources": sources,
        "limitations": [
            "Process visibility does not prove provider health, model suitability, GPU usability, deployment revision, or target-system success.",
            "No device inventory, environment values, credentials, hostnames, or network identifiers are exposed.",
        ],
    }
    payload["readbackHash"] = _canonical_hash(payload)
    return payload


def _mutation_requested(mission: str) -> bool:
    lowered = mission.lower()
    return any(term in lowered for term in _MUTATION_TERMS)


def _tool_score(tool: dict[str, Any], mission: str) -> tuple[int, list[str]]:
    lowered = mission.lower()
    name = str(tool.get("name") or "")
    description = str(tool.get("description") or "").lower()
    capabilities = [str(item) for item in tool.get("capabilities") or []]
    score = 0
    reasons: list[str] = []

    if name in _READ_BASELINE:
        score += 12
        reasons.append("safe repository-read baseline")

    for capability in capabilities:
        terms = _INTENT_TERMS.get(capability, ())
        hits = [term for term in terms if term in lowered]
        if hits:
            score += 4 + len(hits)
            reasons.append(f"mission matches capability:{capability}")

    name_terms = tuple(part for part in name.lower().split("_") if len(part) > 2)
    if any(term in lowered for term in name_terms):
        score += 3
        reasons.append("mission matches tool name")

    description_terms = ("test", "diff", "read", "write", "git", "repository", "shell")
    if any(term in lowered and term in description for term in description_terms):
        score += 1
        reasons.append("mission matches tool description")

    return score, reasons


def project_tools_for_mission(mission: str, *, limit: int = MAX_PROJECTED_TOOLS) -> dict[str, Any]:
    """Project a small advisory tool set from the real central ToolRegistry."""
    normalized = _bounded_mission(mission)
    if not normalized:
        raise ValueError("mission is required")
    requested = max(1, min(int(limit or MAX_PROJECTED_TOOLS), MAX_PROJECTED_TOOLS))
    mutation_requested = _mutation_requested(normalized)

    available = get_tool_registry().list_tools()
    ranked: list[dict[str, Any]] = []
    for tool in available:
        effect = str(tool.get("effect") or "read")
        if effect != "read" and not mutation_requested:
            continue
        score, reasons = _tool_score(tool, normalized)
        if score <= 0:
            continue
        ranked.append({
            "name": str(tool.get("name") or ""),
            "effect": effect,
            "capabilities": sorted(str(item) for item in tool.get("capabilities") or []),
            "score": score,
            "reasons": reasons,
        })

    ranked.sort(key=lambda item: (-int(item["score"]), item["effect"] != "read", item["name"]))
    selected = ranked[:requested]
    payload = {
        "status": "PROJECTED_UNVERIFIED",
        "registrySource": "agent_runtime.tools.base.get_tool_registry",
        "authorizesExecution": False,
        "mutationIntentDetected": mutation_requested,
        "limit": requested,
        "availableToolCount": len(available),
        "selected": selected,
        "limitations": [
            "Projection reduces model context only; ToolRunner policy, capability checks, permissions and workspace/revision gates remain authoritative.",
            "A projected tool is not evidence that the tool can or should execute.",
        ],
    }
    payload["projectionHash"] = _canonical_hash({
        "missionHash": _sha256_text(normalized),
        "selected": selected,
        "limit": requested,
    })
    return payload


def provider_readiness_projection() -> dict[str, Any]:
    """Describe the canonical routing contract without fabricating provider health."""
    payload = {
        "status": "UNVERIFIED",
        "runtimeVerified": False,
        "canonicalRoutes": {
            "paid": ["openrouter"],
            "free": ["freellm", "revolver"],
        },
        "prohibitedRuntimeRoutes": ["litellm"],
        "degraded": ["PROVIDER_RUNTIME_READBACK_NOT_SUPPLIED_TO_HANDOFF"],
        "requirementsForRuntimeVerification": [
            "server-resolved execution route",
            "provider/model identity",
            "route or price/config hash where applicable",
            "actual provider execution receipt",
            "independent result/readback evidence",
        ],
    }
    payload["contractHash"] = _canonical_hash(payload)
    return payload


def compare_candidate_evidence(input_text: str, candidates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Bind candidate outputs to one input and summarize supplied independent evidence.

    This function never calls a model and never promotes a comparison to runtime truth.
    """
    bounded_input = str(input_text or "")[:_MAX_MISSION_CHARS]
    if not bounded_input.strip():
        raise ValueError("input_text is required")
    input_hash = _sha256_text(bounded_input)
    normalized: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        candidate_input_hash = str(candidate.get("inputHash") or input_hash)
        if candidate_input_hash != input_hash:
            raise ValueError(f"candidate {index} inputHash does not match comparison input")
        output = str(candidate.get("output") or "")
        evidence = [
            str(item)[:2_000]
            for item in (candidate.get("evidence") or [])
            if str(item).strip()
        ]
        normalized.append({
            "model": str(candidate.get("model") or f"candidate-{index + 1}")[:200],
            "inputHash": input_hash,
            "outputHash": _sha256_text(output),
            "evidenceCount": len(evidence),
            "evidenceHash": _canonical_hash(evidence),
        })

    status = "EVIDENCE_BOUND_COMPARISON" if len(normalized) >= 2 else "INSUFFICIENT_CANDIDATES"
    payload = {
        "status": status,
        "runtimeVerified": False,
        "inputHash": input_hash,
        "candidateCount": len(normalized),
        "candidates": normalized,
        "winner": None,
        "limitations": [
            "Hash agreement proves binding, not correctness.",
            "No candidate becomes target-system evidence without independent verification.",
            "This comparison does not select a winner when no explicit external evaluator evidence is supplied.",
        ],
    }
    payload["comparisonHash"] = _canonical_hash(payload)
    return payload


def build_adaptive_handoff_projection(mission: str) -> dict[str, Any]:
    normalized = _bounded_mission(mission)
    if not normalized:
        raise ValueError("mission is required")
    projection = {
        "version": ADAPTIVE_HANDOFF_VERSION,
        "runtime": runtime_environment_readback(),
        "toolProjection": project_tools_for_mission(normalized),
        "providerReadiness": provider_readiness_projection(),
        "modelComparison": {
            "status": "READY_FOR_EVIDENCE",
            "executed": False,
            "runtimeVerified": False,
            "contract": "same-input-hash + output-hash + independent-evidence binding",
        },
    }
    projection["projectionHash"] = _canonical_hash(projection)
    return projection


def render_adaptive_handoff_lines(projection: dict[str, Any]) -> list[str]:
    tools = projection.get("toolProjection", {}).get("selected", [])
    names = ", ".join(str(item.get("name") or "") for item in tools) or "none"
    provider = projection.get("providerReadiness", {})
    runtime = projection.get("runtime", {})
    return [
        "[Adaptive evidence-bounded handoff projection]",
        f"Projected tools (advisory only): {names}",
        f"Provider route contract: paid=OpenRouter; free=FreeLLM/Revolver; runtime status={provider.get('status', 'UNVERIFIED')}.",
        f"Backend process observation status: {runtime.get('status', 'OBSERVED_UNVERIFIED')}; this is not deployment or target health.",
        "Model comparison contract is ready but not executed unless multiple same-input candidates and independent evidence are supplied.",
        "Projection never grants permission or bypasses ToolRunner, workspace, revision, consent, CI, Draft-PR, deployment, or runtime-evidence gates.",
    ]
