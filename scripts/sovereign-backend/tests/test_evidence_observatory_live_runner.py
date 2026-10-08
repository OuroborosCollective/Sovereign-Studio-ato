"""Live-runner transport contract tests. Simulated network only in test code.

These tests never count as actual HF Space/CAG runtime readbacks.
"""
from __future__ import annotations

import base64
import hashlib
import sys
import types
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import evidence_observatory_four_layer as four
import evidence_observatory_live_runner as runner
from evidence_observatory_contracts import sha256_json, sha256_text


REVISION = "d2f89c47b0286abef0f5f805b04f6e1eb90e2c57"


@pytest.mark.parametrize("n", [173, 174, 2, 1])
def test_live_claim_parser_remains_exact_and_bounded(n):
    assert runner._clean_claim(f"{n} is prime") == (f"{n} is prime", n)


@pytest.mark.parametrize("value", [
    "18446744073709551629 is prime", "173 is prime; DeleteDirectory[\"/\"]",
    "not a formal number", "23.4 is prime",
])
def test_live_claim_parser_rejects_unsupported_nondeterministic_inputs(value):
    with pytest.raises(four.FourLayerEvidenceError):
        runner._clean_claim(value)


@pytest.mark.parametrize("raw,expected", [
    ("True", True), ("False", False), ("true", True), ("false", False),
])
def test_cag_exact_boolean_normalization(raw, expected):
    assert runner._bool_from_wolfram_result(raw) is expected


@pytest.mark.parametrize("raw", [None, "False because likely", "2", '{"answer":true}', "", "Possibly True"])
def test_cag_ambiguous_results_cannot_influence_verdict(raw):
    with pytest.raises(four.FourLayerEvidenceError):
        runner._bool_from_wolfram_result(raw)


def _create_test_signer(monkeypatch, number):
    secret = Ed25519PrivateKey.generate()
    pub = secret.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key_id = hashlib.sha256(pub).hexdigest()
    monkeypatch.setattr(four, "EXPECTED_TRUST_KEY_ID", key_id)
    pub64 = base64.b64encode(pub).decode("ascii")
    anchor = {
        "schemaVersion": "sovereign.proof-router-issuer-trust-anchor.v1",
        "algorithm": "Ed25519",
        "keyId": key_id,
        "publicKeyBase64": pub64,
        "privateKeyPublished": False,
    }
    observed = number == 173
    receipt = {
        "schemaVersion": "sovereign.proof-router-receipt.v2",
        "route": "formal computation",
        "claim": f"{number} is prime",
        "implementationVersion": "2.1.3",
        "verifierAuthority": "bounded-local-deterministic",
        "wolframVerificationExpression": f"VerificationTest[PrimeQ[{number}], True]",
        "verdict": "PROVEN" if observed else "CONTRADICTED",
        "truthNotInferredFromAgreement": True,
        "claimSha256": sha256_text(f"{number} is prime"),
        "method": "deterministic-primality-64bit",
        "asserted": True,
        "observed": observed,
        "issuer": {
            "status": "SIGNED", "algorithm": "Ed25519",
            "keyId": key_id, "publicKeyBase64": pub64,
        },
    }
    receipt["receiptSha256"] = sha256_json(receipt)
    receipt["issuerSignatureBase64"] = base64.b64encode(
        secret.sign(bytes.fromhex(receipt["receiptSha256"]))
    ).decode("ascii")
    return anchor, receipt


