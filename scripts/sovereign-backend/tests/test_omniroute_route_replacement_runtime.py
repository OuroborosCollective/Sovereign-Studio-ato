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
        "provider": "freellm",
        "runtime_kind": "freellm",
        "base_url": OMNIROUTE_BASE_URL,
        "disabled": True,
        "source_present": True,
        "model_present": True,
        "config": {
            "transport": "freellm",
            "routeSource": "omniroute",
            "sourceType": "omniroute",
            "providerModel": "auto",
            "executionProfile": "free_single_agent",
            "billingCategory": "free",
            "billingClass": "free",
            "fundingMode": "provider_free_quota",
            "pricingVerified": False,
            "markupMultiplier": 0,
            "minimumMultiplier": 0,
            "userChargeCredits": 0,
            "quotaScope": "freellm:omniroute:auto",
            "quotaEvidence": {
                "scope": "freellm:omniroute:auto",
                "stateOwner": "postgresql-revolver-state",
            },
            "routingOwner": "free-revolver-v3",
            "resolverMode": "revolver",
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
        self.rowcount = 1
        self._row = {"acquired": True}
        self.route = _canonical_omniroute_route()
        self.source = {"id": runtime._SOURCE_ID}
        self.model = {"id": "omniroute-auto-model"}
        self.rowcount_by_sql: dict[str, int] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, params=()) -> None:
        self.executed.append((sql, tuple(params)))
        self.rowcount = next(
            (count for marker, count in self.rowcount_by_sql.items() if marker in sql),
            1,
        )

    def fetchone(self):
        sql = self.executed[-1][0] if self.executed else ""
        if "pg_try_advisory_xact_lock" in sql:
            return self._row
        if "FROM llm_routes WHERE id=%s FOR UPDATE" in sql:
            return self.route
        if "FROM llm_revolver_provider_sources" in sql and "FOR UPDATE" in sql:
            return self.source
        if "FROM llm_revolver_provider_models" in sql and "FOR UPDATE" in sql:
            return self.model
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
    audits: list[tuple[str, str | None, dict, int]] = []
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
        audit=lambda action, target, changes: audits.append(
            (action, target, changes, connection.commits)
        ),
    )

    result = service.scan_once()

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["freeLlmApiChanged"] is False
    assert confirmations == [1, 2]
    assert connection.commits == 1
    assert connection.closed == 1
    assert audits and audits[-1][0] == "omniroute_runtime_double_canary_verified"
    assert audits[-1][3] == 1
    assert writes == []
    all_sql = "\n".join(
        sql for sql, _params in connection.cursor_instance.executed
    )
    assert "FROM llm_routes WHERE id=%s FOR UPDATE" in all_sql
    assert "llm_revolver_provider_sources" in all_sql
    assert "llm_revolver_provider_models" in all_sql
    assert "UPDATE llm_routes" in all_sql
    assert "freellmapi:3001" not in all_sql
    assert "freellmpool:8080" not in all_sql


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
        sql + " " + repr(params)
        for sql, params in connection.cursor_instance.executed
    )
    assert "freellmapi:3001" not in all_material
    assert "freellmpool:8080" not in all_material
    assert "sovereign-omniroute-auto" in all_material
    assert connection.commits == 1
    assert connection.rollbacks == 0
    advisory_locks = [
        sql
        for sql, _params in connection.cursor_instance.executed
        if "pg_try_advisory_xact_lock" in sql
    ]
    assert len(advisory_locks) == 1
    assert next(
        index
        for index, (sql, _params) in enumerate(connection.cursor_instance.executed)
        if "pg_try_advisory_xact_lock" in sql
    ) < next(
        index
        for index, (sql, _params) in enumerate(connection.cursor_instance.executed)
        if "SET disabled=true" in sql
    )


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
        sql + " " + repr(params)
        for sql, params in connection.cursor_instance.executed
    )
    assert "freellmapi:3001" not in all_material
    assert "freellmpool:8080" not in all_material
    assert "sovereign-omniroute-auto" in all_material
    assert connection.commits == 1
    assert "SET disabled=false" not in all_material


def test_activation_projection_rowcount_conflict_rolls_back_without_ready_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    connection.cursor_instance.rowcount_by_sql["UPDATE llm_routes"] = 0
    query_writes: list[str] = []

    def query(_sql: str, _params=None, *, write=False, **_kwargs):
        if write:
            query_writes.append(_sql)
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
    monkeypatch.setattr(runtime, "_completion_canary", lambda confirmation: {
        "confirmation": confirmation,
        "upstreamRequestId": f"req-{confirmation}",
        "providerGenerationId": f"gen-{confirmation}",
        "responseModel": "keyless-model",
        "providerCostUsd": 0.0,
        "latencyMs": 10,
        "textualChatResponseVerified": True,
        "rawProviderResponsePersisted": False,
        "requestAuthorizationHeaderSent": False,
    })
    service = runtime.OmniRouteExecutionRuntime(
        query=query,
        get_connection=lambda: connection,
        audit=lambda *_args, **_kwargs: pytest.fail("audit requires a commit"),
    )

    result = service.scan_once()

    assert result["ok"] is False
    assert result["blocker"] == "omniroute_canonical_state_rows_missing"
    assert query_writes == []
    assert connection.commits == 0
    assert connection.rollbacks == 1
    all_sql = "\n".join(
        sql for sql, _params in connection.cursor_instance.executed
    )
    assert "UPDATE llm_revolver_provider_sources" in all_sql
    assert "UPDATE llm_revolver_provider_models" in all_sql
    assert "SET disabled=false" in all_sql
    assert "SET disabled=true" in all_sql


