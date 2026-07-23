import asyncio
import secrets
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PRODUCTION_BACKEND = BACKEND.parent / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

import agent_runtime.cognitive_swarm_agents as swarm_module
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


def _configure_internal_litellm(monkeypatch, tmp_path: Path) -> None:
    owner_root = tmp_path / "owner-secrets"
    owner_root.mkdir(mode=0o700)
    key_path = owner_root / "litellm_master_key.txt"
    key_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    key_path.chmod(0o600)
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(owner_root))
    monkeypatch.setenv("LITELLM_MASTER_KEY_FILE", str(key_path))
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")
    assert swarm_module.ensure_openai_runtime_key() is True


def test_default_model_uses_the_internal_litellm_alias() -> None:
    assert DEFAULT_MODEL == "sovereign-fast"
    assert ALLOWED_LITELLM_MODEL_ALIASES == frozenset({"sovereign-fast"})
    production_agents = (
        PRODUCTION_BACKEND / "agent_runtime" / "cognitive_swarm_agents.py"
    ).read_text("utf-8")
    assert "DEFAULT_MODEL: Final[str] = AGENTS_LITELLM_ALIAS" in production_agents
    assert "ALLOWED_LITELLM_MODEL_ALIASES" in production_agents


def test_agents_sdk_topology_contains_eight_core_agents_plus_bounded_specialists_or_fails_closed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    status = agents_sdk_status()
    if status["available"] is False:
        with pytest.raises(RuntimeError, match="openai-agents"):
            build_cognitive_swarm(model=DEFAULT_MODEL)
        return

    _configure_internal_litellm(monkeypatch, tmp_path)
    swarm = build_cognitive_swarm(model=DEFAULT_MODEL)
    assert swarm.agent_count == 12
    assert swarm.dispatcher.name == "The Dispatcher"
    assert len(swarm.workers) == 6
    assert len(swarm.specialists) == 4
    assert swarm.judge.name == "The Judge"


def test_swarm_build_rejects_direct_provider_model_identifiers() -> None:
    with pytest.raises(ValueError, match="LiteLLM model alias"):
        build_cognitive_swarm(model="direct-provider-model")


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
    assert all(event["status"] in {"RUNNING", "VERIFYING", "COMPLETED", "BLOCKED"} for event in events)
    assert sum(event["status"] == "BLOCKED" for event in events) == 12
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

    result = asyncio.run(run_cognitive_swarm("Confirm the release-readiness nullfund."))

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
        ),
    )

    intent = asyncio.run(classify_mission_intent(
        "Inspect the paid route.",
        model="openai/gpt-5.4-mini",
        route={"id": "paid-main"},
    ))

    assert intent is expected
    assert captured["output_type"] is MissionIntent


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


def test_legacy_swarm_fails_closed_without_litellm_compatibility_key(
    monkeypatch,
    tmp_path: Path,
) -> None:
    owner_root = tmp_path / "missing-owner-secrets"
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(owner_root))
    monkeypatch.setenv(
        "LITELLM_MASTER_KEY_FILE",
        str(owner_root / "litellm_master_key.txt"),
    )
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")
    result = asyncio.run(run_cognitive_swarm("Inspect the current runtime evidence."))
    assert result["ok"] is False
    assert result["status"] == "BLOCKED"
    assert "Legacy-LiteLLM compatibility key" in result["blocker"]
    assert result["manifest"]["agentCount"] == 20
    assert result["manifest"]["coreAgentCount"] == 8
    assert result["manifest"]["maxActiveSpecialists"] == 4
