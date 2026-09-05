"""Exercise the real chat handler with only network/persistence adapters replaced."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

APP = Path(__file__).resolve().parents[1] / "app.py"
CONTRACT = {
    "mode": "action", "intent": "code_execution", "action_disposition": "review",
    "clarification_code": "none", "is_startup": False, "confidence": 0.9, "language": "de",
}


def load_contract_functions(namespace):
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    names = {
        "_SOVEREIGN_CODE_ACTION_CONTRACT_ID", "_SOVEREIGN_CODE_ACTION_RESPONSE_FORMAT",
        "_CODE_ACTION_CONTRACT_KEYS", "_CODE_ACTION_INTENTS", "_llm_route_config",
        "_code_action_contract_mode", "_route_supports_code_action_contract",
        "_validate_code_action_contract", "_code_action_contract_messages", "public_llm_chat",
    }
    nodes = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in names)
        or (isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in names for target in node.targets
        ))
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP), "exec"), namespace)


def handler(response_content, *, pinned=False, contract=True):
    events = []
    sent = []
    messages = [{"role": "system", "content": "Interpret the request."},
                {"role": "user", "content": "Pruefe das Repository."}]
    route = {"id": "route-primary", "model_id": "model-primary", "provider": "freellm",
             "config": {"billingCategory": "free"}}
    fallback = {**route, "id": "route-fallback", "model_id": "model-fallback"}
    body = {"model": route["id"], "messages": messages, "max_tokens": 1000,
            "routeSelectionMode": "pinned" if pinned else "auto"}
    if contract:
        body["outputContractId"] = "sovereign-code-action-v1"
    response = SimpleNamespace(ok=True, status_code=200)
    result = {"choices": [{"message": {"content": response_content}}]}
    policy = {"billingCategory": "free", "markupMultiplier": 0}
    def fetch(_route, *, json_data):
        sent.append(json_data)
        events.append("fetch")
        return response, ""
    def settle(**_kwargs):
        events.append("settle")
        return {"chargedCredits": 0}, ""
    def record(**kwargs):
        events.append(kwargs["outcome"])
    namespace = {
        "_json": json, "hashlib": hashlib, "os": os,
        "app": SimpleNamespace(route=lambda *_a, **_k: lambda fn: fn),
        "require_session": lambda fn: fn,
        "request": SimpleNamespace(session_user_id="owner", get_json=lambda **_k: body),
        "jsonify": lambda value: value,
        "sanitize_agent_text": lambda value, *_a: value.strip(),
        "_normalize_llm_request_id": lambda _body: "86830d21-af7e-4c8f-8859-763ebe151823",
        "_resolve_enabled_llm_route": lambda _model: route,
        "route_transport": lambda row: row["provider"],
        "route_billing_policy": lambda _row: policy,
        "_load_llm_revolver_candidates": lambda *_a, **_k: [route, fallback],
        "_estimate_llm_input_token_upper_bound": lambda msgs: sum(len(m["content"]) for m in msgs),
        "reservation_credits": lambda **_k: (0, 0),
        "_reserve_provider_funded_llm_credits": lambda **_k: {"newBalance": 0},
        "_create_llm_usage_settlement": lambda *_a, **_k: True,
        "_read_verified_credit_balance": lambda *_a: 0,
        "_update_llm_usage_settlement": lambda *_a, **_k: None,
        "_mark_llm_settlement_failed": lambda *_a, **_k: events.append("settlement_failed"),
        "fetch_direct_llm": fetch,
        "_safe_upstream_json": lambda _resp: result,
        "extract_direct_llm_evidence": lambda *_a, **_k: {"totalTokens": 4},
        "revolver_provider_usage_seen": lambda evidence: evidence.get("totalTokens", 0) > 0,
        "_record_llm_revolver_attempt": record,
        "_settle_llm_usage": settle,
        "FREE_CATEGORY": "free", "FREE_SINGLE_AGENT_PROFILE": "free_single_agent",
        "PAID_SWARM_PROFILE": "paid_swarm_6",
        "BillingPolicyError": ValueError, "InsufficientCredits": LookupError,
        "CreditStateConflict": RuntimeError,
    }
    load_contract_functions(namespace)
    return namespace, sent, events, messages


@pytest.mark.parametrize("pinned", [False, True])
def test_full_schema_reaches_provider_and_input_is_not_modified(pinned):
    ns, sent, events, original = handler(json.dumps(CONTRACT), pinned=pinned)
    snapshot = json.loads(json.dumps(original))
    result = ns["public_llm_chat"]()
    assert isinstance(result, dict), result
    assert result["outputContract"]["validated"] is True
    assert original == snapshot
    instruction = sent[0]["messages"][0]
    assert instruction["role"] == "system"
    assert json.dumps(ns["_SOVEREIGN_CODE_ACTION_RESPONSE_FORMAT"]["json_schema"]["schema"],
                      ensure_ascii=True, sort_keys=True, separators=(",", ":")) in instruction["content"]
    assert "confidence" in instruction["content"]
    assert sent[0]["messages"][1:] == original
    assert "response_format" not in sent[0]


@pytest.mark.parametrize("invalid", [
    "Ich kann helfen.",
    json.dumps({**CONTRACT, "action_disposition": "execute"}),
    json.dumps({**CONTRACT, "mode": "clarify", "intent": "unknown", "clarification_code": "none"}),
])
def test_invalid_contract_is_never_recorded_as_success_or_retried_after_usage(invalid):
    ns, sent, events, _original = handler(invalid)
    result, status = ns["public_llm_chat"]()
    assert status == 502
    assert result["blocker"] == "llm_output_contract_violation"
    assert result["sovereignBilling"]["chargedCredits"] == 0
    assert len(sent) == 1
    assert "success" not in events
    assert "terminal_failure" in events
    assert "settle" in events


def test_valid_contract_records_success_after_validation():
    ns, sent, events, _original = handler(json.dumps(CONTRACT))
    validate = ns["_validate_code_action_contract"]
    def observed_validate(payload):
        events.append("validate")
        return validate(payload)
    ns["_validate_code_action_contract"] = observed_validate
    result = ns["public_llm_chat"]()
    assert result["outputContract"]["validated"] is True
    assert events.index("validate") < events.index("success")
    assert len(sent) == 1


def test_plain_chat_does_not_receive_an_action_schema():
    ns, sent, _events, original = handler("Hallo", contract=False)
    result = ns["public_llm_chat"]()
    assert result["choices"][0]["message"]["content"] == "Hallo"
    assert sent[0]["messages"] == original
    assert "response_format" not in sent[0]
