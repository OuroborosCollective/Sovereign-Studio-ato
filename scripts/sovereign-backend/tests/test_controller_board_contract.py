from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
CONTROLLER = BACKEND / "controller_board.py"
APP = BACKEND / "app.py"
DOCKERFILE = BACKEND / "Dockerfile"
RUN_STORE = BACKEND / "agent_runtime" / "cognitive_run_store.py"
JOB_STORE = BACKEND / "agent_runtime" / "job_store.py"
JOB_ROUTES = BACKEND / "agent_runtime" / "routes.py"
PATTERN_GATEWAY = BACKEND / "agent_runtime" / "pattern_gateway.py"
SWARM_ROUTES = BACKEND / "agent_runtime" / "cognitive_swarm_routes.py"
A2A_ADAPTER = BACKEND / "agent_runtime" / "a2a_adapter.py"
A2A_ROUTES = BACKEND / "agent_runtime" / "a2a_routes.py"
SWARM_AGENTS = BACKEND / "agent_runtime" / "cognitive_swarm_agents.py"
REPOSITORY_TOOLS = BACKEND / "agent_runtime" / "cognitive_repository_tools.py"
TOOL_EVENTS = BACKEND / "agent_runtime" / "tool_events.py"
FILE_TOOL = BACKEND / "agent_runtime" / "tools" / "file_tool.py"
WORKFLOW = BACKEND.parents[1] / ".github" / "workflows" / "sovereign-agent-backend.yml"
CI_WORKFLOW = BACKEND.parents[1] / ".github" / "workflows" / "ci.yml"
CANONICAL_RUNTIME = BACKEND.parents[1] / "backend" / "agent_runtime"
CANONICAL_RUN_STORE = CANONICAL_RUNTIME / "cognitive_run_store.py"
CANONICAL_JOB_STORE = CANONICAL_RUNTIME / "job_store.py"
CANONICAL_JOB_ROUTES = CANONICAL_RUNTIME / "routes.py"
CANONICAL_PATTERN_GATEWAY = CANONICAL_RUNTIME / "pattern_gateway.py"
CANONICAL_SWARM_ROUTES = CANONICAL_RUNTIME / "cognitive_swarm_routes.py"
CANONICAL_A2A_ADAPTER = CANONICAL_RUNTIME / "a2a_adapter.py"
CANONICAL_A2A_ROUTES = CANONICAL_RUNTIME / "a2a_routes.py"
CANONICAL_SWARM_AGENTS = CANONICAL_RUNTIME / "cognitive_swarm_agents.py"
CANONICAL_REPOSITORY_TOOLS = CANONICAL_RUNTIME / "cognitive_repository_tools.py"
CANONICAL_TOOL_EVENTS = CANONICAL_RUNTIME / "tool_events.py"
CANONICAL_FILE_TOOL = CANONICAL_RUNTIME / "tools" / "file_tool.py"


def test_controller_module_has_valid_python_syntax() -> None:
    for path in (CONTROLLER, RUN_STORE, JOB_STORE, JOB_ROUTES, PATTERN_GATEWAY, SWARM_ROUTES, A2A_ADAPTER, A2A_ROUTES, SWARM_AGENTS, REPOSITORY_TOOLS, TOOL_EVENTS, FILE_TOOL):
        ast.parse(path.read_text("utf-8"), filename=str(path))


def test_canonical_and_deployed_agent_runtime_are_byte_identical() -> None:
    assert RUN_STORE.read_bytes() == CANONICAL_RUN_STORE.read_bytes()
    assert JOB_STORE.read_bytes() == CANONICAL_JOB_STORE.read_bytes()
    assert JOB_ROUTES.read_bytes() == CANONICAL_JOB_ROUTES.read_bytes()
    assert PATTERN_GATEWAY.read_bytes() == CANONICAL_PATTERN_GATEWAY.read_bytes()
    assert SWARM_ROUTES.read_bytes() == CANONICAL_SWARM_ROUTES.read_bytes()
    assert A2A_ADAPTER.read_bytes() == CANONICAL_A2A_ADAPTER.read_bytes()
    assert A2A_ROUTES.read_bytes() == CANONICAL_A2A_ROUTES.read_bytes()
    assert SWARM_AGENTS.read_bytes() == CANONICAL_SWARM_AGENTS.read_bytes()
    assert REPOSITORY_TOOLS.read_bytes() == CANONICAL_REPOSITORY_TOOLS.read_bytes()
    assert TOOL_EVENTS.read_bytes() == CANONICAL_TOOL_EVENTS.read_bytes()
    assert FILE_TOOL.read_bytes() == CANONICAL_FILE_TOOL.read_bytes()


