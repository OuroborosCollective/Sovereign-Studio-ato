"""Bounded canaries must separate token exhaustion from a non-chat model."""
from __future__ import annotations

import ast
import json
import time
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from direct_llm_runtime import classify_freellm_canary_state
from free_revolver_provider_contracts import general_chat_response_verified

BACKEND = Path(__file__).resolve().parents[1]


def run_canary(payload):
    sent = []
    class Response:
        status_code = 200
        headers = {}
        raw = SimpleNamespace(read=lambda size, **_kwargs: json.dumps(payload).encode()[:size])
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def raise_for_status(self): pass
    class Session:
        trust_env = True
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def post(self, _url, **kwargs):
            assert self.trust_env is False
            assert kwargs["allow_redirects"] is False
            sent.append(kwargs["json"])
            return Response()
    namespace = {
        "Any": object, "json": json, "time": time,
        "requests": SimpleNamespace(Session=Session, Timeout=requests.Timeout,
                                   RequestException=requests.RequestException),
        "assert_provider_target_allowed": lambda _endpoint: None,
        "_auth_headers": lambda *_args: {},
        "_MAX_MODELS_RESPONSE_BYTES": 2_000_000,
        "_KNOWN_KEYLESS_POOL_PROVIDERS": set(),
        "general_chat_response_verified": general_chat_response_verified,
        "managed_internal_source_spec": lambda _base: {"sourceId": "freellmapi-direct"},
    }
    path = BACKEND / "free_revolver_provider_runtime.py"
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == "_direct_completion_canary")
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    result = namespace["_direct_completion_canary"](
        api_base="http://freellmapi:3001/v1", auth_mode="none", key="", model_id="canary-model",
    )
    return result, sent


def completion(content, finish_reason="stop"):
    return {"id": "canary-generation", "model": "canary-model",
            "choices": [{"message": {"role": "assistant", "content": content},
                         "finish_reason": finish_reason}], "usage": {"cost": 0}}


def test_canary_reserves_a_bounded_budget_beyond_eight_reasoning_tokens():
    result, sent = run_canary(completion("OK"))
    assert result["ok"] is True
    assert 256 <= sent[0]["max_tokens"] <= 512
    assert result["evidence"]["textualChatResponseVerified"] is True
    assert result["evidence"]["rawResponsePersisted"] is False


def test_truncated_empty_completion_remains_unverified_and_recheckable():
    result, _sent = run_canary(completion("", "length"))
    assert result["ok"] is False
    assert result["failureFamily"] == "completion_token_limit"
    assert classify_freellm_canary_state(result)[0] == "discovered"


@pytest.mark.parametrize("payload", [completion("blocked"), completion(""), {"choices": []}])
def test_non_chat_and_invalid_responses_do_not_become_ready(payload):
    result, _sent = run_canary(payload)
    assert result["ok"] is False
    assert classify_freellm_canary_state(result)[0] == "blocked"


def test_internal_status_counts_current_receipts_instead_of_stored_ready_flags():
    path = BACKEND / "free_revolver_provider_runtime.py"
    node = next(n for n in ast.walk(ast.parse(path.read_text()))
                if isinstance(n, ast.FunctionDef) and n.name == "internal_freellm_provider_status")
    source = {"id": "source-a", "api_base": "http://freellmapi:3001/v1",
              "enabled": True, "model_count": 7, "ready_count": 7, "free_eligible_count": 7}
    evidence_rows = [{"upstream_model_id": "current", "route_id": "route-current"},
                     {"upstream_model_id": "stale", "route_id": "route-stale"}]
    def query(sql, *_args, **_kwargs):
        return [source] if "GROUP BY source.id" in sql else evidence_rows
    ns = {
        "app": SimpleNamespace(route=lambda *_a, **_k: lambda fn: fn),
        "_internal_owner_authorized": lambda: True, "query": query,
        "_runtime_identity": lambda: {"sourceRevisionVerified": True},
        "_MANAGED_AUTH_MODE": "managed-bearer",
        "is_managed_internal_provider_url": lambda _base: True,
        "_managed_key_state": lambda *_a: {"available": True, "blocker": None, "fingerprintMatches": True},
        "managed_internal_source_spec": lambda _base: {"sourceId": "freellmapi-direct"},
        "_revision_bound_ready_model_ids": lambda *_a, **_k: {"current"},
        "_blocked_general_chat_evidence": lambda *_a: [],
        "FREELLM_PROVIDER_SPECS": {}, "_minimum_ready_routes": lambda: 7,
        "jsonify": lambda payload: payload,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    result = ns["internal_freellm_provider_status"]()
    assert result["readyCount"] == 1
    assert result["minimumReadySatisfied"] is False
    provider = result["providers"][0]
    assert provider["modelCount"] == 7
    assert provider["storedReadyCount"] == 7
    assert provider["readyCount"] == 1
    assert [item["modelId"] for item in provider["readyEvidence"]] == ["current"]
