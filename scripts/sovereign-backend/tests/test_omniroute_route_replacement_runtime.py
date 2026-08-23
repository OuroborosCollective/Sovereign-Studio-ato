from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import types

import pytest

# The runtime helpers under test only need Flask for route-adapter construction.
# Keep these deterministic boundary tests runnable in the isolated Python gate,
# which intentionally does not install the production web stack.
try:
    import flask  # noqa: F401
except ModuleNotFoundError:
    flask_stub = types.ModuleType("flask")
    flask_stub.jsonify = lambda *args, **kwargs: (args, kwargs)
    sys.modules["flask"] = flask_stub

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


def _canonical_omniroute_route() -> dict:
    return {
        "id": runtime._ROUTE_ID,
        "model_id": runtime._MODEL_ALIAS,
        "base_url": OMNIROUTE_BASE_URL,
        "disabled": True,
        "config": {},
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
        if "FROM llm_routes WHERE id=%s" in sql:
            return _canonical_omniroute_route()
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
        if "FROM llm_routes WHERE id=%s" in sql:
            return _canonical_omniroute_route()
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


def test_omniroute_401_canary_degrades_only_its_dedicated_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    writes: list[tuple[str, tuple]] = []

    def query(sql: str, params=None, *, one=False, write=False):
        writes.append((sql, tuple(params or ())))
        if "FROM llm_routes WHERE id=%s" in sql:
            return _canonical_omniroute_route()
        return None

    monkeypatch.setattr(runtime, "_runtime_identity", lambda: {
        "sourceRevision": "a" * 40,
        "sourceRevisionVerified": True,
        "imageDigest": "sha256:" + "b" * 64,
        "imageDigestVerified": True,
    })
    monkeypatch.setattr(runtime, "_models_readback", lambda: {
        "modelCount": 42,
        "modelSetSha256": "c" * 64,
        "rawModelCatalogPersisted": False,
    })
    monkeypatch.setattr(
        runtime,
        "_completion_canary",
        lambda _confirmation: (_ for _ in ()).throw(
            runtime.OmniRouteActivationError("omniroute_canary_http_401")
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
        "blocker": "omniroute_canary_http_401",
        "freeLlmApiChanged": False,
    }
    all_material = "\n".join(
        sql + " " + repr(params) for sql, params in writes
    )
    assert "freellmapi:3001" not in all_material
    assert "freellmpool:8080" not in all_material
    assert "sovereign-omniroute-auto" in all_material


def test_invalid_canonical_route_identity_fails_before_canary_or_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    calls: list[tuple[str, bool]] = []

    def query(sql: str, _params=None, *, one=False, write=False):
        calls.append((sql, write))
        if "FROM llm_routes WHERE id=%s" in sql:
            return {
                "id": runtime._ROUTE_ID,
                "model_id": "wrong-model-id",
                "base_url": OMNIROUTE_BASE_URL,
                "disabled": True,
                "config": {},
            }
        return None

    monkeypatch.setattr(
        runtime, "_models_readback",
        lambda: pytest.fail("invalid route identity must block before upstream canaries"),
    )
    service = runtime.OmniRouteExecutionRuntime(
        query=query,
        get_connection=lambda: connection,
        audit=lambda *_args, **_kwargs: None,
    )

    result = service.scan_once()

    assert result == {
        "ok": False,
        "status": "blocked",
        "routeSource": "omniroute",
        "blocker": "omniroute_route_identity_invalid",
        "freeLlmApiChanged": False,
    }
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert not any(write for _sql, write in calls)
    assert service.status()["blocker"] == "omniroute_route_identity_invalid"


def test_connection_failure_never_strands_the_local_omniroute_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    attempts: list[object] = [RuntimeError("temporary postgres outage"), connection]

    def get_connection():
        attempt = attempts.pop(0)
        if isinstance(attempt, Exception):
            raise attempt
        return attempt

    def query(sql: str, _params=None, *, one=False, write=False):
        if "FROM llm_routes WHERE id=%s" in sql:
            return {
                "id": runtime._ROUTE_ID,
                "model_id": "wrong-model-id",
                "base_url": OMNIROUTE_BASE_URL,
                "disabled": True,
                "config": {},
            }
        return None

    service = runtime.OmniRouteExecutionRuntime(
        query=query,
        get_connection=get_connection,
        audit=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(service, "_mark_failed", lambda _family: None)

    first = service.scan_once()

    assert first == {
        "ok": False,
        "status": "degraded",
        "routeSource": "omniroute",
        "blocker": "omniroute_activation_internal_failure",
        "freeLlmApiChanged": False,
    }
    assert service._local_lock.locked() is False

    second = service.scan_once()

    assert second == {
        "ok": False,
        "status": "blocked",
        "routeSource": "omniroute",
        "blocker": "omniroute_route_identity_invalid",
        "freeLlmApiChanged": False,
    }
    assert connection.closed == 1
    assert service._local_lock.locked() is False


class _RouteApp:
    def __init__(self) -> None:
        self.routes: dict[tuple[str, tuple[str, ...]], object] = {}

    def route(self, path: str, methods: list[str]):
        def register(handler):
            self.routes[(path, tuple(methods))] = handler
            return handler
        return register


def test_refresh_returns_canonical_status_projection_after_success_or_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = {
        "id": "sovereign-omniroute-auto",
        "model_id": "sovereign-omniroute:auto",
        "base_url": OMNIROUTE_BASE_URL,
        "disabled": True,
        "config": {
            "selectable": False,
            "canaryVerified": False,
            "activationState": "blocked",
            "activationBlocker": "omniroute_canary_http_401",
            "canaryConfirmationCount": 0,
        },
    }

    def query(sql: str, _params=None, *, one=False, **_kwargs):
        assert "FROM llm_routes WHERE id=%s" in sql
        assert one is True
        return route

    app = _RouteApp()
    monkeypatch.setattr(runtime, "jsonify", lambda payload: payload)
    monkeypatch.setattr(runtime.OmniRouteExecutionRuntime, "start", lambda _self: None)
    service = runtime.register_omniroute_execution_runtime(
        app,
        require_admin=lambda handler: handler,
        query=query,
        get_connection=lambda: _Connection(),
        audit=lambda *_args, **_kwargs: None,
    )
    refresh = app.routes[("/api/admin/llm/omniroute/refresh", ("POST",))]
    assert callable(refresh)

    expected_keys = {
        "ok",
        "routeSource",
        "routeId",
        "modelId",
        "apiBase",
        "disabled",
        "activationState",
        "blocker",
        "confirmationCount",
        "receiptSha256",
        "sourceRevision",
        "imageDigest",
        "freeLlmApiChanged",
        "rawProviderResponsesReturned",
    }

    monkeypatch.setattr(service, "scan_once", lambda: {"ok": True})
    success_payload, success_status = refresh()
    assert success_status == 200
    assert expected_keys <= success_payload.keys()
    assert success_payload["routeSource"] == "omniroute"
    assert success_payload["activationState"] == "blocked"

    monkeypatch.setattr(service, "scan_once", lambda: {"ok": False, "status": "degraded"})
    failure_payload, failure_status = refresh()
    assert failure_status == 503
    assert expected_keys <= failure_payload.keys()
    assert failure_payload["blocker"] == "omniroute_canary_http_401"
