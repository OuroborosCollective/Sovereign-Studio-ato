from pathlib import Path
import sys

from flask import Flask

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_swarm_routes import register_cognitive_swarm_routes


def _require_session(handler):
    return handler


def _app() -> Flask:
    app = Flask(__name__)
    register_cognitive_swarm_routes(app, require_session=_require_session)
    return app


def test_swarm_manifest_route_reports_exact_topology(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _app().test_client()
    response = client.get("/api/user/agent/swarm/manifest")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["runtime"] == "openai-agents-sdk"
    assert payload["configured"] is False
    assert payload["manifest"]["agentCount"] == 8
    assert payload["manifest"]["autoMerge"] is False


def test_swarm_run_fails_closed_without_protected_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _app().test_client()
    response = client.post(
        "/api/user/agent/swarm/run",
        json={"mission": "Inspect supplied evidence.", "evidence": "No runtime evidence supplied."},
    )
    payload = response.get_json()
    assert response.status_code == 503
    assert payload["status"] == "BLOCKED"
    assert "OPENAI_API_KEY" in payload["blocker"]


def test_swarm_rejects_secret_shaped_input() -> None:
    client = _app().test_client()
    response = client.post(
        "/api/user/agent/swarm/run",
        json={"mission": "Use github_pat_example in the workflow."},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "secret-shaped material is forbidden in swarm input"
