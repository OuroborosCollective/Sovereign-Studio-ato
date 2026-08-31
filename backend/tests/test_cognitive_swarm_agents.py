import asyncio
from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PRODUCTION_BACKEND = BACKEND.parent / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

import agent_runtime.cognitive_swarm_agents as swarm_module
from agent_runtime.cognitive_repository_tools import build_repository_fleet_bindings
from agent_runtime.llm_contract import LlmRouteBinding
from agent_runtime.cognitive_swarm_agents import (
    ALLOWED_LITELLM_MODEL_ALIASES,
    CognitiveSwarm,
    DEFAULT_MODEL,
    DispatchPlan,
    JudgeVerdict,
    MissionIntent,
    RELEASE_HUNT_SKILL_PATH,
    SKILL_PATH,
    SwarmExecutionError,
    WorkerReport,
    _parse_freellm_intent_text,
    agents_sdk_status,
    build_cognitive_swarm,
    classify_mission_intent,
    classify_swarm_exception,
    run_cognitive_swarm,
    run_free_single_agent,
)


def _route_binding(transport: str) -> LlmRouteBinding:
    return LlmRouteBinding(
        source_revision="a" * 40,
        route_id=f"{transport}-route",
        transport=transport,
        route_class="OPENROUTER_PAID" if transport == "openrouter" else "FREELLM_FREE",
        provider_model="openai/gpt-5.4-mini" if transport == "openrouter" else "free-model",
        route_snapshot_sha256="b" * 64,
        price_snapshot_sha256="c" * 64 if transport == "openrouter" else "0" * 64,
    )


def test_default_model_has_no_legacy_litellm_alias() -> None:
    assert DEFAULT_MODEL == ""
    assert ALLOWED_LITELLM_MODEL_ALIASES == frozenset()
    production_agents = (
        PRODUCTION_BACKEND / "agent_runtime" / "cognitive_swarm_agents.py"
    ).read_text("utf-8")
    assert "ensure_openai_runtime_key" not in production_agents
    assert "http://litellm:4000" not in production_agents
    assert "AGENTS_DIRECT_OPENROUTER_ROUTE_REQUIRED" in production_agents


def test_agents_sdk_topology_contains_eight_core_agents_plus_bounded_specialists_or_fails_closed() -> None:
    kwargs = {
        "main_model": "openai/gpt-5.4-mini",
        "agent_model": "openai/gpt-5.4-mini",
        "main_run_config": object(),
        "agent_run_config": object(),
    }
    status = agents_sdk_status()
    if status["available"] is False:
        with pytest.raises(RuntimeError, match="openai-agents"):
            build_cognitive_swarm(**kwargs)
        return

    swarm = build_cognitive_swarm(**kwargs)
    assert swarm.agent_count == 12
    assert swarm.dispatcher.name == "The Dispatcher"
    assert len(swarm.workers) == 6
    assert len(swarm.specialists) == 4
    assert swarm.judge.name == "The Judge"


def test_swarm_build_rejects_missing_database_resolved_run_config() -> None:
    with pytest.raises(ValueError, match="Database-resolved direct route RunConfig"):
        build_cognitive_swarm(model="openai/gpt-5.4-mini")


def test_stage_observer_reports_each_core_agent_in_both_loops(monkeypatch) -> None:
    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (object(), object()))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="openai/gpt-5.4-mini",
            transport="openrouter",
            run_config=object(),
        ),
    )

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

    def fake_build(**kwargs):
        return fake_swarm

    async def fake_run_stage(runner_class, agent, prompt, *, stage, **kwargs):
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
            main_route={"id": "paid-main"},
            agent_route={"id": "paid-main"},
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
    assert all(event["status"] in {"RUNNING", "VERIFYING", "COMPLETED", "BLOCKED"} for event in events)
    assert sum(event["status"] == "BLOCKED" for event in events) == 12
    assert all("prompt" not in event and "output" not in event for event in events)


