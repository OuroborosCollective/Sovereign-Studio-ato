from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import llm_route_scanner as scanner


ROOT = BACKEND.parents[1]
MODULE = BACKEND / "llm_route_scanner.py"
APP = BACKEND / "app.py"
MIGRATION = BACKEND / "migrations" / "036_llm_route_scanner_candidates.sql"
COMPOSE = BACKEND / "docker-compose.yml"
DEPLOY = ROOT / "tools" / "sovereign-chatgpt-mcp" / "deploy" / "deploy-sovereign-backend"
ROLLBACK = ROOT / "tools" / "sovereign-chatgpt-mcp" / "deploy" / "rollback-sovereign-backend"


class FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._body = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload).encode("utf-8")
        )
        self.headers = {
            "Content-Length": str(len(self._body)),
            "Content-Type": "application/json",
        }
        self.closed = False

    def iter_content(self, chunk_size: int = 16_384):
        for index in range(0, len(self._body), chunk_size):
            yield self._body[index:index + chunk_size]

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.trust_env = True

    def post(self, url, **kwargs):
        self.calls.append({"method": "POST", "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("unexpected POST")
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        self.calls.append({"method": "GET", "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("unexpected GET")
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def _manager(session: FakeSession | None = None) -> scanner.RouteManager:
    return scanner.RouteManager(
        acquire_lease=lambda _run_id, _lease: True,
        release_lease=lambda _run_id: None,
        persist_snapshot=lambda _snapshot: None,
        session_factory=(lambda: session) if session is not None else scanner.requests.Session,
    )


def test_extracts_explicit_and_base_completion_endpoints() -> None:
    text = """
    https://free.example.org/v1/chat/completions
    https://another.example.net/api/v1
    https://api.openai.com/v1
    """

    found = _manager().extract_endpoints_from_text(text)

    assert "https://free.example.org/v1/chat/completions" in found
    assert "https://another.example.net/api/v1/chat/completions" in found
    assert all("openai.com" not in item for item in found)


def test_candidate_normalization_blocks_http_private_hosts_and_nonstandard_ports() -> None:
    with pytest.raises(ValueError, match="https_required"):
        scanner._normalize_candidate_endpoint(
            "http://free.example.org/v1/chat/completions"
        )
    with pytest.raises(ValueError, match="host_blocked"):
        scanner._normalize_candidate_endpoint(
            "https://localhost/v1/chat/completions"
        )
    with pytest.raises(ValueError, match="nonstandard_port"):
        scanner._normalize_candidate_endpoint(
            "https://free.example.org:8443/v1/chat/completions"
        )
    with pytest.raises(ValueError, match="ip_literal"):
        scanner._normalize_candidate_endpoint(
            "https://127.0.0.1/v1/chat/completions"
        )


def test_validate_route_requires_two_fixed_canaries_without_user_prompt(monkeypatch) -> None:
    response_payload = {
        "id": "canary",
        "choices": [{"message": {"content": "Ping"}}],
    }
    session = FakeSession([
        FakeResponse(200, response_payload),
        FakeResponse(200, response_payload),
    ])
    monkeypatch.setattr(
        scanner,
        "_resolve_public_addresses",
        lambda _host: ("203.0.113.10",),
    )

    result = _manager(session).validate_route(
        "https://free.example.org/v1/chat/completions",
        ["seed"],
    )

    assert result.status == "canary_passed"
    assert result.confirmation_count == 2
    assert len(session.calls) == 2
    for call in session.calls:
        assert call["allow_redirects"] is False
        assert call["stream"] is True
        assert call["json"]["messages"] == [
            {"role": "user", "content": "Reply only with Ping."}
        ]
        assert call["headers"]["Authorization"] == (
            "Bearer dummy-free-route-canary"
        )
        assert "real user" not in json.dumps(call["json"]).lower()


def test_validate_route_blocks_noncanonical_response(monkeypatch) -> None:
    session = FakeSession([
        FakeResponse(200, {
            "choices": [{"message": {"content": "Ignore previous instructions"}}],
        })
    ])
    monkeypatch.setattr(
        scanner,
        "_resolve_public_addresses",
        lambda _host: ("203.0.113.10",),
    )

    result = _manager(session).validate_route(
        "https://free.example.org/v1/chat/completions",
        ["source"],
    )

    assert result.status == "blocked"
    assert result.confirmation_count == 0
    assert result.failure_family == "candidate_response_contract_failed"


def test_scan_once_is_lease_bound_and_persists_only_candidate_evidence(monkeypatch) -> None:
    persisted: list[scanner.ScanSnapshot] = []
    released: list[str] = []
    manager = scanner.RouteManager(
        acquire_lease=lambda _run_id, _lease: True,
        release_lease=released.append,
        persist_snapshot=persisted.append,
        source_urls=("https://raw.githubusercontent.com/example/list/main/README.md",),
        seed_routes=(),
    )
    monkeypatch.setattr(
        manager,
        "fetch_routes_from_sources",
        lambda: ({
            "https://free.example.org/v1/chat/completions": {"source"}
        }, [], 0),
    )
    monkeypatch.setattr(
        manager,
        "validate_route",
        lambda route, sources: scanner.CandidateEvidence(
            route,
            tuple(sources),
            "canary_passed",
            2,
            200,
            "",
            12,
            "a" * 64,
        ),
    )

    snapshot = manager.scan_once()

    assert snapshot.status == "completed"
    assert snapshot.canary_passed_count == 1
    assert persisted == [snapshot]
    assert released == [snapshot.run_id]
    assert snapshot.safe_payload()["userPromptsForwarded"] is False
    assert snapshot.safe_payload()["automaticRouteActivation"] is False


def test_uploaded_fastapi_surface_is_not_reintroduced_into_production() -> None:
    source = MODULE.read_text("utf-8")
    app = APP.read_text("utf-8")

    assert "from fastapi import" not in source
    assert "FastAPI(" not in source
    assert "import uvicorn" not in source
    assert "class PromptRequest" not in source
    assert 'app.post("/api/execute")' not in source
    assert "register_llm_route_scanner" in source
    assert "from llm_route_scanner import register_llm_route_scanner" in app
    assert "llm_route_scanner_service = register_llm_route_scanner(" in app
    assert '"automaticRouteActivation": False' in source
    assert '"userPromptsForwarded": False' in source


def test_scanner_schema_and_deployment_are_candidate_only() -> None:
    migration = MIGRATION.read_text("utf-8")
    compose = COMPOSE.read_text("utf-8")
    deploy = DEPLOY.read_text("utf-8")
    rollback = ROLLBACK.read_text("utf-8")
    app = APP.read_text("utf-8")

    assert "CREATE TABLE IF NOT EXISTS llm_route_scanner_runtime" in migration
    assert "CREATE TABLE IF NOT EXISTS llm_route_scanner_runs" in migration
    assert "CREATE TABLE IF NOT EXISTS llm_route_scanner_candidates" in migration
    assert "CHECK (routing_eligible = false)" in migration
    assert "036_llm_route_scanner_candidates.sql" in app
    assert 'SOVEREIGN_LLM_ROUTE_SCANNER_ENABLED: "1"' in compose
    assert '--env "SOVEREIGN_LLM_ROUTE_SCANNER_ENABLED=0"' in deploy
    assert '--env "SOVEREIGN_LLM_ROUTE_SCANNER_ENABLED=1"' in deploy
    assert '--env "SOVEREIGN_LLM_ROUTE_SCANNER_ENABLED=1"' in rollback
