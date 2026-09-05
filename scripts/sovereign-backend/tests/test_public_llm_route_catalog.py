from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app.py"
sys.path.insert(0, str(BACKEND))
from llm_revolver import route_is_verified_free


def _function(name: str) -> ast.FunctionDef:
    module = ast.parse(APP.read_text(encoding="utf-8"))
    return next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _load_function(name: str, namespace: dict) -> dict:
    node = _function(name)
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(module, str(APP), "exec"), namespace)
    return namespace


def test_runtime_selectability_requires_a_verified_executor_route() -> None:
    namespace = _load_function(
        "_is_runtime_selectable_llm_route",
        {
            "route_is_verified_free": lambda route: bool(route.get("verifiedFree")),
            "route_is_verified_paid": lambda route: bool(route.get("verifiedPaid")),
        },
    )
    selectable = namespace["_is_runtime_selectable_llm_route"]

    assert selectable({"verifiedFree": True}) is True
    assert selectable({"verifiedPaid": True}) is True
    assert selectable({"verifiedFree": False, "verifiedPaid": False}) is False


def test_public_catalog_excludes_routes_the_executor_would_reject() -> None:
    source = APP.read_text(encoding="utf-8")
    catalog_sql = source[source.index("def public_llm_routes()"):source.index("def public_llm_route(")]
    assert "base_url, runtime_kind, tier, disabled, priority, config" in catalog_sql

    class FakeApp:
        @staticmethod
        def route(_path: str):
            return lambda function: function

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
            self.headers: dict[str, str] = {}

    class FakeRequest:
        args: dict[str, str] = {}

    rows = [
        {"id": "stale", "selectable": False},
        {"id": "verified-free", "selectable": True},
    ]
    namespace = _load_function(
        "public_llm_routes",
        {
            "app": FakeApp(),
            "request": FakeRequest(),
            "query": lambda *_args, **_kwargs: rows,
            "jsonify": lambda payload: payload,
            "make_response": FakeResponse,
            "_public_llm_route_payload": lambda route: {
                "id": route["id"],
                "enabled": True,
            },
            "_is_runtime_selectable_llm_route": lambda route: bool(route["selectable"]),
            "_route_supports_code_action_contract": lambda _route: False,
        },
    )

    response = namespace["public_llm_routes"]()

    assert response.payload["routes"] == [{"id": "verified-free", "enabled": True}]
    assert response.payload["purpose"] == "execution"
    assert response.headers["Cache-Control"] == "no-store, max-age=0"


def test_action_contract_catalog_keeps_only_server_or_provider_verified_routes() -> None:
    class FakeApp:
        @staticmethod
        def route(_path: str):
            return lambda function: function

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
            self.headers: dict[str, str] = {}

    class FakeRequest:
        args = {"purpose": "action-contract"}

    rows = [
        {"id": "general-chat", "selectable": True, "structured": False},
        {"id": "structured", "selectable": True, "structured": True},
    ]
    namespace = _load_function(
        "public_llm_routes",
        {
            "app": FakeApp(),
            "request": FakeRequest(),
            "query": lambda *_args, **_kwargs: rows,
            "jsonify": lambda payload: payload,
            "make_response": FakeResponse,
            "_public_llm_route_payload": lambda route: {"id": route["id"]},
            "_is_runtime_selectable_llm_route": lambda route: bool(route["selectable"]),
            "_route_supports_code_action_contract": lambda route: bool(route["structured"]),
        },
    )

    response = namespace["public_llm_routes"]()

    assert response.payload["purpose"] == "action-contract"
    assert response.payload["routes"] == [{"id": "structured"}]


def test_unknown_catalog_purpose_fails_closed() -> None:
    class FakeApp:
        @staticmethod
        def route(_path: str):
            return lambda function: function

    class FakeRequest:
        args = {"purpose": "surprise"}

    namespace = _load_function(
        "public_llm_routes",
        {
            "app": FakeApp(),
            "request": FakeRequest(),
            "jsonify": lambda payload: payload,
        },
    )

    payload, status = namespace["public_llm_routes"]()

    assert status == 400
    assert payload["blocker"] == "llm_route_catalog_purpose_invalid"
    assert payload["routes"] == []