def test_read_only_agents_missions_have_a_terminal_completed_path() -> None:
    agents = SWARM_AGENTS.read_text("utf-8")
    routes = SWARM_ROUTES.read_text("utf-8")

    assert "mission_complete: bool = False" in agents
    assert "def _resolved_swarm_status(" in agents
    assert 'return True, "COMPLETED"' in agents
    assert "verdict.mission_complete = False" in agents
    assert '{"BLOCKED", "READY_FOR_DRAFT_PR", "COMPLETED"}' in routes
    assert '"NO_FURTHER_ACTION_REQUIRED"' in routes
    assert 'final_state["status"] in {"READY_FOR_DRAFT_PR", "COMPLETED"}' in routes


def test_controller_board_is_registered_in_the_real_backend() -> None:
    controller = CONTROLLER.read_text("utf-8")
    app = APP.read_text("utf-8")

    assert 'from controller_board import register_controller_board_routes' in app
    assert 'register_controller_board_routes(' in app
    assert 'require_session=require_session' in app
    assert 'COPY *.py ./' in DOCKERFILE.read_text("utf-8")
    assert '@app.route("/controller")' in controller
    assert '@app.route("/api/controller/overview", methods=["GET"])' in controller
    assert '@app.route("/api/controller/github", methods=["GET"])' in controller
    assert '@app.route("/api/internal/controller/runs", methods=["GET"])' in controller
    assert '@app.route("/api/internal/controller/runs", methods=["POST"])' in controller
    assert '@app.route("/api/internal/controller/runs/<run_id>", methods=["GET"])' in controller
    assert '@app.route("/api/internal/controller/runs/<run_id>/events/external", methods=["POST"])' in controller
    assert '@app.route("/api/internal/controller/runs/<run_id>/resume", methods=["POST"])' in controller


def test_backend_reserves_request_capacity_during_long_agents_sdk_runs() -> None:
    dockerfile = DOCKERFILE.read_text("utf-8")

    assert "--worker-class gthread" in dockerfile
    assert '--workers \\"${SOVEREIGN_WEB_WORKERS:-2}\\"' in dockerfile
    assert '--threads \\"${SOVEREIGN_WEB_THREADS:-4}\\"' in dockerfile
    assert "--timeout 120" in dockerfile
    assert "--workers 2 --timeout 120" not in dockerfile


def test_backend_ci_is_validation_only_and_queue_only() -> None:
    workflow = WORKFLOW.read_text("utf-8")
    ci_workflow = CI_WORKFLOW.read_text("utf-8")

    assert "release-policy-gate:" in workflow
    assert "agent_runtime/a2a_adapter.py" in ci_workflow
    assert "agent_runtime/a2a_routes.py" in ci_workflow
    assert "tests/test_a2a_adapter.py" in ci_workflow
    assert "tests/test_a2a_routes.py" in ci_workflow
    assert "production release requires the Sovereign host-command queue." in workflow
    assert "appleboy/" not in workflow
    assert "VPS_PASSWORD" not in workflow
    assert "docker build" not in workflow
    assert "docker run" not in workflow
    assert "Deploy to VPS" not in workflow


def test_controller_uses_real_user_session_and_never_browser_storage() -> None:
    controller = CONTROLLER.read_text("utf-8")

    assert "'/api/auth/login'" in controller
    assert "'/api/auth/me'" in controller
    assert "'/api/auth/logout'" in controller
    assert "credentials:'include'" in controller
    assert "sovereign_session" not in controller
    assert "localStorage" not in controller
    assert "sessionStorage" not in controller
    assert "state={user:null,overview:null,github:null,adminKey:''" in controller


