from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

try:
    import flask  # noqa: F401
except ModuleNotFoundError:
    flask_stub = types.ModuleType("flask")
    flask_stub.jsonify = lambda value=None, **kwargs: value if value is not None else kwargs
    flask_stub.request = types.SimpleNamespace(json={})
    sys.modules["flask"] = flask_stub

import openrouter_model_census as census
import openrouter_provider_runtime as runtime


REVISION = "1" * 40
IMAGE_DIGEST = "sha256:" + ("2" * 64)
CATALOG_SNAPSHOT = "a" * 64
MODEL_SET = "b" * 64
PROVIDER_POLICY = {
    "require_parameters": True,
    "allow_fallbacks": False,
    "data_collection": "deny",
    "zdr": True,
}


def _model(index: int) -> dict:
    return {
        "routeId": f"route-{index}",
        "modelId": f"vendor/model-{index}",
        "displayName": f"Model {index}",
        "priority": index,
        "catalogPayloadSha256": f"{index + 1:064x}",
    }


def _observed(model_id: str) -> dict:
    return {
        **census._base_result(
            model_id,
            classification="OBSERVED",
            input_sha256="c" * 64,
            latency_ms=11,
            http_status=200,
            request_id=f"req-{model_id.replace('/', '-')}",
        ),
        "resolvedModel": model_id,
        "modelIdentityMatch": True,
        "provider": "test-provider",
        "finishReason": "tool_calls",
        "toolCallCount": 1,
        "expectedToolPresent": True,
        "toolCallMatch": True,
        "argumentsSha256": "d" * 64,
        "outputSha256": "e" * 64,
        "usage": {
            "promptTokens": 10,
            "cachedPromptTokens": 0,
            "completionTokens": 4,
            "reasoningTokens": 0,
            "totalTokens": 14,
            "providerCostUsd": "0.00001",
        },
    }


def test_catalog_snapshot_binds_one_shared_catalog_and_unique_models() -> None:
    rows = [
        {
            "id": "route-1",
            "model_name": "One",
            "priority": 1,
            "config": {
                "providerModel": "vendor/one",
                "catalogPayloadSha256": "1" * 64,
                "catalogSnapshotSha256": CATALOG_SNAPSHOT,
            },
        },
        {
            "id": "route-2",
            "model_name": "Two",
            "priority": 2,
            "config": {
                "providerModel": "vendor/two",
                "catalogPayloadSha256": "2" * 64,
                "catalogSnapshotSha256": CATALOG_SNAPSHOT,
            },
        },
    ]

    def query(sql: str):
        assert "billingCategory" in sql
        return rows

    models, snapshot, model_set = census.catalog_snapshot(
        query,
        model_id_pattern=runtime._MODEL_ID_RE,
    )

    assert [item["modelId"] for item in models] == ["vendor/one", "vendor/two"]
    assert snapshot == CATALOG_SNAPSHOT
    rehash = census.canonical_sha256(
        [
            {
                "routeId": item["routeId"],
                "modelId": item["modelId"],
                "catalogPayloadSha256": item["catalogPayloadSha256"],
            }
            for item in models
        ]
    )
    assert model_set == rehash


def test_execute_census_sends_exactly_one_client_request_per_model_and_hashes_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    models = [_model(0), _model(1), _model(2)]
    attempts: list[str] = []

    def fake_request(key: str, *, model_id: str, **kwargs) -> dict:
        assert key == "protected-test-value"
        assert kwargs["provider_policy"] == PROVIDER_POLICY
        attempts.append(model_id)
        return _observed(model_id)

    monkeypatch.setattr(census, "request_model_once", fake_request)
    receipt = census.execute_census(
        key="protected-test-value",
        models=models,
        catalog_snapshot_sha256=CATALOG_SNAPSHOT,
        model_set_sha256=MODEL_SET,
        source_revision=REVISION,
        image_digest=IMAGE_DIGEST,
        operation="f" * 64,
        checkpoint_path=tmp_path / "checkpoint.jsonl",
        receipt_path=tmp_path / "receipt.json",
        openrouter_base_url="https://openrouter.example/api/v1",
        request_headers=lambda _key: {"Authorization": "protected"},
        provider_policy=PROVIDER_POLICY,
        parallelism=1,
    )

    assert attempts == [item["modelId"] for item in models]
    assert receipt["catalogModelCount"] == 3
    assert receipt["clientRequestAttempts"] == 3
    assert receipt["oneRequestPerModelClientInvariantVerified"] is True
    assert receipt["providerHttpResponsesObserved"] == 3
    assert receipt["allProviderHttpResponsesObserved"] is True
    assert receipt["summary"]["classificationCounts"] == {"OBSERVED": 3}
    assert receipt["summary"]["observedProviderCostUsd"] == "0.00003"
    assert receipt["automaticFallback"] is False
    assert receipt["clientAutomaticRetries"] == 0
    assert receipt["truthVerdict"] == "NOT_ASSERTED"
    assert receipt["leaderboardEnabled"] is False
    assert receipt["semanticQualityClaimed"] is False
    assert receipt["rawResponsesPersisted"] is False
    assert receipt["secretValuesReturned"] is False
    assert len({item["modelId"] for item in receipt["results"]}) == 3
    assert all(item["requestCount"] == 1 for item in receipt["results"])

    expected = dict(receipt)
    receipt_hash = expected.pop("receiptSha256")
    assert census.canonical_sha256(expected) == receipt_hash
    assert census.load_receipt(tmp_path / "receipt.json")["receiptSha256"] == receipt_hash

    checkpoint_events = [
        json.loads(line)
        for line in (tmp_path / "checkpoint.jsonl").read_text("utf-8").splitlines()
    ]
    assert [event["type"] for event in checkpoint_events] == [
        "attempt",
        "result",
        "attempt",
        "result",
        "attempt",
        "result",
    ]