def _install_test_transport(monkeypatch, tmp_path, *, number=173, first_stage="RUNNING",
                            final_stage="RUNNING", revision_changes=False):
    """Supply explicitly synthetic test transports, not an observed runtime."""
    anchor, receipt = _create_test_signer(monkeypatch, number)
    anchor_path = tmp_path / "issuer_trust_anchor.json"
    import json
    anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
    events = []
    state = {"reads": 0}
    class FakeApi:
        def space_info(self, space_id):
            events.append("space_info")
            assert space_id == runner.SPACE_ID
            state["reads"] += 1
            revision = "0" * 40 if revision_changes and state["reads"] > 1 else REVISION
            return types.SimpleNamespace(sha=revision)
        def get_space_runtime(self, space_id):
            events.append("runtime")
            assert space_id == runner.SPACE_ID
            return types.SimpleNamespace(
                stage=final_stage if state["reads"] >= 2 else first_stage,
                hardware="cpu-basic",
            )
    def test_downloader(**kw):
        events.append("pinned_anchor_download")
        assert kw["repo_id"] == runner.SPACE_ID
        assert kw["revision"] == REVISION
        return str(anchor_path)
    class FakeClient:
        def __init__(self, src, verbose=False):
            events.append("space_client")
            assert src == runner.SPACE_ID
        def predict(self, claim, api_name):
            events.append("formal_ui")
            assert claim == f"{number} is prime"
            assert api_name == "/formal_ui"
            return [receipt, {}]
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(
        HfApi=FakeApi, hf_hub_download=test_downloader
    ))
    monkeypatch.setitem(sys.modules, "gradio_client", types.SimpleNamespace(Client=FakeClient))
    from agent_runtime.adapters import wolfram_agenttools as cag
    def fake_cag(*, capability_id, payload, normalized_result_limit):
        events.append("cag_transport")
        assert capability_id == "wolfram.cag.compute"
        assert payload["code"] == f"PrimeQ[{number}]"
        return types.SimpleNamespace(
            status=cag.WolframCagStatus.SUCCEEDED_UNVERIFIED,
            normalized_result="True" if number == 173 else "False",
            request_hash="a" * 64, response_hash="b" * 64,
        )
    monkeypatch.setattr(cag, "execute_live_cag_request", fake_cag)
    return events


@pytest.mark.parametrize("number,verdict", [(173, "SUPPORTED"), (174, "REFUTED")])
def test_synthetic_transport_contract_produces_replayable_hash_bound_rows(
    monkeypatch, tmp_path, number, verdict,
):
    events = _install_test_transport(monkeypatch, tmp_path, number=number)
    result = runner.capture_live_four_layer_case(claim=f"{number} is prime")
    assert result["status"] == "LIVE_SPACE_AND_CAG_CAPTURED"
    assert result["publicationStatus"] == "NOT_PUBLISHED"
    assert result["notionStatus"] == "NOT_INDEXED"
    assert result["run"]["verdict"] == verdict
    assert result["run"]["wolfram"]["providerReceipt"]["status"] == "SUCCEEDED_UNVERIFIED"
    assert four.validate_four_layer_run(result["run"]) is True
    assert result["publicRow"]["workflowState"] == "PUBLISHABLE"
    assert events.index("formal_ui") < events.index("cag_transport")
    assert events.count("space_info") == 3
    projection = runner.notion_evidence_index(result)
    assert projection["publicationStatus"] == "NOT_HF_PUBLISHED_VERIFIED"
    assert projection["hfCommitOid"] is None


def test_stale_runtime_aborts_before_formal_and_provider_calls(monkeypatch, tmp_path):
    events = _install_test_transport(monkeypatch, tmp_path, first_stage="STOPPED")
    with pytest.raises(four.FourLayerEvidenceError, match="space_runtime_not_running"):
        runner.capture_live_four_layer_case(claim="173 is prime")
    assert "formal_ui" not in events
    assert "cag_transport" not in events


def test_revision_change_blocks_paid_provider_call(monkeypatch, tmp_path):
    events = _install_test_transport(monkeypatch, tmp_path, revision_changes=True)
    with pytest.raises(four.FourLayerEvidenceError, match="space_revision_changed_during_receipt"):
        runner.capture_live_four_layer_case(claim="173 is prime")
    assert "formal_ui" in events
    assert "cag_transport" not in events


def test_runtime_stops_after_cag_then_fails_closed(monkeypatch, tmp_path):
    events = _install_test_transport(monkeypatch, tmp_path, final_stage="STOPPED")
    with pytest.raises(four.FourLayerEvidenceError, match="space_revision_or_stage_changed_during_run"):
        runner.capture_live_four_layer_case(claim="173 is prime")
    assert "cag_transport" in events


def test_invalid_capture_cannot_publish_or_index(monkeypatch):
    with pytest.raises(four.FourLayerEvidenceError, match="publication_requires_live_space"):
        runner.publish_captured_four_layer_case({"status": "UNVERIFIED"})
    with pytest.raises(four.FourLayerEvidenceError, match="notion_projection_requires_live_capture"):
        runner.notion_evidence_index({"status": "UNVERIFIED"})


def test_live_runner_source_never_creates_hf_jobs_or_sandboxes():
    import ast
    source = (BACKEND / "evidence_observatory_live_runner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = [
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id in {"hf_jobs", "hf_sandbox", "create_sandbox"}
    ]
    assert names == []
