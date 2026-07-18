from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

import litellm_runtime


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict[str, Any]:
        return self._payload


def test_completion_canary_classifies_provider_quota_without_returning_raw_error(monkeypatch) -> None:
    raw_message = "You exceeded your current quota."
    monkeypatch.setattr(
        litellm_runtime,
        "litellm_readiness",
        lambda: {"ok": True, "httpStatus": 200},
    )
    monkeypatch.setattr(
        litellm_runtime,
        "fetch_litellm",
        lambda *args, **kwargs: (
            FakeResponse(
                429,
                {"error": {"code": "insufficient_quota", "message": raw_message}},
            ),
            "",
        ),
    )

    result = litellm_runtime.litellm_completion_canary("sovereign-fast")

    assert result["ok"] is False
    assert result["health"] == "blocked"
    assert result["blocker"] == "provider_quota_exhausted"
    assert result["httpStatus"] == 429
    assert result["readinessVerified"] is True
    assert result["completionVerified"] is False
    assert result["evidence"] == {}
    assert raw_message not in str(result)


def test_completion_canary_requires_real_choices_and_returns_only_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        litellm_runtime,
        "litellm_readiness",
        lambda: {"ok": True, "httpStatus": 200},
    )
    monkeypatch.setattr(
        litellm_runtime,
        "fetch_litellm",
        lambda *args, **kwargs: (
            FakeResponse(
                200,
                {
                    "id": "call-safe",
                    "choices": [{"message": {"content": "OK"}}],
                    "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 1,
                        "total_tokens": 5,
                    },
                },
                headers={"x-request-id": "request-safe"},
            ),
            "",
        ),
    )

    result = litellm_runtime.litellm_completion_canary("sovereign-balanced")

    assert result["ok"] is True
    assert result["health"] == "healthy"
    assert result["completionVerified"] is True
    assert result["evidence"]["totalTokens"] == 5
    assert result["evidence"]["upstreamRequestId"] == "request-safe"
    assert "choices" not in result
    assert "content" not in str(result)


def test_completion_canary_stops_before_provider_when_litellm_is_not_ready(monkeypatch) -> None:
    called = False

    def forbidden_fetch(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("completion must not run")

    monkeypatch.setattr(
        litellm_runtime,
        "litellm_readiness",
        lambda: {"ok": False, "httpStatus": 503, "errorCode": "litellm_not_ready"},
    )
    monkeypatch.setattr(litellm_runtime, "fetch_litellm", forbidden_fetch)

    result = litellm_runtime.litellm_completion_canary("sovereign-fast")

    assert result["ok"] is False
    assert result["health"] == "degraded"
    assert result["blocker"] == "litellm_not_ready"
    assert result["readinessVerified"] is False
    assert called is False


def test_admin_health_route_and_ui_use_one_quota_aware_canary_contract() -> None:
    source = (BACKEND / "app.py").read_text("utf-8")
    route_start = source.index('def admin_llm_route_healthcheck(rid):')
    route_end = source.index('@app.route("/api/admin/launcher/tools/<tid>/healthcheck"', route_start)
    route = source[route_start:route_end]

    assert "litellm_completion_canary(model_id)" in route
    assert "legacy_direct_provider_disabled" in route
    assert 'api_key AS "apiKey"' not in route
    assert "requests.get(" not in route
    assert "provider_quota_exhausted" in source
    assert "Provider-Kontingent erschöpft" in source
    assert "boundedFetch('/api/admin/llm/routes/'" in source


def test_litellm_runtime_mirror_remains_byte_equal() -> None:
    assert (BACKEND / "litellm_runtime.py").read_bytes() == (
        ROOT / "backend" / "litellm_runtime.py"
    ).read_bytes()
