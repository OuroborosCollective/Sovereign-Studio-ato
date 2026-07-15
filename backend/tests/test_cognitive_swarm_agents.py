import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PRODUCTION_BACKEND = BACKEND.parent / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

import agent_runtime.cognitive_swarm_agents as swarm_module
from agent_runtime.cognitive_swarm_agents import (
    CognitiveSwarm,
    DEFAULT_MODEL,
    DispatchPlan,
    JudgeVerdict,
    SKILL_PATH,
    SwarmExecutionError,
    WorkerReport,
    agents_sdk_status,
    build_cognitive_swarm,
    classify_swarm_exception,
    run_cognitive_swarm,
)


def test_default_model_uses_the_agents_sdk_low_latency_baseline() -> None:
    assert DEFAULT_MODEL == "gpt-5.4-mini"
    production_agents = (
        PRODUCTION_BACKEND / "agent_runtime" / "cognitive_swarm_agents.py"
    ).read_text("utf-8")
    assert 'DEFAULT_MODEL: Final[str] = "gpt-5.4-mini"' in production_agents


def test_agents_sdk_topology_contains_eight_core_agents_plus_bounded_specialists_or_fails_closed() -> None:
    status = agents_sdk_status()
    if status["available"] is False:
        with pytest.raises(RuntimeError, match="openai-agents"):
            build_cognitive_swarm(model="gpt-5.6")
        return

    swarm = build_cognitive_swarm(model="gpt-5.6")
    assert swarm.agent_count == 12
    assert swarm.dispatcher.name == "The Dispatcher"
    assert len(swarm.workers) == 6
    assert len(swarm.specialists) == 4
    assert swarm.judge.name == "The Judge"


def test_stage_observer_reports_each_core_agent_in_both_loops(monkeypatch) -> None:
    monkeypatch.setattr(swarm_module, "ensure_openai_runtime_key", lambda: True)
    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (object(), object()))

    dispatcher = object()
    workers = tuple(object() for _ in range(6))
    judge = object()
    fake_swarm = CognitiveSwarm(
        dispatcher=dispatcher,
        workers=workers,
        specialists=(),
        judge=judge,
    )
    worker_roles = {id(worker): role for worker, role in zip(workers, swarm_module.WORKER_ROLES, strict=True)}

    def fake_build(*, model=None):
        return fake_swarm

    async def fake_run_stage(runner_class, agent, prompt, *, stage):
        if agent is dispatcher:
            output = DispatchPlan(
                mission="Inspect evidence.",
                ordered_work=[f"work-{index}" for index in range(6)],
                required_evidence=["runtime evidence"],
                initial_blockers=["missing evidence"],
            )
        elif agent is judge:
            output = JudgeVerdict(
                loop=0,
                verdict="blocked",
                blockers=["missing evidence"],
                accepted_evidence=[],
                rejected_claims=[],
                required_next_actions=["provide evidence"],
                draft_pr_ready=False,
                human_approval_required=False,
            )
        else:
            role = worker_roles[id(agent)]
            output = WorkerReport(
                role=role,
                loop=0,
                status="blocked",
                findings=["Evidence is incomplete."],
                required_actions=["Provide evidence."],
                evidence_observed=[],
                evidence_missing=["runtime evidence"],
                blocked=True,
            )
        return SimpleNamespace(final_output=output)

    monkeypatch.setattr(swarm_module, "build_cognitive_swarm", fake_build)
    monkeypatch.setattr(swarm_module, "_run_stage", fake_run_stage)
    events: list[dict[str, object]] = []

    result = asyncio.run(
        run_cognitive_swarm(
            "Inspect bounded runtime evidence.",
            stage_observer=events.append,
        )
    )

    assert result["status"] == "BLOCKED"
    assert len(events) == 30
    assert events[0]["agentId"] == "dispatcher"
    assert events[0]["eventType"] == "agent_started"
    assert events[-1]["agentId"] == "judge"
    assert events[-1]["eventType"] == "agent_completed"
    for role in swarm_module.WORKER_ROLES:
        assert sum(event["agentId"] == role for event in events) == 4
    assert sum(event["agentId"] == "judge" for event in events) == 4
    assert all(event["status"] in {"RUNNING", "VERIFYING", "COMPLETED"} for event in events)
    assert all("prompt" not in event and "output" not in event for event in events)