def test_internal_operator_bridge_is_owner_scoped_and_never_accepts_browser_credentials() -> None:
    controller = CONTROLLER.read_text("utf-8")

    assert 'request.headers.get("X-Sovereign-Owner-Request-Key"' in controller
    assert "hmac.compare_digest(expected, supplied)" in controller
    assert 'os.getenv("SOVEREIGN_OWNER_ADMIN_ID"' in controller
    assert 'os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL"' in controller
    assert "WHERE run_id=%s AND user_id=%s::uuid" in controller
    assert "create_agent_run(" in controller
    assert "claim_agent_run_for_resume(" in controller
    assert "record_external_action_event(" in controller
    assert "execute_persisted_swarm(" in controller
    assert '"operatorBridge": True' in controller
    assert '"protectedValuesReturned": False' in controller
    assert "secret-shaped material is forbidden in operator input" in controller
    assert "secret-shaped material is forbidden in operator evidence" in controller
    assert "secret-shaped material is forbidden in external event input" in controller
    assert "adminKey" not in controller.split('@app.route("/api/internal/controller/runs"', 1)[1].split('@app.route("/api/controller/overview"', 1)[0]
    assert "sovereign_session" not in controller


def test_external_action_stream_is_idempotent_owner_scoped_and_state_neutral() -> None:
    controller = CONTROLLER.read_text("utf-8")
    run_store = RUN_STORE.read_text("utf-8")

    assert "EXTERNAL_ACTION_SOURCES" in run_store
    for source in ("mcp", "broker", "github", "browserless", "tika", "gotenberg", "database"):
        assert f'"{source}"' in run_store.split("EXTERNAL_ACTION_SOURCES", 1)[1].split("})", 1)[0]
    assert "def record_external_action_event(" in run_store
    assert "ON CONFLICT (evidence_id) DO NOTHING" in run_store
    assert "ON CONFLICT (event_id) DO NOTHING" in run_store
    external_function = run_store.split("def record_external_action_event(", 1)[1].split("def transition_agent_run(", 1)[0]
    assert "UPDATE agent_runs" not in external_function
    assert "UPDATE agent_tasks" not in external_function
    assert '"runStateChanged": False' in external_function
    assert '"taskStateChanged": False' in external_function
    assert '"activeBlockerChanged": False' in external_function
    assert '"rawSecretsPersisted": False' in external_function

    external_route = controller.split(
        '@app.route("/api/internal/controller/runs/<run_id>/events/external"',
        1,
    )[1].split(
        '@app.route("/api/internal/controller/runs/<run_id>/resume"',
        1,
    )[0]
    assert "_service_authorized()" in external_route
    assert "_operator_owner_user_id(conn)" in external_route
    assert "record_external_action_event(" in external_route
    assert '201 if result["created"] else 200' in external_route
    assert '"protectedValuesReturned": False' in external_route


def test_code_missions_use_llm_intent_and_materialize_six_tool_bound_tasks() -> None:
    controller = CONTROLLER.read_text("utf-8")
    routes = SWARM_ROUTES.read_text("utf-8")
    agents = SWARM_AGENTS.read_text("utf-8")
    tools = REPOSITORY_TOOLS.read_text("utf-8")
    run_store = RUN_STORE.read_text("utf-8")
    tool_events = TOOL_EVENTS.read_text("utf-8")
    job_store = JOB_STORE.read_text("utf-8")

    assert "class MissionIntent(BaseModel):" in agents
    assert "async def classify_mission_intent(" in agents
    assert 'Literal["conversation", "read_only_analysis", "repository_execution"]' in agents
    assert "Understand the user's natural language" in agents
    assert "stage_billing = AgentStageBilling(" in controller
    assert "mission_intent = asyncio.run(classify_mission_intent(" in controller
    assert "stage_billing=stage_billing" in controller
    assert "_persist_billing_blocker(" in controller
    assert controller.index("received_state = create_agent_run(") < controller.index("stage_billing = AgentStageBilling(")
    assert controller.index("stage_billing = AgentStageBilling(") < controller.index("mission_intent = asyncio.run(classify_mission_intent(")
    assert "intent_classification_failure" in controller
    assert "link_agent_run_job(" in controller
    assert 'mission_intent.mode == "repository_execution"' in controller
    assert "_IMPLEMENTATION_ACTION_PATTERN" not in controller
    assert "_IMPLEMENTATION_TARGET_PATTERN" not in controller
    assert "create_sovereign_agent_job(" in controller
    assert 'clone_repo=True' in controller
    assert 'job_id=implementation_job.job_id if implementation_job else None' in controller
    assert "create_repository_swarm_tasks(" in controller
    assert "BoundRepositoryToolset(" in controller
    assert "repository_tool_factory=(repository_toolset.tools_for_role" in controller
    assert "ROLE_WORK_PACKAGES" in tools
    for role in ("data_storage", "business_core", "endpoint_bridge", "chat_cognitive", "ui_accessibility", "predictive_qa"):
        assert f'"{role}"' in tools
    assert "function_tool(read_repository_file)" in tools
    assert "function_tool(scan_repository_family)" in tools
    assert "function_tool(apply_exact_repository_patch)" in tools
    assert "start_agent_tool_call(" in tools
    assert "finish_agent_tool_call(" in tools
    assert "INSERT INTO agent_tool_calls" in run_store
    assert "tool_call_count = tool_call_count + 1" in run_store
    assert 'stage="agent_evidence_gate" if not evidence_pending else "agent_evidence_pending"' in tool_events
    assert "next_blocker = gate.reason if tool_failed else None" in tool_events
    assert "jsonb_agg(item ORDER BY item)" in job_store
    assert "COALESCE(sovereign_agent_jobs.changed_files" in job_store
    assert "LEFT(sovereign_agent_jobs.diff_summary || E'\\n---\\n' || input.diff_summary" in job_store
    assert '"autoMerge": False' in controller


