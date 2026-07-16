from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
CONTROLLER = BACKEND / "controller_board.py"
APP = BACKEND / "app.py"
DOCKERFILE = BACKEND / "Dockerfile"
RUN_STORE = BACKEND / "agent_runtime" / "cognitive_run_store.py"
SWARM_ROUTES = BACKEND / "agent_runtime" / "cognitive_swarm_routes.py"
SWARM_AGENTS = BACKEND / "agent_runtime" / "cognitive_swarm_agents.py"
WORKFLOW = BACKEND.parents[1] / ".github" / "workflows" / "sovereign-agent-backend.yml"
CANONICAL_RUNTIME = BACKEND.parents[1] / "backend" / "agent_runtime"
CANONICAL_RUN_STORE = CANONICAL_RUNTIME / "cognitive_run_store.py"
CANONICAL_SWARM_ROUTES = CANONICAL_RUNTIME / "cognitive_swarm_routes.py"
CANONICAL_SWARM_AGENTS = CANONICAL_RUNTIME / "cognitive_swarm_agents.py"


def test_controller_module_has_valid_python_syntax() -> None:
    for path in (CONTROLLER, RUN_STORE, SWARM_ROUTES, SWARM_AGENTS):
        ast.parse(path.read_text("utf-8"), filename=str(path))


def test_canonical_and_deployed_agent_runtime_are_byte_identical() -> None:
    assert RUN_STORE.read_bytes() == CANONICAL_RUN_STORE.read_bytes()
    assert SWARM_ROUTES.read_bytes() == CANONICAL_SWARM_ROUTES.read_bytes()
    assert SWARM_AGENTS.read_bytes() == CANONICAL_SWARM_AGENTS.read_bytes()


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
    assert 'COPY controller_board.py .' in DOCKERFILE.read_text("utf-8")
    assert '@app.route("/controller")' in controller
    assert '@app.route("/api/controller/overview", methods=["GET"])' in controller
    assert '@app.route("/api/controller/github", methods=["GET"])' in controller
    assert '@app.route("/api/internal/controller/runs", methods=["GET"])' in controller
    assert '@app.route("/api/internal/controller/runs", methods=["POST"])' in controller
    assert '@app.route("/api/internal/controller/runs/<run_id>", methods=["GET"])' in controller
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

    assert "release-policy-gate:" in workflow
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
    assert "execute_persisted_swarm(" in controller
    assert '"operatorBridge": True' in controller
    assert '"protectedValuesReturned": False' in controller
    assert "secret-shaped material is forbidden in operator input" in controller
    assert "secret-shaped material is forbidden in operator evidence" in controller
    assert "adminKey" not in controller.split('@app.route("/api/internal/controller/runs"', 1)[1].split('@app.route("/api/controller/overview"', 1)[0]
    assert "sovereign_session" not in controller


def test_code_missions_materialize_real_job_workspace_and_tool_task() -> None:
    controller = CONTROLLER.read_text("utf-8")

    assert "def _mission_requires_repository_execution(" in controller
    assert "create_sovereign_agent_job(" in controller
    assert 'clone_repo=True' in controller
    assert 'job_id=implementation_job.job_id if implementation_job else None' in controller
    assert "create_agent_task(" in controller
    assert 'status="WAITING_FOR_TOOL"' in controller
    assert 'next_action="EXECUTE_BOUNDED_REPOSITORY_TOOLS"' in controller
    assert '("file", "git-status", "diff", "test", "draft-pr-prepare", "draft-pr-create")' in controller
    assert '"At least one actionable changed file is persisted."' in controller
    assert '"Git diff evidence is non-empty and git diff --check passes."' in controller
    assert '"At most one Draft PR is created and auto-merge remains disabled."' in controller
    assert '"autoMerge": False' in controller


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