def test_repository_workers_follow_persisted_serial_fleet_lanes(monkeypatch) -> None:
    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (object(), object()))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="openai/gpt-5.4-mini",
            transport="openrouter",
            run_config=object(),
        ),
    )
    dispatcher = object()
    workers = tuple(object() for _ in range(6))
    judge = object()
    fake_swarm = CognitiveSwarm(
        dispatcher=dispatcher,
        workers=workers,
        specialists=(),
        judge=judge,
    )
    worker_roles = {
        id(worker): role
        for worker, role in zip(workers, swarm_module.WORKER_ROLES, strict=True)
    }
    monkeypatch.setattr(swarm_module, "build_cognitive_swarm", lambda **kwargs: fake_swarm)

    worker_order: list[str] = []

    async def fake_run_stage(runner_class, agent, prompt, *, stage, **kwargs):
        if agent is dispatcher:
            return SimpleNamespace(final_output=DispatchPlan(
                mission="Inspect Fleet binding.",
                ordered_work=[f"work-{index}" for index in range(6)],
                required_evidence=["fleet plan"],
                initial_blockers=[],
            ))
        if agent is judge:
            return SimpleNamespace(final_output=JudgeVerdict(
                loop=0,
                verdict="blocked",
                blockers=["runtime evidence remains bounded"],
                accepted_evidence=[],
                rejected_claims=[],
                required_next_actions=["retain evidence"],
                draft_pr_ready=False,
                human_approval_required=False,
            ))
        role = worker_roles[id(agent)]
        worker_order.append(role)
        assert "Repository Fleet binding (immutable for this pass):" in prompt
        return SimpleNamespace(final_output=WorkerReport(
            role=role,
            loop=0,
            status="blocked",
            findings=["No unbounded repository action was taken."],
            required_actions=["preserve Fleet evidence"],
            evidence_observed=["Fleet lane binding"],
            evidence_missing=[],
            blocked=True,
        ))

    monkeypatch.setattr(swarm_module, "_run_stage", fake_run_stage)
    bindings = build_repository_fleet_bindings(
        run_id="run-test-runtime",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        workspace_id="agent-test-runtime",
        workspace_branch="main",
        base_revision="a" * 40,
        task_ids_by_agent={role: f"task-{role}" for role in swarm_module.WORKER_ROLES},
    )
    admitted_lanes: list[tuple[str, tuple[str, ...]]] = []
    lane_transition_journal: list[tuple[str, str]] = []

    @contextmanager
    def fleet_lane_guard(lane_id: str, roles: tuple[str, ...]):
        admitted_lanes.append((lane_id, roles))
        lane_transition_journal.append(("guard_entered", lane_id))
        try:
            yield
        finally:
            lane_transition_journal.append(("guard_exited", lane_id))

    events: list[dict[str, object]] = []

    def observe(event: dict[str, object]) -> None:
        if event["eventType"] in {"fleet_lane_started", "fleet_lane_completed"}:
            lane_transition_journal.append((str(event["eventType"]), str(event["fleetLaneId"])))
        events.append(event)

    result = asyncio.run(run_cognitive_swarm(
        "Inspect the persisted Fleet lanes.",
        main_route={"id": "paid-main"},
        agent_route={"id": "paid-main"},
        repository_tool_factory=lambda role: [],
        fleet_plan=bindings.plan,
        fleet_task_ids_by_role=bindings.task_ids_by_role,
        fleet_assignments_by_role=bindings.assignments_by_role,
        fleet_lane_guard=fleet_lane_guard,
        fleet_head_readback=lambda: "a" * 40,
        stage_observer=observe,
    ))

    expected_roles = [
        next(
            role
            for role, task_id in bindings.task_ids_by_role.items()
            if task_id == lane.task_ids[0]
        )
        for lane in bindings.plan.lanes
    ]
    assert worker_order == expected_roles * 2
    assert admitted_lanes == [
        (lane.lane_id, (role,))
        for lane in bindings.plan.lanes
        for role in [next(
            role
            for role, task_id in bindings.task_ids_by_role.items()
            if task_id == lane.task_ids[0]
        )]
    ] * 2
    assert result["fleetPlanHash"] == bindings.plan.plan_hash
    assert result["fleetTaskIdsByRole"] == bindings.task_ids_by_role
    assert all(lane.parallel_safe is False for lane in bindings.plan.lanes)
    lane_events = [event for event in events if event["eventType"] == "fleet_lane_started"]
    assert len(lane_events) == len(bindings.plan.lanes) * 2
    assert all(event["fleetPlanHash"] == bindings.plan.plan_hash for event in lane_events)
    assert lane_transition_journal == [
        transition
        for _loop in range(2)
        for lane in bindings.plan.lanes
        for transition in (
            ("guard_entered", lane.lane_id),
            ("fleet_lane_started", lane.lane_id),
            ("fleet_lane_completed", lane.lane_id),
            ("guard_exited", lane.lane_id),
        )
    ]