def test_visible_user_swarm_route_uses_the_same_repository_execution_path() -> None:
    routes = SWARM_ROUTES.read_text("utf-8")

    assert 'def start_cognitive_swarm_run(' in routes
    assert '@app.route("/api/user/agent/swarm/run", methods=["POST"])' in routes
    assert "mission_intent = asyncio.run(classify_mission_intent(" in routes
    assert "normalized_mission," in routes
    assert "model=normalized_model," in routes
    assert "stage_billing=stage_billing," in routes
    assert routes.index("received_state = create_agent_run(") < routes.index("stage_billing = AgentStageBilling(")
    assert routes.index("stage_billing = AgentStageBilling(") < routes.index("mission_intent = asyncio.run(classify_mission_intent(")
    assert "payload, status_code = start_cognitive_swarm_run(" in routes
    assert "payload, status_code = resume_cognitive_swarm_run(" in routes
    assert "start_run=start_cognitive_swarm_run" in routes
    assert "resume_run=resume_cognitive_swarm_run" in routes
    assert "intent_classification_failure" in routes
    assert "link_agent_run_job(" in routes
    assert 'mission_intent.mode == "repository_execution"' in routes
    assert "create_sovereign_agent_job(" in routes
    assert "create_repository_swarm_tasks(" in routes
    assert "BoundRepositoryToolset(" in routes
    assert "repository_tool_factory=(repository_toolset.tools_for_role" in routes
    assert "task_ids_by_agent=task_ids_by_agent" in routes
    assert '"learningState": "PENDING_EVIDENCE"' in routes
    assert '"autoMerge": False' in routes
    assert "persist_pattern_learning_candidate_once(" in routes
    assert '"learningEvidence"' in routes
    assert "pg_advisory_xact_lock" in PATTERN_GATEWAY.read_text("utf-8")


def test_task_lifecycle_preserves_history_without_false_active_blockers() -> None:
    controller = CONTROLLER.read_text("utf-8")

    assert "def _current_task_id(" in controller
    assert "def _task_runtime_view(" in controller
    assert '"taskLifecycle": "current" if is_current else "historical"' in controller
    assert '"isActiveBlocker": is_current and not run_terminal' in controller
    assert '"resolvedByTaskId": current_task_id if not is_current else None' in controller
    assert '"READY_FOR_DRAFT_PR",' in controller.split("_TERMINAL_RUN_STATUSES", 1)[1].split("})", 1)[0]
    assert "JOIN LATERAL (" in controller
    assert "ORDER BY created_at DESC LIMIT 1" in controller
    assert "Historische Evidence, kein aktiver Blocker." in controller


def test_release_hunt_evidence_is_persisted_and_rendered_from_jsonb() -> None:
    controller = CONTROLLER.read_text("utf-8")
    routes = SWARM_ROUTES.read_text("utf-8")
    agents = SWARM_AGENTS.read_text("utf-8")

    assert '"releaseHunt": release_hunt' in routes
    assert 'hunt_outcome not in {"FINDING", "NULLFIND", "BLOCKED"}' in routes
    assert '"nullfindConfirmed": nullfind_confirmed' in routes
    assert "payload->'releaseHunt' AS release_hunt" in controller
    assert '"releaseHunt": release_hunt' in controller
    assert '"releaseHunt": _release_hunt_payload' in controller
    assert "Release-Jagd · ${esc(h.errorFamily" in controller
    assert "RELEASE_HUNT_SKILL_PATH" in agents
    assert "sovereign-release-ready-error-family-hunt" in agents