def test_internal_failure_rolls_back_without_stale_failure_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    monkeypatch.setattr(runtime, "_runtime_identity", lambda: {
        "sourceRevision": "a" * 40,
        "sourceRevisionVerified": True,
        "imageDigest": "sha256:" + "b" * 64,
        "imageDigestVerified": True,
    })
    monkeypatch.setattr(
        runtime,
        "_models_readback",
        lambda: (_ for _ in ()).throw(RuntimeError("unexpected decoder failure")),
    )
    service = runtime.OmniRouteExecutionRuntime(
        query=lambda *_args, **_kwargs: None,
        get_connection=lambda: connection,
        audit=lambda *_args, **_kwargs: None,
    )

    result = service.scan_once()

    assert result["ok"] is False
    assert result["blocker"] == "omniroute_activation_internal_failure"
    assert connection.commits == 0
    assert connection.rollbacks == 1
    all_sql = "\n".join(
        sql for sql, _params in connection.cursor_instance.executed
    )
    assert "SET disabled=true" not in all_sql


def test_audit_failure_after_committed_activation_does_not_project_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()

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
    monkeypatch.setattr(runtime, "_completion_canary", lambda confirmation: {
        "confirmation": confirmation,
        "upstreamRequestId": f"req-{confirmation}",
        "providerGenerationId": f"gen-{confirmation}",
        "responseModel": "keyless-model",
        "providerCostUsd": 0.0,
        "latencyMs": 10,
        "textualChatResponseVerified": True,
        "rawProviderResponsePersisted": False,
        "requestAuthorizationHeaderSent": False,
    })
    service = runtime.OmniRouteExecutionRuntime(
        query=lambda *_args, **_kwargs: None,
        get_connection=lambda: connection,
        audit=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit down")),
    )

    result = service.scan_once()

    assert result["ok"] is True
    assert connection.commits == 1
    all_sql = "\n".join(
        sql for sql, _params in connection.cursor_instance.executed
    )
    assert "SET disabled=true" not in all_sql


def test_status_is_ready_only_for_a_real_execution_verified_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = {
        "sourceRevision": "a" * 40,
        "sourceRevisionVerified": True,
        "imageDigest": "sha256:" + "b" * 64,
        "imageDigestVerified": True,
    }
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", identity["sourceRevision"])
    monkeypatch.setenv("SOVEREIGN_IMAGE_DIGEST", identity["imageDigest"])
    receipt = runtime._receipt(identity, {
        "modelSetSha256": "c" * 64,
    }, [
        {
            "upstreamRequestId": "req-1",
            "providerCostUsd": 0.0,
            "requestAuthorizationHeaderSent": False,
        },
        {
            "upstreamRequestId": "req-2",
            "providerCostUsd": 0.0,
            "requestAuthorizationHeaderSent": False,
        },
    ])
    route = _canonical_omniroute_route()
    route["disabled"] = False
    route["config"].update({
        "providerModel": "auto",
        "executionProfile": "free_single_agent",
        "billingCategory": "free",
        "billingClass": "free",
        "fundingMode": "provider_free_quota",
        "pricingVerified": False,
        "freeEligible": True,
        "quotaContractVerified": True,
        "userChargeCredits": 0,
        "markupMultiplier": 0,
        "canaryVerified": True,
        "canaryConfirmationCount": 2,
        "catalogVerified": True,
        "transportCanaryVerified": True,
        "selectable": True,
        "quotaScope": "freellm:omniroute:auto",
        "quotaEvidence": {
            "scope": "freellm:omniroute:auto",
            "stateOwner": "postgresql-revolver-state",
        },
        "runtimeIdentity": identity,
        "canaryReceipt": receipt,
    })
    service = runtime.OmniRouteExecutionRuntime(
        query=lambda *_args, **_kwargs: route,
        get_connection=lambda: _Connection(),
        audit=lambda *_args, **_kwargs: None,
    )

    status = service.status()

    assert status["ok"] is True
    assert status["disabled"] is False
    assert status["activationState"] == "ready"
    assert status["blocker"] is None


