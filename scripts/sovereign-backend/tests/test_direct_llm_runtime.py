from __future__ import annotations

from pathlib import Path
import sys

import requests

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from direct_llm_runtime import (
    classify_direct_llm_failure,
    classify_freellm_canary_state,
)


def _response(status: int, payload: dict | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.headers = {"Content-Type": "application/json"}
    response._content = __import__("json").dumps(payload or {}).encode("utf-8")
    return response


def _route(transport: str) -> dict:
    return {
        "provider": transport,
        "runtime_kind": transport,
        "config": {"transport": transport},
    }


def test_direct_failure_classification_keeps_availability_retryable() -> None:
    assert classify_direct_llm_failure(
        _route("freellm"), _response(404), ""
    )["blocker"] == "freellm_upstream_unavailable"
    assert classify_direct_llm_failure(
        _route("freellm"), _response(429), ""
    )["blocker"] == "freellm_rate_limited"
    assert classify_direct_llm_failure(
        _route("openrouter"), _response(503), ""
    )["blocker"] == "openrouter_upstream_unavailable"
    assert classify_direct_llm_failure(
        _route("openrouter"), None, "openrouter_request_failed"
    )["blocker"] == "openrouter_upstream_unavailable"


def test_direct_failure_classification_keeps_credentials_hard_blocked() -> None:
    result = classify_direct_llm_failure(
        _route("freellm"), _response(401), ""
    )
    assert result["health"] == "blocked"
    assert result["blocker"] == "freellm_credentials_rejected"


def test_freellm_canary_state_separates_deferred_from_policy_blockers() -> None:
    assert classify_freellm_canary_state({
        "blocker": "freellm_upstream_unavailable",
        "failureFamily": "upstream_http_5xx",
    }) == ("discovered", "freellm_upstream_unavailable")
    assert classify_freellm_canary_state({
        "blocker": "freellm_rate_limited",
        "failureFamily": "upstream_rate_limited",
    }) == ("discovered", "freellm_rate_limited")
    assert classify_freellm_canary_state({
        "blocker": "free_provider_cost_not_zero",
    }) == ("blocked", "free_provider_cost_not_zero")


def test_direct_runtime_never_uses_redirects_proxy_env_or_unbounded_response() -> None:
    runtime = (BACKEND / "direct_llm_runtime.py").read_text("utf-8")
    assert "allow_redirects=False" in runtime
    assert "session.trust_env = False" in runtime
    assert "_MAX_RESPONSE_BYTES" in runtime
    assert "response.raw.read(_MAX_RESPONSE_BYTES + 1" in runtime
    assert "rawProviderResponsePersisted" in runtime
    assert "openrouter_api_key.txt" in runtime
    assert "freellmapi_unified_key.txt" in runtime


def test_retryable_migration_reclassifies_only_historical_generic_failures() -> None:
    migration = (
        BACKEND
        / "migrations"
        / "038_reclassify_retryable_freellm_canary_failures.sql"
    ).read_text("utf-8")
    assert "status = 'discovered'" in migration
    assert "last_error_code = 'free_provider_canary_failed'" in migration
    assert "enabled = false" in migration
    assert "freellm_upstream_availability_unconfirmed" in migration
