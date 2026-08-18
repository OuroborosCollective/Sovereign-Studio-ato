from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import direct_llm_runtime  # noqa: E402
import omniroute_execution_runtime as runtime  # noqa: E402
from llm_transport import (  # noqa: E402
    FREELLM_BASE_URL,
    FREELLM_EXECUTION_BASE_URLS,
    FREELLMPOOL_BASE_URL,
    OMNIROUTE_BASE_URL,
    route_is_direct_freellm,
    route_is_omniroute_source,
)


def _route(base_url: str, model: str = "auto") -> dict:
    return {
        "id": "route-test",
        "provider": "freellm",
        "runtime_kind": "freellm",
        "base_url": base_url,
        "disabled": False,
        "config": {
            "transport": "freellm",
            "providerModel": model,
            "executionProfile": "free_single_agent",
            "direct": True,
        },
    }


def test_transport_keeps_freellmapi_retires_pool_and_adds_omniroute() -> None:
    assert FREELLM_BASE_URL in FREELLM_EXECUTION_BASE_URLS
    assert OMNIROUTE_BASE_URL in FREELLM_EXECUTION_BASE_URLS
    assert FREELLMPOOL_BASE_URL not in FREELLM_EXECUTION_BASE_URLS
    assert route_is_direct_freellm(_route(FREELLM_BASE_URL, "free-model")) is True
    assert route_is_direct_freellm(_route(OMNIROUTE_BASE_URL)) is True
    assert route_is_omniroute_source(_route(OMNIROUTE_BASE_URL)) is True
    assert route_is_direct_freellm(_route(FREELLMPOOL_BASE_URL)) is False


def test_omniroute_is_keyless_but_freellmapi_keeps_protected_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    @contextmanager
    def protected(transport: str, api_base: str, *, openrouter_free: bool = False):
        calls.append((transport, api_base))
        yield "owner-secret-value"

    monkeypatch.setattr(direct_llm_runtime, "_protected_key", protected)

    with direct_llm_runtime._authorization_headers(_route(OMNIROUTE_BASE_URL)) as headers:
        assert headers == {}
    assert calls == []

    with direct_llm_runtime._authorization_headers(
        _route(FREELLM_BASE_URL, "free-model")
    ) as headers:
        assert headers == {"Authorization": "Bearer owner-secret-value"}
    assert calls == [("freellm", FREELLM_BASE_URL)]


class _Cursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._row = {"acquired": True}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, params=()) -> None:
        self.executed.append((sql, tuple(params)))

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed += 1


def test_runtime_double_canary_promotes_only_omniroute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    writes: list[tuple[str, tuple]] = []
    audits: list[tuple[str, str | None, dict]] = []
    confirmations: list[int] = []

    def query(sql: str, params=None, *, one=False, write=False):
        writes.append((sql, tuple(params or ())))
        return None

    monkeypatch.setattr(runtime, "_runtime_identity", lambda: {
        "sourceRevision": "a" * 40,
        "sourceRevisionVerified": True,
        "imageDigest": "sha256:" + "b" * 64,
        "imageDigestVerified": True,
    })
    monkeypatch.setattr(runtime, "_models_readback", lambda: {
        "modelCount": 7,
        "modelSetSha256": "c" * 64,
        "rawModelCatalogPersisted": False,
    })

    def canary(number: int) -> dict:
        confirmations.append(number)
        return {
            "confirmation": number,
            "upstreamRequestId": f"req-{number}",
            "providerGenerationId": f"gen-{number}",
            "responseModel": "keyless-model",
            "providerCostUsd": 0.0,
            "latencyMs": 10 + number,
            "textualChatResponseVerified": True,
            "rawProviderResponsePersisted": False,
            "requestAuthorizationHeaderSent": False,
        }

    monkeypatch.setattr(runtime, "_completion_canary", canary)
    service = runtime.OmniRouteExecutionRuntime(
        query=query,
        get_connection=lambda: connection,
        audit=lambda action, target, changes: audits.append((action, target, changes)),
    )

    result = service.scan_once()

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["freeLlmApiChanged"] is False
    assert confirmations == [1, 2]
    assert connection.commits == 1
    assert connection.closed == 1
    assert audits and audits[-1][0] == "omniroute_runtime_double_canary_verified"
    all_sql = "\n".join(sql for sql, _params in writes)
    assert "sovereign-omniroute-auto" not in all_sql or "llm_routes" in all_sql
    assert "freellmapi:3001" not in all_sql
    assert "freellmpool:8080" not in all_sql
    assert any("UPDATE llm_routes" in sql for sql, _params in writes)
    assert any("llm_revolver_provider_models" in sql for sql, _params in writes)


def test_runtime_failure_disables_only_omniroute_and_never_freellmapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    writes: list[tuple[str, tuple]] = []

    def query(sql: str, params=None, *, one=False, write=False):
        writes.append((sql, tuple(params or ())))
        return None

    monkeypatch.setattr(runtime, "_runtime_identity", lambda: {
        "sourceRevision": "a" * 40,
        "sourceRevisionVerified": True,
        "imageDigest": "sha256:" + "b" * 64,
        "imageDigestVerified": True,
    })
    monkeypatch.setattr(
        runtime,
        "_models_readback",
        lambda: (_ for _ in ()).throw(
            runtime.OmniRouteActivationError("omniroute_models_unavailable")
        ),
    )
    service = runtime.OmniRouteExecutionRuntime(
        query=query,
        get_connection=lambda: connection,
        audit=lambda *_args, **_kwargs: None,
    )

    result = service.scan_once()

    assert result == {
        "ok": False,
        "status": "degraded",
        "routeSource": "omniroute",
        "blocker": "omniroute_models_unavailable",
        "freeLlmApiChanged": False,
    }
    all_material = "\n".join(
        sql + " " + repr(params) for sql, params in writes
    )
    assert "freellmapi:3001" not in all_material
    assert "freellmpool:8080" not in all_material
    assert "sovereign-omniroute-auto" in all_material