def test_explicit_mission_completion_finishes_without_approval(monkeypatch) -> None:
    monkeypatch.setattr(swarm_module, "ensure_openai_runtime_key", lambda: True)
    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (object(), object()))

    dispatcher = object()
    workers = tuple(object() for _ in range(6))
    judge = object()
    fake_swarm = CognitiveSwarm(
        dispatcher=dispatcher,
        workers=workers,
        specialists=(),
        judge=judge,
    )
    worker_roles = {id(worker): role for worker, role in zip(workers, swarm_module.WORKER_ROLES, strict=True)}

    monkeypatch.setattr(swarm_module, "build_cognitive_swarm", lambda *, model=None: fake_swarm)

    async def fake_run_stage(runner_class, agent, prompt, *, stage):
        if agent is dispatcher:
            output = DispatchPlan(
                mission="Confirm the release-readiness nullfund.",
                ordered_work=[f"work-{index}" for index in range(6)],
                required_evidence=["verified release evidence"],
                initial_blockers=[],
            )
        elif agent is judge:
            output = JudgeVerdict(
                loop=0,
                verdict="nullfund_confirmed",
                blockers=[],
                accepted_evidence=["All required release gates are green."],
                rejected_claims=[],
                required_next_actions=["Document the nullfund."],
                draft_pr_ready=False,
                mission_complete=True,
                human_approval_required=False,
            )
        else:
            role = worker_roles[id(agent)]
            output = WorkerReport(
                role=role,
                loop=0,
                status="nullfund_confirmed",
                findings=["No evidenced defect remains."],
                required_actions=[],
                evidence_observed=["verified release evidence"],
                evidence_missing=[],
                blocked=False,
            )
        return SimpleNamespace(final_output=output)

    monkeypatch.setattr(swarm_module, "_run_stage", fake_run_stage)

    result = asyncio.run(run_cognitive_swarm("Confirm the release-readiness nullfund."))

    assert result["ok"] is True
    assert result["status"] == "COMPLETED"
    assert result["approvalRequired"] is False
    assert result["finalVerdict"]["verdict"] == "nullfund_confirmed"
    assert result["finalVerdict"]["mission_complete"] is True
    assert result["finalVerdict"]["blockers"] == []


def test_nullfund_label_cannot_override_a_real_blocker() -> None:
    verdict = JudgeVerdict(
        loop=2,
        verdict="nullfund_confirmed",
        blockers=["Runtime evidence is still missing."],
        accepted_evidence=[],
        rejected_claims=[],
        required_next_actions=["Provide the missing runtime evidence."],
        draft_pr_ready=False,
        mission_complete=True,
        human_approval_required=False,
    )

    assert swarm_module._resolved_swarm_status(verdict) == (False, "BLOCKED")


def test_provider_failures_are_classified_without_raw_error_text() -> None:
    class ProviderFailure(Exception):
        status_code = 429
        request_id = "req-safe-123"

    failure = classify_swarm_exception(
        ProviderFailure("sensitive provider message must never persist"),
        stage="dispatcher",
    )

    assert isinstance(failure, SwarmExecutionError)
    assert failure.family == "OPENAI_RATE_LIMITED"
    assert failure.stage == "dispatcher"
    assert failure.retryable is True
    assert failure.http_status == 429
    assert failure.request_id == "req-safe-123"
    payload = failure.safe_payload()
    assert payload["rawErrorPersisted"] is False
    assert "sensitive provider message" not in str(payload)