def test_repository_workers_fail_closed_without_a_persisted_fleet_plan() -> None:
    with pytest.raises(SwarmExecutionError) as captured:
        asyncio.run(run_cognitive_swarm(
            "Inspect the repository execution boundary.",
            main_route={"id": "paid-main"},
            agent_route={"id": "paid-main"},
            repository_tool_factory=lambda role: [],
        ))

    assert captured.value.family == "FLEET_PLAN_REQUIRED_FOR_REPOSITORY_WORKERS"
    assert captured.value.next_action == "BUILD_AND_PERSIST_A_HASH_BOUND_FLEET_PLAN"


def test_explicit_mission_completion_finishes_without_approval(monkeypatch) -> None:
    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (object(), object()))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="openai/gpt-5.4-mini",
            transport="openrouter",
            run_config=object(),
        ),
    )

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

    monkeypatch.setattr(swarm_module, "build_cognitive_swarm", lambda **kwargs: fake_swarm)

    async def fake_run_stage(runner_class, agent, prompt, *, stage, **kwargs):
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
                required_next_actions=["Switch to the next distinct error family."],
                draft_pr_ready=False,
                mission_complete=True,
                human_approval_required=False,
                hunt_outcome="NULLFIND",
                error_family="functional-chat-cognitive-action",
                next_error_family="agents-sdk-recovery-persistence",
                nullfind_confirmed=True,
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

    result = asyncio.run(run_cognitive_swarm(
        "Confirm the release-readiness nullfund.",
        main_route={"id": "paid-main"},
        agent_route={"id": "paid-main"},
    ))

    assert result["ok"] is True
    assert result["status"] == "COMPLETED"
    assert result["approvalRequired"] is False
    assert result["finalVerdict"]["verdict"] == "nullfund_confirmed"
    assert result["finalVerdict"]["hunt_outcome"] == "NULLFIND"
    assert result["finalVerdict"]["nullfind_confirmed"] is True


def test_freellm_intent_parser_normalizes_plain_text_contract() -> None:
    intent = _parse_freellm_intent_text(
        "MODE=repository_execution\nGOAL=Patch the verified workspace and run tests.",
        "Fallback goal.",
    )

    assert intent.mode == "repository_execution"
    assert intent.normalized_goal == "Patch the verified workspace and run tests."
    assert intent.requires_online_tools is True
    assert intent.requires_repository_workspace is True
    assert intent.learning_scope == []
    assert intent.confidence == 0.0


def test_freellm_intent_parser_accepts_fenced_json_without_semantic_guessing() -> None:
    intent = _parse_freellm_intent_text(
        '```json\n{"mode":"conversation","normalized_goal":"Explain the current route."}\n```',
        "Fallback goal.",
    )

    assert intent.mode == "conversation"
    assert intent.normalized_goal == "Explain the current route."
    assert intent.requires_online_tools is False
    assert intent.requires_repository_workspace is False


def test_freellm_intent_parser_rejects_unbounded_natural_language() -> None:
    with pytest.raises(SwarmExecutionError) as captured:
        _parse_freellm_intent_text(
            "I think the user probably wants a repository change.",
            "Fallback goal.",
        )

    assert captured.value.family == "AGENTS_INTENT_TEXT_INVALID"
    assert captured.value.next_action == "RETRY_WITH_PLAIN_TEXT_INTENT_CONTRACT"


def test_freellm_intent_router_uses_plain_text_without_output_schema(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.model = kwargs["model"]

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            return SimpleNamespace(
                final_output="MODE=read_only_analysis\nGOAL=Inspect the persisted route evidence."
            )

    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (FakeAgent, FakeRunner))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="auto",
            transport="freellm",
            run_config=object(),
            route_binding=_route_binding("freellm"),
        ),
    )

    intent = asyncio.run(classify_mission_intent(
        "Inspect the persisted route evidence.",
        model="auto",
        route={"id": "free-auto"},
    ))

    assert intent.mode == "read_only_analysis"
    assert intent.normalized_goal == "Inspect the persisted route evidence."
    assert "output_type" not in captured
    assert "MODE=<conversation|read_only_analysis|repository_execution>" in str(captured["instructions"])
    receipt = intent.contract_receipt()
    assert receipt["verdict"] == "VERIFIED"
    assert receipt["verificationScope"] == "SCHEMA_ONLY"
    assert receipt["sourceRevision"] == "a" * 40
    assert len(receipt["requestSha256"]) == 64
    assert len(receipt["receiptSha256"]) == 64


