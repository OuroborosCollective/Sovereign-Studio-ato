"""OpenAI Agents SDK orchestration for the Sovereign cognitive swarm.

The model layer plans and reviews. Repository, database, deployment and merge
mutations remain in the existing bounded runtime tools and approval gates.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, Field

from .cognitive_swarm_manifest import (
    AGENTS,
    SPECIALIST_ROLES,
    WORKER_ROLES,
    manifest_payload,
    max_active_specialists,
)


DEFAULT_MODEL: Final[str] = "gpt-5.6"
SKILL_PATH: Final[Path] = Path(__file__).parent / "skills" / "sovereign-cognitive-architecture" / "SKILL.md"

_AGENT_CLASS: Any | None = None
_RUNNER_CLASS: Any | None = None
_AGENTS_SDK_ERROR = ""

try:
    _AGENTS_SDK_VERSION = importlib.metadata.version("openai-agents")
    _agents_module = importlib.import_module("agents")
    _agent_candidate = getattr(_agents_module, "Agent", None)
    _runner_candidate = getattr(_agents_module, "Runner", None)
    if not callable(_agent_candidate) or _runner_candidate is None or not callable(getattr(_runner_candidate, "run", None)):
        raise ImportError("the imported agents module is not the OpenAI Agents SDK")
    _AGENT_CLASS = _agent_candidate
    _RUNNER_CLASS = _runner_candidate
except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
    _AGENTS_SDK_VERSION = ""
    _AGENTS_SDK_ERROR = f"{type(exc).__name__}: {exc}"


def agents_sdk_status() -> dict[str, object]:
    available = _AGENT_CLASS is not None and _RUNNER_CLASS is not None
    return {
        "available": available,
        "distribution": "openai-agents",
        "version": _AGENTS_SDK_VERSION or None,
        "error": None if available else _AGENTS_SDK_ERROR or "OpenAI Agents SDK is unavailable.",
    }


def _require_agents_sdk() -> tuple[Any, Any]:
    if _AGENT_CLASS is None or _RUNNER_CLASS is None:
        raise RuntimeError(
            "openai-agents is unavailable or shadowed by a different 'agents' module; "
            "install the pinned backend dependency before running the swarm"
        )
    return _AGENT_CLASS, _RUNNER_CLASS


class DispatchPlan(BaseModel):
    mission: str
    ordered_work: list[str] = Field(min_length=6, max_length=6)
    required_evidence: list[str]
    initial_blockers: list[str]


class WorkerReport(BaseModel):
    role: str
    loop: int
    status: str
    findings: list[str]
    required_actions: list[str]
    evidence_observed: list[str]
    evidence_missing: list[str]
    blocked: bool


class JudgeVerdict(BaseModel):
    loop: int
    verdict: str
    blockers: list[str]
    accepted_evidence: list[str]
    rejected_claims: list[str]
    required_next_actions: list[str]
    draft_pr_ready: bool
    human_approval_required: bool = True


class CognitiveSwarm:
    def __init__(
        self,
        *,
        dispatcher: Any,
        workers: tuple[Any, ...],
        specialists: tuple[Any, ...],
        judge: Any,
    ) -> None:
        if len(workers) != 6:
            raise ValueError("The Sovereign orchestrator requires exactly six bounded core worker agents.")
        if len(specialists) > max_active_specialists():
            raise ValueError("Active specialist agents exceed SOVEREIGN_MAX_ACTIVE_AGENTS.")
        self.dispatcher = dispatcher
        self.workers = workers
        self.specialists = specialists
        self.judge = judge

    @property
    def agent_count(self) -> int:
        return 2 + len(self.workers) + len(self.specialists)


def _load_skill_instructions() -> str:
    content = SKILL_PATH.read_text("utf-8").strip()
    if not content.startswith("---"):
        raise RuntimeError("Sovereign cognitive skill front matter is missing.")
    return content


def _base_instructions(skill: str) -> str:
    return (
        "You are part of the Sovereign cognitive architecture. "
        "Treat the supplied runtime evidence as the only source of truth. "
        "Never invent file changes, tests, screenshots, traces, deployments, database writes or PR states. "
        "Missing evidence is a blocker. Never request or reveal secrets. "
        "Do not authorize merge or production deployment.\n\n"
        f"Repository skill contract:\n{skill}"
    )


def build_cognitive_swarm(model: str | None = None) -> CognitiveSwarm:
    agent_class, _ = _require_agents_sdk()
    selected_model = (model or os.getenv("SOVEREIGN_AGENTS_MODEL") or DEFAULT_MODEL).strip()
    if not selected_model:
        raise ValueError("A model identifier is required.")

    skill = _load_skill_instructions()
    base = _base_instructions(skill)

    specialists: list[Any] = []
    specialist_tools: list[Any] = []
    for role in SPECIALIST_ROLES[:max_active_specialists()]:
        specialist = agent_class(
            name=f"Sovereign {role.replace('_', ' ').title()} Specialist",
            model=selected_model,
            instructions=(
                f"{base}\n\n"
                f"You are the bounded {role} specialist. Work on exactly one assigned package. "
                "Never spawn agents, merge, deploy, read secrets, change global state, or write outside assigned files. "
                "Return evidence-backed findings and required actions only."
            ),
            output_type=WorkerReport,
        )
        specialists.append(specialist)
        specialist_tools.append(
            specialist.as_tool(
                tool_name=f"specialist_{role}",
                tool_description=f"Analyze one bounded {role} work package and return evidence-backed findings.",
                max_turns=6,
            )
        )

    dispatcher = agent_class(
        name=AGENTS[0].name,
        model=selected_model,
        instructions=(
            f"{base}\n\n"
            "Create one ordered six-item plan, one item for each fixed core worker role in manifest order. "
            "Do not perform worker tasks yourself. Identify required evidence, initial blockers, and specialists needed."
        ),
        output_type=DispatchPlan,
    )

    workers: list[Any] = []
    for contract in AGENTS[1:7]:
        worker_tools = specialist_tools if contract.role == "chat_cognitive" else []
        workers.append(agent_class(
            name=contract.name,
            model=selected_model,
            instructions=(
                f"{base}\n\n"
                f"Your fixed role is {contract.role}. Responsibility: {contract.responsibility} "
                f"Allowed zones: {', '.join(contract.allowed_zones)}. "
                "Analyze only your bounded domain. Return a WorkerReport. "
                "Use a specialist tool only for a clearly bounded package and keep orchestration ownership. "
                "Set blocked=true whenever evidence needed for a claim is absent. "
                "You may recommend exact changes, but you may not claim they were applied."
            ),
            tools=worker_tools,
            output_type=WorkerReport,
        ))

    judge = agent_class(
        name=AGENTS[-1].name,
        model=selected_model,
        instructions=(
            f"{base}\n\n"
            "You are the final evidence controller. You never edit files and never perform a release. "
            "Reject unsupported worker claims. draft_pr_ready may be true only when all required evidence "
            "is supplied, all checks are green, no blocker remains, and the result is explicitly Draft-PR-only. "
            "The first-loop verdict can never end the workflow; a second refinement loop is mandatory."
        ),
        output_type=JudgeVerdict,
    )

    swarm = CognitiveSwarm(
        dispatcher=dispatcher,
        workers=tuple(workers),
        specialists=tuple(specialists),
        judge=judge,
    )
    if swarm.agent_count < 8:
        raise RuntimeError("Sovereign core topology dropped below eight agents.")
    return swarm


def _worker_input(
    *,
    mission: str,
    evidence: str,
    plan: DispatchPlan,
    loop: int,
    role: str,
    prior_verdict: JudgeVerdict | None,
) -> str:
    previous = prior_verdict.model_dump_json() if prior_verdict else "none"
    return (
        f"Mission:\n{mission}\n\n"
        f"Fixed worker role: {role}\n"
        f"Double-loop pass: {loop}\n\n"
        f"Dispatcher plan:\n{plan.model_dump_json()}\n\n"
        f"Supplied runtime evidence:\n{evidence or '[no evidence supplied]'}\n\n"
        f"Prior judge verdict:\n{previous}\n"
    )


def _judge_input(
    *,
    mission: str,
    evidence: str,
    plan: DispatchPlan,
    loop: int,
    reports: list[WorkerReport],
) -> str:
    return (
        f"Mission:\n{mission}\n\n"
        f"Double-loop checkpoint: {loop}\n"
        f"Dispatcher plan:\n{plan.model_dump_json()}\n\n"
        f"Worker reports:\n{[report.model_dump() for report in reports]}\n\n"
        f"Independent supplied runtime evidence:\n{evidence or '[no evidence supplied]'}\n"
    )


async def run_cognitive_swarm(
    mission: str,
    *,
    evidence: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    normalized_mission = mission.strip()
    if not normalized_mission:
        raise ValueError("mission is required")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return {
            "ok": False,
            "status": "BLOCKED",
            "blocker": "OPENAI_API_KEY is not configured in the protected backend environment.",
            "manifest": manifest_payload(),
        }

    _, runner_class = _require_agents_sdk()
    swarm = build_cognitive_swarm(model=model)
    plan_result = await runner_class.run(
        swarm.dispatcher,
        f"Mission:\n{normalized_mission}\n\nRuntime evidence:\n{evidence or '[no evidence supplied]'}",
    )
    plan = plan_result.final_output
    if not isinstance(plan, DispatchPlan):
        raise RuntimeError("Dispatcher returned an invalid structured plan.")

    loop_payloads: list[dict[str, Any]] = []
    prior_verdict: JudgeVerdict | None = None

    for loop in (1, 2):
        reports: list[WorkerReport] = []
        for role, worker in zip(WORKER_ROLES, swarm.workers, strict=True):
            result = await runner_class.run(
                worker,
                _worker_input(
                    mission=normalized_mission,
                    evidence=evidence,
                    plan=plan,
                    loop=loop,
                    role=role,
                    prior_verdict=prior_verdict,
                ),
            )
            report = result.final_output
            if not isinstance(report, WorkerReport):
                raise RuntimeError(f"Worker {role} returned an invalid structured report.")
            report.role = role
            report.loop = loop
            reports.append(report)

        judge_result = await runner_class.run(
            swarm.judge,
            _judge_input(
                mission=normalized_mission,
                evidence=evidence,
                plan=plan,
                loop=loop,
                reports=reports,
            ),
        )
        verdict = judge_result.final_output
        if not isinstance(verdict, JudgeVerdict):
            raise RuntimeError("Judge returned an invalid structured verdict.")
        verdict.loop = loop
        if loop == 1:
            verdict.draft_pr_ready = False
            if "mandatory_second_loop" not in verdict.required_next_actions:
                verdict.required_next_actions.append("mandatory_second_loop")

        loop_payloads.append({
            "loop": loop,
            "workers": [report.model_dump() for report in reports],
            "judge": verdict.model_dump(),
        })
        prior_verdict = verdict

    final_verdict = prior_verdict
    if final_verdict is None:
        raise RuntimeError("The mandatory double loop did not produce a verdict.")

    return {
        "ok": final_verdict.draft_pr_ready and not final_verdict.blockers,
        "status": "READY_FOR_DRAFT_PR" if final_verdict.draft_pr_ready and not final_verdict.blockers else "BLOCKED",
        "manifest": manifest_payload(),
        "plan": plan.model_dump(),
        "loops": loop_payloads,
        "finalVerdict": final_verdict.model_dump(),
        "activeSpecialists": len(swarm.specialists),
        "approvalRequired": True,
        "autoMerge": False,
    }