def test_status_query_requires_executable_source_and_model_supporting_state() -> None:
    queries: list[str] = []

    def query(sql: str, _params=None, **_kwargs):
        queries.append(sql)
        return _canonical_omniroute_route()

    service = runtime.OmniRouteExecutionRuntime(
        query=query,
        get_connection=lambda: _Connection(),
        audit=lambda *_args, **_kwargs: None,
    )

    assert service._canonical_route() is not None
    contract_sql = " ".join(queries[-1].split())
    assert "auth_mode='none' AND enabled=true AND status='healthy'" in contract_sql
    assert (
        "litellm_alias=%s AND enabled=true AND status='ready' "
        "AND free_verified=true AND free_eligible=true"
    ) in contract_sql


@pytest.mark.parametrize("missing_field", ["source_present", "model_present"])
def test_status_blocks_when_the_canonical_source_or_model_readback_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    missing_field: str,
) -> None:
    route = _canonical_omniroute_route()
    route["disabled"] = False
    route[missing_field] = False
    monkeypatch.setattr(
        runtime,
        "verify_free_route_reason",
        lambda _route: pytest.fail("supporting-row drift must block before verifier"),
    )
    service = runtime.OmniRouteExecutionRuntime(
        query=lambda *_args, **_kwargs: route,
        get_connection=lambda: _Connection(),
        audit=lambda *_args, **_kwargs: None,
    )

    status = service.status()

    assert status["ok"] is False
    assert status["disabled"] is True
    assert status["activationState"] == "blocked"
    assert status["blocker"] == "omniroute_canonical_state_rows_missing"


@pytest.mark.parametrize(("field", "value"), [
    ("executionProfile", "paid_swarm_6"),
    ("providerModel", "not-auto"),
    ("routingOwner", "not-free-revolver-v3"),
    ("markupMultiplier", True),
])
def test_static_execution_identity_drift_blocks_before_canary_or_write(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    connection = _Connection()
    connection.cursor_instance.route["config"][field] = value
    service = runtime.OmniRouteExecutionRuntime(
        query=lambda *_args, **_kwargs: None,
        get_connection=lambda: connection,
        audit=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        runtime,
        "_models_readback",
        lambda: pytest.fail("static identity drift must block before upstream canaries"),
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
    assert not any(
        "UPDATE " in sql or "INSERT INTO llm_revolver_provider_checks" in sql
        for sql, _params in connection.cursor_instance.executed
    )


def test_status_uses_execution_verifier_and_never_renders_stale_ready_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _canonical_omniroute_route()
    route["disabled"] = False
    route["config"].update({
        "selectable": True,
        "canaryVerified": True,
        "canaryConfirmationCount": "not-a-number",
        "activationState": "ready",
        "activationBlocker": None,
    })
    monkeypatch.setattr(runtime, "verify_free_route_reason", lambda _route: {
        "ok": False,
        "failureFamilies": ["free_runtime_source_revision_mismatch"],
    })
    service = runtime.OmniRouteExecutionRuntime(
        query=lambda *_args, **_kwargs: route,
        get_connection=lambda: _Connection(),
        audit=lambda *_args, **_kwargs: None,
    )

    status = service.status()

    assert status["ok"] is False
    assert status["disabled"] is True
    assert status["activationState"] == "blocked"
    assert status["blocker"] == "free_runtime_source_revision_mismatch"
    assert status["confirmationCount"] == 0


@pytest.mark.parametrize("invalid_route", [
    {"model_id": "wrong-model-id"},
    {"base_url": f"{OMNIROUTE_BASE_URL}/"},
    {"base_url": OMNIROUTE_BASE_URL.replace("/v1", "/V1")},
])
def test_invalid_canonical_route_identity_fails_before_canary_or_mutation(
    monkeypatch: pytest.MonkeyPatch,
    invalid_route: dict[str, str],
) -> None:
    connection = _Connection()
    connection.cursor_instance.route.update(invalid_route)
    calls: list[tuple[str, bool]] = []

    def query(sql: str, _params=None, *, one=False, write=False):
        calls.append((sql, write))
        if "FROM llm_routes WHERE id=%s" in sql:
            route = _canonical_omniroute_route()
            route.update(invalid_route)
            return route
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
    connection.cursor_instance.route["model_id"] = "wrong-model-id"
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
        "provider": "freellm",
        "runtime_kind": "freellm",
        "base_url": OMNIROUTE_BASE_URL,
        "disabled": True,
        "source_present": True,
        "model_present": True,
        "config": {
            "transport": "freellm",
            "routeSource": "omniroute",
            "sourceType": "omniroute",
            "providerModel": "auto",
            "executionProfile": "free_single_agent",
            "billingCategory": "free",
            "billingClass": "free",
            "fundingMode": "provider_free_quota",
            "pricingVerified": False,
            "markupMultiplier": 0,
            "minimumMultiplier": 0,
            "userChargeCredits": 0,
            "quotaScope": "freellm:omniroute:auto",
            "quotaEvidence": {
                "scope": "freellm:omniroute:auto",
                "stateOwner": "postgresql-revolver-state",
            },
            "routingOwner": "free-revolver-v3",
            "resolverMode": "revolver",
            "direct": True,
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