def test_paid_intent_router_keeps_structured_output_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = MissionIntent(
        mode="read_only_analysis",
        normalized_goal="Inspect the paid route.",
        requires_online_tools=True,
        requires_repository_workspace=False,
        learning_scope=[],
        confidence=1.0,
    )

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.model = kwargs["model"]

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            return SimpleNamespace(final_output=expected)

    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (FakeAgent, FakeRunner))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="openai/gpt-5.4-mini",
            transport="openrouter",
            run_config=object(),
            route_binding=_route_binding("openrouter"),
        ),
    )

    intent = asyncio.run(classify_mission_intent(
        "Inspect the paid route.",
        model="openai/gpt-5.4-mini",
        route={"id": "paid-main"},
    ))

    assert intent is expected
    assert captured["output_type"] is MissionIntent
    receipt = intent.contract_receipt()
    assert receipt["verdict"] == "VERIFIED"
    assert receipt["verificationScope"] == "SCHEMA_ONLY"
    assert receipt["sourceRevision"] == "a" * 40
    assert len(receipt["routeBindingSha256"]) == 64


def test_free_single_agent_normalizes_plain_text_without_structured_output(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.model = kwargs["model"]

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            captured["prompt"] = prompt
            return SimpleNamespace(final_output="  FreeLLM plain-text answer.  ")

    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (FakeAgent, FakeRunner))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="auto",
            transport="freellm",
            run_config=object(),
        ),
    )
    intent = MissionIntent(
        mode="read_only_analysis",
        normalized_goal="Inspect the current route state.",
        requires_online_tools=True,
        requires_repository_workspace=False,
        learning_scope=[],
        confidence=1.0,
    )

    result = asyncio.run(run_free_single_agent(
        "Inspect the current route state.",
        model="auto",
        intent=intent,
        route={"id": "free-auto"},
    ))

    assert result["ok"] is True
    assert result["status"] == "COMPLETED"
    assert result["result"]["mode"] == "read_only_analysis"
    assert result["result"]["assistant_text"] == "FreeLLM plain-text answer."
    assert result["result"]["response_truncated"] is False
    assert "output_type" not in captured
    assert "do not emit JSON or a schema wrapper" in str(captured["instructions"])
    assert "Validated mission mode: read_only_analysis" in str(captured["prompt"])


def test_free_single_agent_injects_agent_zero_capability_tool_without_replacing_repository_tools(monkeypatch) -> None:
    captured: dict[str, object] = {}
    repository_marker = object()
    capability_marker = object()

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.model = kwargs["model"]

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            return SimpleNamespace(final_output="Capability-aware answer.")

    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (FakeAgent, FakeRunner))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="auto",
            transport="freellm",
            run_config=object(),
        ),
    )
    intent = MissionIntent(
        mode="read_only_analysis",
        normalized_goal="Inspect a rendered page using the capability boundary.",
        requires_online_tools=True,
        requires_repository_workspace=False,
        learning_scope=[],
        confidence=1.0,
    )

    result = asyncio.run(run_free_single_agent(
        "Inspect a rendered page using the capability boundary.",
        model="auto",
        intent=intent,
        route={"id": "free-auto"},
        repository_tool_factory=lambda role: [repository_marker] if role == "free_single_agent" else [],
        capability_tool_factory=lambda role: [capability_marker] if role == "free_single_agent" else [],
    ))

    assert result["ok"] is True
    assert captured["tools"] == [repository_marker, capability_marker]
    assert "Agent Zero capability tools" in str(captured["instructions"])
    assert "non-authoritative external evidence" in str(captured["instructions"])