def test_failure_details_are_bounded_and_come_from_persisted_evidence() -> None:
    controller = CONTROLLER.read_text("utf-8")

    assert "_FAILURE_DIAGNOSTIC_KEYS" in controller
    assert '"failureStage"' in controller
    assert '"failureFamily"' in controller
    assert '"errorType"' in controller
    assert '"httpStatus"' in controller
    assert '"requestId"' in controller
    assert "LEFT JOIN agent_evidence e ON e.evidence_id=f.evidence_id" in controller
    assert 'failure["diagnostics"] = _bounded_failure_diagnostics' in controller
    assert "Stage: ${esc(q.failureStage||'unknown')}" in controller
    assert "Error: ${esc(q.errorType||'unknown')}" in controller
    assert "raw exception" not in controller.lower()


def test_visible_runtime_state_comes_from_persisted_agent_evidence() -> None:
    controller = CONTROLLER.read_text("utf-8")

    for table in (
        "agent_runs",
        "agent_tasks",
        "agent_events",
        "agent_evidence",
        "agent_tool_calls",
        "agent_failures",
        "agent_approvals",
    ):
        assert table in controller
    assert '"runtime": "openai-agents-sdk"' in controller
    assert "Math.random" not in controller
    assert "Date.now" not in controller


def test_approval_panel_preserves_owner_and_resume_boundaries() -> None:
    controller = CONTROLLER.read_text("utf-8")
    run_store = RUN_STORE.read_text("utf-8")
    routes = SWARM_ROUTES.read_text("utf-8")

    assert "def request_agent_approval(" in run_store
    assert '"WAITING_FOR_OWNER",\n})' in run_store
    assert "INSERT INTO agent_approvals" in run_store
    assert "SET status = 'WAITING_FOR_OWNER'" in run_store
    assert "request_agent_approval(" in routes
    assert 'kind="draft_pr_readiness"' in routes
    assert '202 if final_state["status"] == "WAITING_FOR_OWNER"' in routes
    assert "protected owner input must be completed in the owner approval surface" in controller
    assert '"ownerUrl": "/owner-approvals"' in controller
    assert '"activeUserConfirmed": True' in controller
    assert '"protectedValueReturned": False' in controller
    assert '"resumeRequired": approved and not draft_pr_approval' in controller
    assert "'/api/user/agent/swarm/runs/'" in controller
    assert "RESUME_FROM_OWNER_APPROVAL" in controller
    assert 'approval_kind == "draft_pr_readiness"' in controller
    assert '"READY_FOR_DRAFT_PR"' in controller
    assert '"CREATE_DRAFT_PR_AFTER_OWNER_APPROVAL"' in controller
    assert "'WAITING_FOR_OWNER'].includes(r.status)" in controller
    assert "WHERE a.approval_id=%s AND r.user_id=%s::uuid" in controller


def test_code_and_playwright_monitors_are_read_only_github_evidence() -> None:
    controller = CONTROLLER.read_text("utf-8")

    assert 'requests.get(' in controller
    assert 'from security_oauth import _decrypt_token' in controller
    assert 'token=session_token' in controller
    assert 'requests.post(' not in controller
    assert 'requests.put(' not in controller
    assert 'requests.patch(' not in controller
    assert '/actions/runs?branch=main&per_page=50' in controller
    assert '/commits?sha=main&per_page=15' in controller
    assert 'for marker in ("playwright", "e2e", "browser", "visual", "smoke")' in controller
    assert '"playwrightStats": {' in controller
    assert '"successRate": success_rate' in controller
    assert 'id="playwrightMetrics"' in controller


def test_controller_is_android_first_and_touch_safe() -> None:
    controller = CONTROLLER.read_text("utf-8")

    assert 'viewport-fit=cover' in controller
    assert 'min-height:48px' in controller
    assert '@media(max-width:420px)' in controller
    assert 'env(safe-area-inset-top)' in controller
    assert 'env(safe-area-inset-bottom)' in controller
    assert 'response.headers["X-Frame-Options"] = "DENY"' in controller
    assert 'response.headers["Content-Security-Policy"]' in controller
