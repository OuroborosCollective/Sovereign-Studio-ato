from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
CONTROLLER = BACKEND / "controller_board.py"
APP = BACKEND / "app.py"
DOCKERFILE = BACKEND / "Dockerfile"
RUN_STORE = BACKEND / "agent_runtime" / "cognitive_run_store.py"
SWARM_ROUTES = BACKEND / "agent_runtime" / "cognitive_swarm_routes.py"


def test_controller_module_has_valid_python_syntax() -> None:
    for path in (CONTROLLER, RUN_STORE, SWARM_ROUTES):
        ast.parse(path.read_text("utf-8"), filename=str(path))


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