def test_swarm_build_failure_is_classified_before_first_model_call(monkeypatch) -> None:
    monkeypatch.setattr(swarm_module, "ensure_openai_runtime_key", lambda: True)
    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (object(), object()))

    def fail_build(*, model=None):
        raise TypeError("raw build detail must not persist")

    monkeypatch.setattr(swarm_module, "build_cognitive_swarm", fail_build)

    with pytest.raises(SwarmExecutionError) as captured:
        asyncio.run(run_cognitive_swarm("Inspect bounded runtime evidence."))

    failure = captured.value
    assert failure.stage == "swarm-build"
    assert failure.family == "AGENTS_SDK_EXECUTION_FAILED"
    assert failure.error_type == "TypeError"
    assert "raw build detail" not in str(failure.safe_payload())


def test_local_runtime_file_errors_are_not_misclassified_as_provider_404() -> None:
    failure = classify_swarm_exception(
        FileNotFoundError("missing runtime asset path must not persist"),
        stage="swarm-build",
    )

    assert failure.family == "AGENTS_RUNTIME_ASSET_MISSING"
    assert failure.next_action == "VERIFY_PRODUCTION_RUNTIME_ASSETS"
    assert failure.retryable is False
    assert failure.http_status is None
    assert "missing runtime asset path" not in str(failure.safe_payload())


def test_structured_output_failure_has_bounded_recovery_family() -> None:
    ModelBehaviorError = type("ModelBehaviorError", (Exception,), {})
    failure = classify_swarm_exception(ModelBehaviorError("raw output"), stage="loop-1:judge")
    assert failure.family == "AGENTS_STRUCTURED_OUTPUT_INVALID"
    assert failure.next_action == "RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS"
    assert failure.safe_payload()["failureStage"] == "loop-1:judge"


def test_routes_persist_only_bounded_failure_metadata() -> None:
    routes = (BACKEND / "agent_runtime" / "cognitive_swarm_routes.py").read_text("utf-8")

    assert "SwarmExecutionError" in routes
    assert "failure = exc.safe_payload()" in routes
    assert '"rawErrorPersisted": False' in routes
    assert '"failureStage": failure_stage' in routes
    assert '"blocker": failure_family' in routes
    assert "evidence_payload=failure" in routes
    assert "family=failure_family" in routes
    assert "Agents SDK execution failed without a validated final verdict." not in routes
    agents = (BACKEND / "agent_runtime" / "cognitive_swarm_agents.py").read_text("utf-8")
    assert 'stage="swarm-build"' in agents
    assert 'stage="dispatcher-output"' in agents
    assert 'stage=f"loop-{loop}:worker-output:{role}"' in agents
    assert 'stage=f"loop-{loop}:judge-output"' in agents


def test_base_instructions_define_released_lease_and_absent_pr_semantics() -> None:
    instructions = swarm_module._base_instructions("bounded skill")

    assert "lease_active=false" in instructions
    assert "the lease is released" in instructions
    assert "absent open PR is informational" in instructions
    assert "never invent a PR continuation blocker" in instructions


def test_repo_local_skill_bundle_is_present_and_bounded() -> None:
    content = SKILL_PATH.read_text("utf-8")
    assert content.startswith("---")
    assert "name: sovereign-cognitive-architecture" in content
    assert "Never auto-merge" in content
    assert "Missing evidence is a blocker" in content


def test_production_image_source_contains_the_same_cognitive_skill_bundle() -> None:
    production_skill = (
        PRODUCTION_BACKEND
        / "agent_runtime"
        / "skills"
        / "sovereign-cognitive-architecture"
        / "SKILL.md"
    )
    assert production_skill.read_bytes() == SKILL_PATH.read_bytes()


def test_swarm_fails_closed_without_openai_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = asyncio.run(run_cognitive_swarm("Inspect the current runtime evidence."))
    assert result["ok"] is False
    assert result["status"] == "BLOCKED"
    assert "OPENAI_API_KEY" in result["blocker"]
    assert result["manifest"]["agentCount"] == 20
    assert result["manifest"]["coreAgentCount"] == 8
    assert result["manifest"]["maxActiveSpecialists"] == 4