def test_free_single_agent_rejects_empty_plain_text(monkeypatch) -> None:
    class FakeAgent:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            return SimpleNamespace(final_output="   ")

    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (FakeAgent, FakeRunner))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="auto",
            transport="freellm",
            run_config=object(),
        ),
    )
    intent = MissionIntent(
        mode="conversation",
        normalized_goal="Say hello.",
        requires_online_tools=False,
        requires_repository_workspace=False,
        learning_scope=[],
        confidence=1.0,
    )

    with pytest.raises(SwarmExecutionError) as captured:
        asyncio.run(run_free_single_agent(
            "Say hello.",
            model="auto",
            intent=intent,
            route={"id": "free-auto"},
        ))

    assert captured.value.family == "AGENTS_TEXT_OUTPUT_INVALID"
    assert captured.value.next_action == "RETRY_WITH_PLAIN_TEXT_OUTPUT"


def test_provider_failures_are_classified_without_raw_error_text() -> None:
    class ProviderFailure(Exception):
        status_code = 429
        request_id = "req-safe-123"

    failure = classify_swarm_exception(
        ProviderFailure("sensitive provider message must never persist"),
        stage="dispatcher",
        transport="openrouter",
    )

    assert isinstance(failure, SwarmExecutionError)
    assert failure.family == "OPENROUTER_RATE_LIMITED"
    assert failure.stage == "dispatcher"
    assert failure.retryable is True
    assert failure.http_status == 429
    assert failure.request_id == "req-safe-123"
    payload = failure.safe_payload()
    assert payload["rawErrorPersisted"] is False
    assert "sensitive provider message" not in str(payload)


def test_swarm_build_failure_is_classified_before_first_model_call(monkeypatch) -> None:
    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (object(), object()))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="openai/gpt-5.4-mini",
            transport="openrouter",
            run_config=object(),
        ),
    )

    def fail_build(**kwargs):
        raise TypeError("raw build detail must not persist")

    monkeypatch.setattr(swarm_module, "build_cognitive_swarm", fail_build)

    with pytest.raises(SwarmExecutionError) as captured:
        asyncio.run(run_cognitive_swarm(
            "Inspect bounded runtime evidence.",
            main_route={"id": "paid-main"},
            agent_route={"id": "paid-main"},
        ))

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
    release_hunt = RELEASE_HUNT_SKILL_PATH.read_text("utf-8")
    bundled = swarm_module._load_skill_instructions()

    assert content.startswith("---")
    assert "name: sovereign-cognitive-architecture" in content
    assert "Never auto-merge" in content
    assert "Missing evidence is a blocker" in content
    assert release_hunt.startswith("---")
    assert "name: sovereign-release-ready-error-family-hunt" in release_hunt
    assert "three immediately consecutive NULLFIND runs" in release_hunt
    assert "isActiveBlocker=true" in release_hunt
    assert content in bundled
    assert release_hunt.strip() in bundled


def test_release_hunt_verdict_fields_are_structured_and_default_closed() -> None:
    verdict = JudgeVerdict(
        loop=2,
        verdict="blocked",
        blockers=["missing runtime evidence"],
        accepted_evidence=[],
        rejected_claims=[],
        required_next_actions=["provide evidence"],
        draft_pr_ready=False,
    )

    assert verdict.hunt_outcome == ""
    assert verdict.error_family == ""
    assert verdict.next_error_family == ""
    assert verdict.nullfind_confirmed is False


def test_production_image_source_contains_the_same_cognitive_skill_bundle() -> None:
    production_skill = (
        PRODUCTION_BACKEND
        / "agent_runtime"
        / "skills"
        / "sovereign-cognitive-architecture"
        / "SKILL.md"
    )
    production_release_hunt_skill = (
        PRODUCTION_BACKEND
        / "agent_runtime"
        / "skills"
        / "sovereign-release-ready-error-family-hunt"
        / "SKILL.md"
    )
    assert production_skill.read_bytes() == SKILL_PATH.read_bytes()
    assert production_release_hunt_skill.read_bytes() == RELEASE_HUNT_SKILL_PATH.read_bytes()


def test_swarm_fails_closed_without_database_resolved_openrouter_route() -> None:
    with pytest.raises(SwarmExecutionError) as captured:
        asyncio.run(run_cognitive_swarm("Inspect the current runtime evidence."))
    assert captured.value.family == "AGENTS_DIRECT_OPENROUTER_ROUTE_REQUIRED"
    assert captured.value.next_action == "RESOLVE_DATABASE_OPENROUTER_ROUTE"
    assert captured.value.retryable is False
