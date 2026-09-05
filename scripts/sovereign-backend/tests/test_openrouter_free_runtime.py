from __future__ import annotations

import io
import json
from pathlib import Path
import stat
import sys
import types

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

try:
    import flask  # noqa: F401
except ModuleNotFoundError:
    flask_stub = types.ModuleType("flask")
    flask_stub.jsonify = lambda value=None, **kwargs: value if value is not None else kwargs
    flask_stub.make_response = lambda value=None, *args, **kwargs: value
    flask_stub.request = types.SimpleNamespace(headers={}, json={})
    sys.modules["flask"] = flask_stub

import direct_llm_runtime
import openrouter_free_runtime as runtime
from llm_revolver import route_is_verified_free
from llm_transport import route_is_openrouter_free
from owner_input_runtime import DEFAULT_TARGETS


REVISION = "a" * 40
DIGEST = "sha256:" + "b" * 64
TEST_CREDENTIAL = "unit-test-free-execution-credential-material"


def _canary() -> dict:
    return {
        "confirmationCount": 2,
        "confirmations": [
            {
                "generationId": "gen-1",
                "totalCostUsd": "0",
                "resolvedModel": "example/model:free",
                "router": "openrouter/free",
                "textualChatResponseVerified": True,
            },
            {
                "generationId": "gen-2",
                "totalCostUsd": "0",
                "resolvedModel": "example/model:free",
                "router": "openrouter/free",
                "textualChatResponseVerified": True,
            },
        ],
        "generationIds": ["gen-1", "gen-2"],
        "resolvedModels": ["example/model:free", "example/model:free"],
        "latenciesMs": [10, 12],
        "providerCostState": "zero",
        "textualChatResponsesVerified": True,
        "rawResponsesPersisted": False,
    }