def test_code_action_contract_is_server_owned_and_forwarded_only_by_id() -> None:
    source = APP.read_text(encoding="utf-8")
    assert '_SOVEREIGN_CODE_ACTION_CONTRACT_ID = "sovereign-code-action-v1"' in source
    assert 'supported.intersection({"response_format", "structured_outputs"})' in source
    assert '"server-validated-json"' in source
    assert 'output_contract_id = str(body.get("outputContractId") or "").strip()' in source
    assert 'candidate_payload["response_format"] = _SOVEREIGN_CODE_ACTION_RESPONSE_FORMAT' in source
    assert 'body.get("response_format")' not in source
    assert 'sanitized != content.strip()' in source


def test_freellm_routes_use_server_validated_json_mode() -> None:
    namespace = _load_function(
        "_code_action_contract_mode",
        {
            "_llm_route_config": lambda route: route.get("config", {}),
            "route_transport": lambda route: route.get("transport"),
            "route_is_verified_free": route_is_verified_free,
        },
    )
    mode = namespace["_code_action_contract_mode"]

    assert mode({"transport": "freellm", "config": {}}) == "server-validated-json"
    assert mode({
        "transport": "openrouter",
        "config": {"supportedParameters": ["response_format"]},
    }) == "provider-structured"
    assert mode({"transport": "openrouter", "config": {}}) is None


def test_code_action_validator_rejects_provider_prose_and_unsafe_disposition() -> None:
    namespace = _load_function(
        "_validate_code_action_contract",
        {
            "_json": json,
            "_CODE_ACTION_CONTRACT_KEYS": {
                "mode",
                "intent",
                "action_disposition",
                "clarification_code",
                "is_startup",
                "confidence",
                "language",
            },
            "_CODE_ACTION_INTENTS": {
                "direct_patch",
                "code_execution",
                "draft_pr",
                "workflow_watch",
                "repair_workflow",
                "load_repo",
            },
        },
    )
    validate = namespace["_validate_code_action_contract"]

    def completion(content: str) -> dict:
        return {"choices": [{"message": {"content": content}}]}

    action = {
        "mode": "action",
        "intent": "code_execution",
        "action_disposition": "review",
        "clarification_code": "none",
        "is_startup": False,
        "confidence": 0.9,
        "language": "de",
    }
    assert validate(completion(json.dumps(action))) == action
    assert validate(completion("Ich kann keinen Code ausführen.")) is None
    assert validate(completion(json.dumps({**action, "action_disposition": "execute"}))) is None
    assert validate(completion(json.dumps({**action, "extra": "provider prose"}))) is None

    clarification = {
        **action,
        "mode": "clarify",
        "intent": "unknown",
        "clarification_code": "repo_required",
        "confidence": 0.2,
    }
    assert validate(completion(json.dumps(clarification))) == clarification
    assert validate(completion(json.dumps({**clarification, "clarification_code": "none"}))) is None


def test_chat_route_resolution_rejects_stale_enabled_rows() -> None:
    stale = {"id": "stale", "model_id": "old-model", "selectable": False}
    verified = {"id": "verified", "model_id": "new-model", "selectable": True}
    namespace = _load_function(
        "_resolve_enabled_llm_route",
        {
            "query": lambda *_args, **_kwargs: [stale],
            "_is_runtime_selectable_llm_route": lambda route: bool(route["selectable"]),
            "route_billing_policy": lambda route: {"billingCategory": "free"},
            "BillingPolicyError": ValueError,
        },
    )
    resolve = namespace["_resolve_enabled_llm_route"]

    assert resolve("old-model") is None
    namespace["query"] = lambda *_args, **_kwargs: [stale, verified]
    assert resolve("new-model") == verified