def test_recovery_never_retries_attempt_marked_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    models = [_model(0), _model(1)]
    checkpoint = tmp_path / "checkpoint.jsonl"
    attempted_input = "7" * 64
    census._append_checkpoint(
        checkpoint,
        {
            "type": "attempt",
            "modelId": models[0]["modelId"],
            "inputSha256": attempted_input,
            "catalogPayloadSha256": models[0]["catalogPayloadSha256"],
        },
    )
    calls: list[str] = []

    def fake_request(_key: str, *, model_id: str, **_kwargs) -> dict:
        calls.append(model_id)
        return _observed(model_id)

    monkeypatch.setattr(census, "request_model_once", fake_request)
    receipt = census.execute_census(
        key="protected-test-value",
        models=models,
        catalog_snapshot_sha256=CATALOG_SNAPSHOT,
        model_set_sha256=MODEL_SET,
        source_revision=REVISION,
        image_digest=IMAGE_DIGEST,
        operation="6" * 64,
        checkpoint_path=checkpoint,
        receipt_path=tmp_path / "receipt.json",
        openrouter_base_url="https://openrouter.example/api/v1",
        request_headers=lambda _key: {},
        provider_policy=PROVIDER_POLICY,
        parallelism=1,
    )

    assert calls == [models[1]["modelId"]]
    first = receipt["results"][0]
    assert first["classification"] == "INTERRUPTED_UNKNOWN"
    assert first["failureFamily"] == "openrouter_census_interrupted_after_attempt_marker"
    assert first["inputSha256"] == attempted_input
    assert receipt["clientRequestAttempts"] == 2
    assert receipt["oneRequestPerModelClientInvariantVerified"] is True
    assert receipt["providerHttpResponsesObserved"] == 1
    assert receipt["allProviderHttpResponsesObserved"] is False
    assert receipt["summary"]["interruptedUnknownCount"] == 1


def test_output_evidence_hashes_raw_content_and_accepts_only_exact_marker() -> None:
    good = census._output_evidence(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "census_ok",
                                    "arguments": '{"value":"OK"}',
                                }
                            }
                        ],
                    },
                }
            ]
        }
    )
    assert good["classification"] == "OBSERVED"
    assert good["toolCallMatch"] is True
    assert "arguments" not in good

    raw_text = "partial private-ish model output"
    budget = census._output_evidence(
        {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"content": raw_text, "tool_calls": []},
                }
            ]
        }
    )
    assert budget["classification"] == "BUDGET_EXHAUSTED"
    assert budget["contentSha256"] == hashlib.sha256(raw_text.encode()).hexdigest()
    assert raw_text not in json.dumps(budget)


def test_internal_reserved_census_route_reuses_existing_operator_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        from flask import Flask, jsonify
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Flask is validated in the full backend CI image")

    app = Flask(__name__)
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "owner-bridge-key")
    captured: dict = {}

    def fake_operation(*, route_id: str, expected_models: int, query, audit):
        del query, audit
        captured.update(route_id=route_id, expected_models=expected_models)
        return jsonify(
            {
                "ok": True,
                "status": "census_running",
                "routeId": route_id,
                "secretValuesReturned": False,
            }
        )

    monkeypatch.setattr(runtime, "_openrouter_census_operation", fake_operation)
    runtime.register_openrouter_provider_runtime(
        app,
        require_admin=lambda fn: fn,
        require_session=lambda fn: fn,
        query=lambda *_args, **_kwargs: {},
        get_connection=lambda: (_ for _ in ()).throw(AssertionError("not expected")),
        audit=lambda *_args, **_kwargs: None,
    )

    response = app.test_client().post(
        "/api/internal/llm/openrouter/activate",
        headers={"X-Sovereign-Owner-Request-Key": "owner-bridge-key"},
        json={"routeId": "openrouter-paid-census-291"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "census_running"
    assert payload["secretValuesReturned"] is False
    assert captured == {
        "route_id": "openrouter-paid-census-291",
        "expected_models": 291,
    }


def test_status_contract_exposes_only_bounded_latest_census_state() -> None:
    source = (BACKEND / "openrouter_provider_runtime.py").read_text("utf-8")

    assert 'OPENROUTER_CENSUS_ROUTE_PREFIX = "openrouter-paid-census-"' in source
    assert '"latestCensus": latest_census' in source
    assert '"censusReceipt": receipt' in source
    assert '"providerRequestsRepeated": False' in source
    assert "fcntl.LOCK_EX | fcntl.LOCK_NB" in source
    assert "daemon=True" in source
    assert "rawResponsesPersisted" in (
        BACKEND / "openrouter_model_census.py"
    ).read_text("utf-8")