def _verified_route(monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", REVISION)
    monkeypatch.setenv("SOVEREIGN_IMAGE_DIGEST", DIGEST)
    config, _ = runtime._route_record(
        key_fingerprint="c" * 64,
        key_source="test-owner-managed-free-key",
        canary=_canary(),
    )
    return {
        "id": runtime.OPENROUTER_FREE_ROUTE_ID,
        "model_id": runtime.OPENROUTER_FREE_ROUTE_ALIAS,
        "provider": "openrouter",
        "runtime_kind": "openrouter",
        "base_url": runtime.OPENROUTER_BASE_URL,
        "disabled": False,
        "priority": 5,
        "config": config,
    }


def test_owner_targets_separate_paid_free_and_management_keys() -> None:
    paid = DEFAULT_TARGETS["openrouter_api_key"]
    free = DEFAULT_TARGETS["openrouter_free_api_key"]
    management = DEFAULT_TARGETS["openrouter_management_api_key"]

    assert paid["path"].endswith("/openrouter_api_key.txt")
    assert free["path"].endswith("/openrouter_free_api_key.txt")
    assert management["path"].endswith("/openrouter_management_api_key.txt")
    assert len({paid["path"], free["path"], management["path"]}) == 3
    assert management["kind"] == "management_credential"


def test_direct_runtime_selects_distinct_free_execution_key() -> None:
    assert direct_llm_runtime._key_contract(
        "openrouter",
        runtime.OPENROUTER_BASE_URL,
        openrouter_free=False,
    ) == ("SOVEREIGN_OPENROUTER_API_KEY_FILE", "openrouter_api_key.txt")
    assert direct_llm_runtime._key_contract(
        "openrouter",
        runtime.OPENROUTER_BASE_URL,
        openrouter_free=True,
    ) == (
        "SOVEREIGN_OPENROUTER_FREE_API_KEY_FILE",
        "openrouter_free_api_key.txt",
    )


def test_openrouter_free_route_requires_revision_bound_zero_cost_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _verified_route(monkeypatch)

    assert route["priority"] == 5
    assert route_is_openrouter_free(route) is True
    assert route_is_verified_free(route) is True
    assert route["config"]["retryEvidence"]["nextTransportAfterCooldown"] == "freellm"
    assert route["config"]["retryEvidence"]["paidFallbackAllowed"] is False
    assert route["config"]["quotaEvidence"]["accountWide"] is True

    route["config"]["canaryReceipt"]["zeroCostEvidenceVerified"] = False
    assert route_is_openrouter_free(route) is False
    assert route_is_verified_free(route) is False


def test_free_key_is_written_with_owner_only_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    runtime._atomic_write_free_key(TEST_CREDENTIAL)

    path = tmp_path / "openrouter_free_api_key.txt"
    assert path.read_text(encoding="utf-8") == TEST_CREDENTIAL
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_route_status_uses_persisted_text_route_id_contract() -> None:
    calls: list[tuple[str, tuple, dict]] = []

    def query(sql: str, params: tuple = (), **kwargs):
        calls.append((sql, params, kwargs))
        if "FROM llm_routes" in sql:
            return {
                "id": runtime.OPENROUTER_FREE_ROUTE_ID,
                "model_id": runtime.OPENROUTER_FREE_ROUTE_ALIAS,
                "disabled": False,
                "priority": 5,
                "runtime_kind": "openrouter",
                "config": {},
            }
        return []

    result = runtime._route_status(query)

    route_sql = calls[0][0]
    assert "id=%s::uuid" not in route_sql
    assert "id=%s LIMIT 1" in route_sql
    assert calls[0][1] == (runtime.OPENROUTER_FREE_ROUTE_ID,)
    assert result["routeId"] == runtime.OPENROUTER_FREE_ROUTE_ID


def test_status_query_failure_only_calls_missing_table_a_migration_gap() -> None:
    class MissingTableError(Exception):
        pgcode = "42P01"

    class TypeContractError(Exception):
        pgcode = "42883"

    assert runtime._status_query_failure(MissingTableError()) == (
        False,
        "openrouter_management_migration_required",
    )
    assert runtime._status_query_failure(TypeContractError()) == (
        None,
        "openrouter_free_status_query_failed",
    )


def test_persist_route_never_casts_text_route_ids_to_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", REVISION)
    monkeypatch.setenv("SOVEREIGN_IMAGE_DIGEST", DIGEST)

    class Cursor:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def execute(self, sql: str, params=None) -> None:
            del params
            self.statements.append(sql)

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    connection = Connection()
    runtime._persist_route(
        lambda: connection,
        key_fingerprint="d" * 64,
        key_source="test",
        canary=_canary(),
        managed_key={
            "hash": "e" * 64,
            "name": "test-free-key",
            "limit": "0",
            "limitReset": "daily",
            "includeByokInLimit": True,
        },
    )

    statements = "\n".join(connection.cursor_instance.statements)
    assert "%s::uuid" not in statements
    assert "VALUES (%s,%s,'OpenRouter Free Router'" in statements
    assert "'active',%s," in statements


class _Raw:
    def __init__(self, payload: bytes) -> None:
        self.buffer = io.BytesIO(payload)

    def read(self, size: int = -1, decode_content: bool = False) -> bytes:
        del decode_content
        return self.buffer.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self.buffer.seek(offset, whence)

    def tell(self) -> int:
        return self.buffer.tell()


class _Response:
    def __init__(self, status: int, payload: dict) -> None:
        self.status_code = status
        self.headers: dict[str, str] = {}
        self.raw = _Raw(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def json(self) -> dict:
        position = self.raw.tell()
        self.raw.seek(0)
        value = json.loads(self.raw.read().decode("utf-8"))
        self.raw.seek(position)
        return value


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.trust_env = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, *args, **kwargs):
        self.response.raw.seek(0)
        return self.response


def test_generation_receipt_rejects_positive_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _Response(
        200,
        {
            "data": {
                "total_cost": "0.000001",
                "model": "example/model:free",
                "router": "openrouter/free",
            }
        },
    )
    monkeypatch.setattr(runtime.requests, "Session", lambda: _Session(response))

    with pytest.raises(runtime.OpenRouterFreeRuntimeError) as exc:
        runtime._generation_zero_cost("execution-credential", "gen-positive")

    assert exc.value.family == "openrouter_free_generation_cost_not_zero"


def test_management_key_is_rejected_for_model_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _Response(200, {"data": {"is_management_key": True}})
    monkeypatch.setattr(runtime.requests, "Session", lambda: _Session(response))

    with pytest.raises(runtime.OpenRouterFreeRuntimeError) as exc:
        runtime._current_key_metadata("management-credential")

    assert exc.value.family == "openrouter_management_key_cannot_execute_models"


def test_management_key_limit_is_fail_closed_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOVEREIGN_OPENROUTER_FREE_KEY_LIMIT_USD", "1")
    with pytest.raises(runtime.OpenRouterFreeRuntimeError) as exc:
        runtime._managed_key_limit()
    assert exc.value.family == "openrouter_free_key_limit_must_be_zero"

    monkeypatch.setenv("SOVEREIGN_OPENROUTER_FREE_KEY_LIMIT_USD", "0")
    assert runtime._managed_key_limit() == 0


class _CanarySession(_Session):
    def __init__(self, completions, receipts, calls):
        self.completions = completions
        self.receipts = receipts
        self.calls = calls
        self.trust_env = True

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _Response(200, self.completions.pop(0))

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return _Response(200, {"data": self.receipts.pop(0)})


def _completion(content="OK", finish_reason="stop", generation="canary-generation"):
    return {
        "id": generation, "model": "example/model:free",
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
    }


def test_double_canary_allows_reasoning_budget_and_requires_two_zero_cost_receipts(monkeypatch):
    calls = []
    completions = [_completion(generation="generation-one"), _completion(generation="generation-two")]
    receipts = [{"total_cost": "0", "model": "example/model:free", "router": "openrouter/free"} for _ in range(2)]
    monkeypatch.setattr(runtime.requests, "Session",
                        lambda: _CanarySession(completions, receipts, calls))
    result = runtime._double_canary(TEST_CREDENTIAL)
    assert result["confirmationCount"] == 2
    assert result["generationIds"] == ["generation-one", "generation-two"]
    assert [method for method, _, _ in calls] == ["POST", "GET", "POST", "GET"]
    for method, url, kwargs in calls:
        assert url.startswith(runtime.OPENROUTER_BASE_URL + "/")
        assert kwargs["allow_redirects"] is False
        if method == "POST":
            assert kwargs["json"]["model"] == "openrouter/free"
            assert kwargs["json"]["max_tokens"] == 512
            assert kwargs["timeout"] == 45
    assert result["providerCostState"] == "zero"


@pytest.mark.parametrize("content,finish_reason,family", [
    ("", "length", "openrouter_free_canary_truncated"),
    ("OK", "length", "openrouter_free_canary_truncated"),
    ("", "stop", "openrouter_free_canary_text_missing"),
    (None, "stop", "openrouter_free_canary_text_missing"),
])
def test_incomplete_or_nontextual_canary_never_activates(monkeypatch, content, finish_reason, family):
    calls = []
    completions = [_completion(content=content, finish_reason=finish_reason)]
    monkeypatch.setattr(runtime.requests, "Session",
                        lambda: _CanarySession(completions, [], calls))
    with pytest.raises(runtime.OpenRouterFreeRuntimeError) as exc:
        runtime._double_canary(TEST_CREDENTIAL)
    assert exc.value.family == family
    assert len(calls) == 1


@pytest.mark.parametrize("cost,model,router,family", [
    ("0.001", "example/model:free", "openrouter/free", "openrouter_free_generation_cost_not_zero"),
    ("0", "example/model", "other/router", "openrouter_free_generation_identity_unverified"),
])
def test_textual_canary_still_requires_free_generation_evidence(monkeypatch, cost, model, router, family):
    calls = []
    completions = [_completion()]
    receipts = [{"total_cost": cost, "model": model, "router": router}]
    monkeypatch.setattr(runtime.requests, "Session",
                        lambda: _CanarySession(completions, receipts, calls))
    with pytest.raises(runtime.OpenRouterFreeRuntimeError) as exc:
        runtime._double_canary(TEST_CREDENTIAL)
    assert exc.value.family == family
    assert [method for method, _, _ in calls] == ["POST", "GET"]


def test_verified_openrouter_free_route_can_enter_strict_server_action_validation(monkeypatch):
    import ast
    from llm_transport import route_transport

    module = ast.parse((BACKEND / "app.py").read_text(encoding="utf-8"))
    names = {"_llm_route_config", "_code_action_contract_mode"}
    nodes = [node for node in module.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"route_transport": route_transport,
                 "route_is_verified_free": route_is_verified_free, "_json": json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    mode = namespace["_code_action_contract_mode"]
    route = _verified_route(monkeypatch)
    assert mode(route) == "server-validated-json"
    route["config"]["canaryReceipt"]["zeroCostEvidenceVerified"] = False
    assert mode(route) is None
    route = _verified_route(monkeypatch)
    route["disabled"] = True
    assert mode(route) is None


def test_generation_receipt_waits_for_late_indexing_without_new_completion(monkeypatch):
    responses = [_Response(404, {"error": {"message": "Resource not found"}}) for _ in range(5)]
    responses.append(_Response(200, {"data": {
        "total_cost": "0", "model": "example/model:free", "router": "openrouter/free",
    }}))
    sleeps = []
    calls = []
    class Session(_Session):
        def get(self, url, **kwargs):
            calls.append((url, kwargs["params"]))
            return responses.pop(0)
    monkeypatch.setattr(runtime.requests, "Session", lambda: Session(None))
    monkeypatch.setattr(runtime.time, "sleep", sleeps.append)
    result = runtime._generation_zero_cost(TEST_CREDENTIAL, "same-generation")
    assert result["totalCostUsd"] == "0"
    assert result["generationId"] == "same-generation"
    assert sleeps == [1, 2, 3, 4, 5]
    assert len(calls) == 6
    assert all(url.endswith("/generation") and params == {"id": "same-generation"}
               for url, params in calls)


def test_missing_generation_receipt_has_bounded_specific_failure(monkeypatch):
    calls = []
    sleeps = []
    class Session(_Session):
        def get(self, url, **kwargs):
            calls.append(url)
            return _Response(404, {"error": {"message": "Resource not found"}})
    monkeypatch.setattr(runtime.requests, "Session", lambda: Session(None))
    monkeypatch.setattr(runtime.time, "sleep", sleeps.append)
    with pytest.raises(runtime.OpenRouterFreeRuntimeError) as exc:
        runtime._generation_zero_cost(TEST_CREDENTIAL, "missing-generation")
    assert exc.value.family == "openrouter_generation_receipt_unavailable"
    assert exc.value.status_code == 503
    assert len(calls) == 6
    assert sum(sleeps) == 15


@pytest.mark.parametrize("status,family", [
    (401, "openrouter_credentials_rejected"),
    (429, "openrouter_rate_limited"),
    (500, "openrouter_upstream_unavailable"),
])
def test_generation_receipt_only_retries_not_found(monkeypatch, status, family):
    sleeps = []
    monkeypatch.setattr(runtime.requests, "Session",
                        lambda: _Session(_Response(status, {"error": {}})))
    monkeypatch.setattr(runtime.time, "sleep", sleeps.append)
    with pytest.raises(runtime.OpenRouterFreeRuntimeError) as exc:
        runtime._generation_zero_cost(TEST_CREDENTIAL, "generation")
    assert exc.value.family == family
    assert sleeps == []


def test_data_policy_endpoint_failure_does_not_relax_privacy():
    response = _Response(404, {"error": {
        "message": "No endpoints found that match your data policy.",
    }})
    assert runtime._safe_error_family(response) == "openrouter_data_policy_no_endpoints"
    assert runtime._FREE_PROVIDER_POLICY["data_collection"] == "deny"
