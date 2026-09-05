"""Regression tests execute the production schema and production attempt loop.

Transport/database doubles stay at external boundaries; these tests are not
runtime receipts and never authorize or contact a live provider.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

APP = Path(__file__).resolve().parents[1] / "app.py"
MODULE = ast.parse(APP.read_text(encoding="utf-8"))
ACTION = {
    "mode": "action", "intent": "code_execution",
    "action_disposition": "review", "clarification_code": "none",
    "is_startup": False, "confidence": 0.9, "language": "de",
}


def _production_namespace():
    names = {
        "_code_action_contract_messages", "_code_action_contract_mode",
        "_llm_route_config", "_validate_code_action_contract",
    }
    constants = {
        "_SOVEREIGN_CODE_ACTION_RESPONSE_FORMAT", "_CODE_ACTION_CONTRACT_KEYS",
        "_CODE_ACTION_INTENTS",
    }
    nodes = [node for node in MODULE.body if (
        isinstance(node, ast.FunctionDef) and node.name in names
    ) or (
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets)
    )]
    namespace = {"_json": json, "route_transport": lambda route: route["transport"]}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP), "exec"), namespace)
    return namespace


def _completion(valid=True, usage=True):
    return {
        "choices": [{"message": {"content": json.dumps(ACTION) if valid else "Plain prose, not JSON"}}],
        "_evidence": {
            "promptTokens": 503 if usage else 0,
            "completionTokens": 168 if usage else 0,
            "totalTokens": 671 if usage else 0,
            "providerCostUsd": None,
            "upstreamRequestId": "provider-receipt" if usage else None,
        },
    }


def _execute_attempts(completions, *, pinned=False, paid=False, recording_fails=False):
    namespace = _production_namespace()
    routes = [{"id": "route-a", "transport": "openrouter" if paid else "freellm",
               "config": {"supportedParameters": ["response_format"]} if paid else {}},
              {"id": "route-b", "transport": "freellm", "config": {}}]
    sent, recorded, refunds, failed = [], [], [], []
    responses = iter(completions)

    def fetch(route, *, json_data):
        sent.append((route, copy.deepcopy(json_data)))
        return SimpleNamespace(ok=True, status_code=200, payload=next(responses)), None

    def record(**kwargs):
        if recording_fails:
            raise RuntimeError("database boundary unavailable")
        recorded.append(kwargs)

    namespace.update({
        "candidate_routes": routes[:1] if pinned else routes,
        "route": routes[0], "route_selection_mode": "pinned" if pinned else "auto",
        "resolver_enabled": not pinned, "output_contract_id": "sovereign-code-action-v1",
        "payload": {"messages": namespace["_code_action_contract_messages"]([
            {"role": "user", "content": "Run the repository tests"}
        ]), "max_tokens": 700, "stream": False},
        "request_id": "test-request", "fetch_direct_llm": fetch,
        "_safe_upstream_json": lambda response: response.payload,
        "extract_direct_llm_evidence": lambda response, payload, **kwargs: dict(payload["_evidence"]),
        "revolver_provider_usage_seen": lambda evidence: bool(
            evidence.get("totalTokens") or evidence.get("upstreamRequestId") or evidence.get("providerCostUsd")
        ),
        "route_is_verified_free": lambda route: route["transport"] == "freellm",
        "_record_llm_revolver_attempt": record,
        "refund_failed_run": lambda code: refunds.append(code),
        "_mark_llm_settlement_failed": lambda request_id, code: failed.append((request_id, code)),
        "jsonify": lambda payload: payload,
    })
    chat = next(node for node in MODULE.body if isinstance(node, ast.FunctionDef) and node.name == "public_llm_chat")
    loop = next(node for node in ast.walk(chat) if isinstance(node, ast.For)
                and isinstance(node.target, ast.Tuple)
                and [getattr(item, "id", "") for item in node.target.elts] == ["attempt_count", "candidate_route"])
    runner = ast.parse("def run():\n    provider_usage_seen = False\n    fallback_route = None\n").body[0]
    runner.body.append(copy.deepcopy(loop))
    runner.body.extend(ast.parse("return result, evidence, attempt_count, fallback_route\n").body)
    executable = ast.fix_missing_locations(ast.Module(body=[runner], type_ignores=[]))
    exec(compile(executable, str(APP), "exec"), namespace)
    result = namespace["run"]()
    return result, sent, recorded, refunds, failed


def test_prompt_only_provider_receives_the_exact_server_schema_without_mutation():
    namespace = _production_namespace()
    original = [{"role": "user", "content": "Check tests"}]
    before = copy.deepcopy(original)
    messages = namespace["_code_action_contract_messages"](original)
    encoded_schema = messages[0]["content"].split("JSON Schema: ", 1)[1]
    assert json.loads(encoded_schema) == namespace["_SOVEREIGN_CODE_ACTION_RESPONSE_FORMAT"]["json_schema"]["schema"]
    assert messages[0]["role"] == "system"
    assert "action_disposition must always be review" in messages[0]["content"]
    assert messages[1:] == original == before
    assert messages[1] is not original[0]


def test_schema_is_included_before_input_cost_reservation():
    source = ast.get_source_segment(APP.read_text(encoding="utf-8"), next(
        node for node in MODULE.body if isinstance(node, ast.FunctionDef) and node.name == "public_llm_chat"
    ))
    assert source.index("messages = _code_action_contract_messages(messages)") < source.index(
        "input_token_upper_bound = _estimate_llm_input_token_upper_bound(messages)"
    ) < source.index("fetch_direct_llm(")


def test_valid_contract_records_success_and_preserves_provider_structured_mode():
    _result, sent, recorded, refunds, _failed = _execute_attempts([_completion()], paid=True)
    assert len(sent) == 1
    assert sent[0][1]["response_format"]["type"] == "json_schema"
    assert recorded[0]["outcome"] == "success"
    assert recorded[0]["decision"] is None
    assert refunds == []


@pytest.mark.parametrize("paid,pinned", [(False, False), (True, False), (False, True)])
def test_rejected_completion_with_usage_is_never_success_or_blindly_retried(paid, pinned):
    _result, sent, recorded, refunds, _failed = _execute_attempts([
        _completion(valid=False), _completion()
    ], paid=paid, pinned=pinned)
    assert len(sent) == 1
    assert recorded[0]["outcome"] == "terminal_failure"
    assert recorded[0]["decision"]["blocker"] == "llm_output_contract_violation"
    assert recorded[0]["evidence"]["totalTokens"] == 671
    assert recorded[0]["response"].status_code == 200
    assert refunds == []


def test_auto_free_contract_failure_can_rotate_only_before_provider_usage():
    result, sent, recorded, refunds, _failed = _execute_attempts([
        _completion(valid=False, usage=False), _completion()
    ])
    assert len(sent) == 2
    assert [entry["outcome"] for entry in recorded] == ["retryable_failure", "success"]
    assert result[2] == 2 and result[3]["id"] == "route-b"
    assert refunds == []


def test_manual_pin_never_rotates_even_without_provider_usage():
    _result, sent, recorded, _refunds, _failed = _execute_attempts([
        _completion(valid=False, usage=False), _completion()
    ], pinned=True)
    assert len(sent) == 1
    assert recorded[0]["outcome"] == "terminal_failure"


def test_attempt_record_failure_with_usage_cannot_refund_real_provider_work():
    result, sent, _recorded, refunds, failed = _execute_attempts([_completion()], recording_fails=True)
    assert len(sent) == 1 and result[1] == 500
    assert result[0]["blocker"] == "revolver_evidence_failed"
    assert refunds == [] and failed == [("test-request", "revolver_evidence_failed")]


def test_rejected_contract_updates_the_actual_settlement_helper():
    node = next(node for node in MODULE.body if isinstance(node, ast.FunctionDef)
                and node.name == "_update_llm_usage_settlement")
    writes = []
    namespace = {"query": lambda sql, params=None, **kwargs: writes.append((sql, params, kwargs))}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP), "exec"), namespace)
    namespace["_update_llm_usage_settlement"](
        "request", status="failed", error_code="llm_output_contract_violation", request_count=1
    )
    assert len(writes) == 1
    sql, params, options = writes[0]
    assert "UPDATE llm_usage_settlements" in sql
    assert "llm_output_contract_violation" in params
    assert options.get("write") is True


def test_admin_quota_identity_matches_the_canonical_backend_constant():
    root = APP.parents[2]
    runtime = ast.parse((APP.parent / "openrouter_free_runtime.py").read_text(encoding="utf-8"))
    quota = next(ast.literal_eval(node.value) for node in runtime.body
                 if isinstance(node, ast.Assign) and any(
                     isinstance(target, ast.Name) and target.id == "OPENROUTER_FREE_QUOTA_SCOPE"
                     for target in node.targets))
    client = (root / "src/features/admin/api/adminApiClient.ts").read_text(encoding="utf-8")
    assert f"policy.accountWideQuotaScope === '{quota}'" in client
