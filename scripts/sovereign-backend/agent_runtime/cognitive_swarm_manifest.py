"""Deterministic contract for the Sovereign eight-agent cognitive swarm.

This module contains no model calls and no side effects. It is the single source
of truth for role count, role ordering, zones, approval boundaries and the
mandatory double-loop lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import PurePosixPath
from typing import Final, Literal


AgentRole = Literal[
    "dispatcher",
    "data_storage",
    "business_core",
    "endpoint_bridge",
    "chat_cognitive",
    "ui_accessibility",
    "predictive_qa",
    "judge",
]

SpecialistRole = Literal[
    "frontend",
    "ux_accessibility",
    "backend",
    "mcp_broker",
    "android",
    "database",
    "browser_qa",
    "document",
    "report",
    "security",
    "dependency",
    "performance",
]

ZoneName = Literal["workspace", "repository", "offline_cache", "external_assets"]


@dataclass(frozen=True, slots=True)
class ZoneContract:
    name: ZoneName
    path: str
    writable: bool
    purpose: str


@dataclass(frozen=True, slots=True)
class AgentContract:
    index: int
    role: AgentRole
    name: str
    responsibility: str
    allowed_zones: tuple[ZoneName, ...]
    may_mutate: bool
    may_release: bool


ZONES: Final[tuple[ZoneContract, ...]] = (
    ZoneContract(
        name="workspace",
        path="/workspace/local/temp_builds",
        writable=True,
        purpose="Isolated validation, compilation and evidence generation.",
    ),
    ZoneContract(
        name="repository",
        path="/workspace/server/core_repo",
        writable=True,
        purpose="Isolated repository clone and task branch; never the live main checkout.",
    ),
    ZoneContract(
        name="offline_cache",
        path="/mnt/sdcard/sovereign_data",
        writable=True,
        purpose="Device-owned offline cache reached only through a validated native bridge.",
    ),
    ZoneContract(
        name="external_assets",
        path="https://cdn.sovereign.local/assets/",
        writable=False,
        purpose="Configured external asset origin; access requires explicit runtime configuration.",
    ),
)


AGENTS: Final[tuple[AgentContract, ...]] = (
    AgentContract(0, "dispatcher", "The Dispatcher", "Plan, route and preserve the fixed execution order.", ("workspace", "repository"), False, False),
    AgentContract(1, "data_storage", "Data & Storage Node", "Inspect database, offline cache, vector and object-storage truth paths.", ("workspace", "repository", "offline_cache", "external_assets"), True, False),
    AgentContract(2, "business_core", "Business & Core Logic Node", "Review credits, tiers, limits and transactional invariants without mock payment success.", ("workspace", "repository"), True, False),
    AgentContract(3, "endpoint_bridge", "Endpoint & Bridge Node", "Review authenticated REST, streaming, MCP and evidence transport boundaries.", ("workspace", "repository"), True, False),
    AgentContract(4, "chat_cognitive", "Functional Chat & Cognitive Action Node", "Review inference, predictive checks, tool routing and bounded pattern learning.", ("workspace", "repository", "offline_cache"), True, False),
    AgentContract(5, "ui_accessibility", "UI, CSS & Accessibility Node", "Review responsive UI, ARIA, CSP and interaction evidence.", ("workspace", "repository"), True, False),
    AgentContract(6, "predictive_qa", "Predictive Build Nervous System & QA Node", "Validate supplied build, test, browser, trace and artifact evidence.", ("workspace", "repository"), False, False),
    AgentContract(7, "judge", "The Judge", "Reject unsupported claims and permit only evidence-backed Draft PR readiness.", ("workspace", "repository"), False, True),
)


WORKER_ROLES: Final[tuple[AgentRole, ...]] = (
    "data_storage",
    "business_core",
    "endpoint_bridge",
    "chat_cognitive",
    "ui_accessibility",
    "predictive_qa",
)

SPECIALIST_ROLES: Final[tuple[SpecialistRole, ...]] = (
    "frontend",
    "ux_accessibility",
    "backend",
    "mcp_broker",
    "android",
    "database",
    "browser_qa",
    "document",
    "report",
    "security",
    "dependency",
    "performance",
)

DEFAULT_MAX_ACTIVE_SPECIALISTS: Final[int] = 4
HARD_MAX_ACTIVE_SPECIALISTS: Final[int] = 8


def max_active_specialists() -> int:
    raw = os.getenv("SOVEREIGN_MAX_ACTIVE_AGENTS", str(DEFAULT_MAX_ACTIVE_SPECIALISTS)).strip()
    try:
        requested = int(raw)
    except ValueError:
        requested = DEFAULT_MAX_ACTIVE_SPECIALISTS
    return max(1, min(requested, HARD_MAX_ACTIVE_SPECIALISTS, len(SPECIALIST_ROLES)))

DOUBLE_LOOP_PHASES: Final[tuple[str, ...]] = (
    "dispatcher_plan",
    "worker_pass_one",
    "judge_checkpoint_one",
    "worker_refinement_pass_two",
    "judge_final_verdict",
)

FORBIDDEN_RELEASE_STATES: Final[frozenset[str]] = frozenset({
    "missing_evidence",
    "failed_check",
    "unresolved_blocker",
    "unreviewed_side_effect",
    "non_draft_release",
})


def validate_manifest() -> None:
    if len(AGENTS) != 8:
        raise ValueError("The orchestrator must contain exactly eight fixed core agents.")
    if tuple(agent.index for agent in AGENTS) != tuple(range(8)):
        raise ValueError("Agent indexes must be contiguous and ordered from zero through seven.")
    if len({agent.role for agent in AGENTS}) != len(AGENTS):
        raise ValueError("Agent roles must be unique.")
    if AGENTS[0].role != "dispatcher" or AGENTS[-1].role != "judge":
        raise ValueError("The topology must start with the dispatcher and end with the judge.")
    if tuple(agent.role for agent in AGENTS[1:7]) != WORKER_ROLES:
        raise ValueError("Exactly six workers must remain between dispatcher and judge.")
    if any(agent.may_release for agent in AGENTS[:-1]):
        raise ValueError("Only the judge may declare Draft PR readiness.")
    if AGENTS[-1].may_mutate:
        raise ValueError("The judge must never mutate the repository.")

    known_zones = {zone.name for zone in ZONES}
    for agent in AGENTS:
        unknown = set(agent.allowed_zones) - known_zones
        if unknown:
            raise ValueError(f"Agent {agent.index} references unknown zones: {sorted(unknown)}")

    for zone in ZONES:
        if zone.name != "external_assets":
            normalized = PurePosixPath(zone.path)
            if not normalized.is_absolute() or ".." in normalized.parts:
                raise ValueError(f"Zone path is not absolute and bounded: {zone.path}")


def manifest_payload() -> dict[str, object]:
    validate_manifest()
    return {
        "schema": 2,
        "agentCount": len(AGENTS) + len(SPECIALIST_ROLES),
        "coreAgentCount": len(AGENTS),
        "specialistAgentCount": len(SPECIALIST_ROLES),
        "maxActiveSpecialists": max_active_specialists(),
        "specialistRoles": list(SPECIALIST_ROLES),
        "agents": [
            {
                "index": agent.index,
                "role": agent.role,
                "name": agent.name,
                "responsibility": agent.responsibility,
                "allowedZones": list(agent.allowed_zones),
                "mayMutate": agent.may_mutate,
                "mayRelease": agent.may_release,
            }
            for agent in AGENTS
        ],
        "zones": [
            {
                "name": zone.name,
                "path": zone.path,
                "writable": zone.writable,
                "purpose": zone.purpose,
            }
            for zone in ZONES
        ],
        "doubleLoop": list(DOUBLE_LOOP_PHASES),
        "releaseMode": "draft_pr_only",
        "autoMerge": False,
        "runtimeTruthRequired": True,
        "specialistsMaySpawnAgents": False,
    }


validate_manifest()
