"""Regressions for signed four-layer Observatory evidence; no fake runtime truth."""
from __future__ import annotations

import base64
import copy
import hashlib
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import evidence_observatory_four_layer as four
from evidence_observatory_contracts import sha256_json, sha256_text
from evidence_observatory_publisher import (
    build_huggingface_publish_plan,
    scan_public_payload,
)


REVISION = "d2f89c47b0286abef0f5f805b04f6e1eb90e2c57"
CAPTURED = "2026-10-08T12:00:00Z"
RESEARCH = [
    {"url": "https://www.alphaxiv.org/abs/2607.28374", "observedAt": CAPTURED},
    {"url": "https://arxiv.org/abs/2608.18312", "observedAt": CAPTURED},
]


def _signed_inputs(monkeypatch, *, prime: int = 173):
    # Real Ed25519 cryptography with ephemeral test-only keys. The fixture never
    # claims that an actual public Space executed a live request.
    private = Ed25519PrivateKey.generate()
    pub = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    public_b64 = base64.b64encode(pub).decode("ascii")
    key_id = hashlib.sha256(pub).hexdigest()
    monkeypatch.setattr(four, "EXPECTED_TRUST_KEY_ID", key_id)
    claim = f"{prime} is prime"
    observed = prime == 173
    anchor = {
        "schemaVersion": "sovereign.proof-router-issuer-trust-anchor.v1",
        "algorithm": "Ed25519",
        "keyId": key_id,
        "publicKeyBase64": public_b64,
        "privateKeyPublished": False,
        "secretEnvName": "TEST_ONLY_SHOULD_NOT_BE_IN_PUBLIC_RUN",
    }
    receipt = {
        "schemaVersion": "sovereign.proof-router-receipt.v2",
        "implementationVersion": "2.1.3",
        "route": "formal computation",
        "claim": claim,
        "verifierAuthority": "bounded-local-deterministic",
        "wolframVerificationExpression": f"VerificationTest[PrimeQ[{prime}], True]",
        "verdict": "PROVEN" if observed else "CONTRADICTED",
        "truthNotInferredFromAgreement": True,
        "claimSha256": sha256_text(claim),
        "method": "deterministic-primality-64bit",
        "asserted": True,
        "observed": observed,
        "issuer": {
            "status": "SIGNED",
            "algorithm": "Ed25519",
            "keyId": key_id,
            "publicKeyBase64": public_b64,
        },
    }
    receipt["receiptSha256"] = sha256_json(receipt)
    receipt["issuerSignatureBase64"] = base64.b64encode(
        private.sign(bytes.fromhex(receipt["receiptSha256"]))
    ).decode("ascii")
    wolfram = {
        "source": "Wolfram",
        "tool": "WolframLanguageEvaluator",
        "expression": f"PrimeQ[{prime}]",
        "result": observed,
        "observedAt": CAPTURED,
    }
    return dict(
        claim=claim, space_revision=REVISION, receipt=receipt,
        trust_anchor=anchor, wolfram_observation=wolfram,
        research_refs=RESEARCH, captured_at=CAPTURED,
    )


def _run(monkeypatch, prime=173):
    return four.build_four_layer_run(**_signed_inputs(monkeypatch, prime=prime))


@pytest.mark.parametrize("number,expected", [(173, "SUPPORTED"), (174, "REFUTED")])
def test_signed_prime_positive_and_negative_runs_pass_legacy_gate(monkeypatch, number, expected):
    run = _run(monkeypatch, number)
    assert run["verdict"] == expected
    assert "secretEnvName" not in run["revisionTrustAnchor"]
    assert four.validate_four_layer_run(run) is True
    row = four.build_four_layer_public_row(run)
    assert row["verdict"] == expected
    assert row["workflowState"] == "PUBLISHABLE"
    assert row["gateReport"]["passed"] is True
    assert row["evidencePassport"]["proofReceiptAuthenticated"] is True
    assert row["fourLayerRunRecord"]["signedReceipt"]["issuerSignatureBase64"]
    assert row["runBundleSha256"] == run["bundleSha256"]
    assert scan_public_payload([row])["findingCount"] == 0


def test_canonical_id_and_hash_reproducible(monkeypatch):
    inputs = _signed_inputs(monkeypatch)
    first = four.build_four_layer_run(**inputs)
    second = four.build_four_layer_run(**inputs)
    assert first == second
    assert first["runId"].startswith("obs4-")
    assert len(first["bundleSha256"]) == 64


@pytest.mark.parametrize("field,value,error", [
    ("receiptSha256", "f" * 64, "receipt_hash_mismatch"),
    ("issuerSignatureBase64", "AAAAAAAAAAA=", "receipt_signature_invalid"),
    ("schemaVersion", "untrusted.v99", "receipt_schema"),
    ("observed", False, "receipt_hash_mismatch"),
    ("claimSha256", "a" * 64, "receipt_claim_mismatch"),
    ("issuer", None, "receipt_unsigned"),
])
def test_unsigned_or_modified_receipt_never_promotes(monkeypatch, field, value, error):
    inputs = _signed_inputs(monkeypatch)
    inputs["receipt"] = copy.deepcopy(inputs["receipt"])
    inputs["receipt"][field] = value
    with pytest.raises(four.FourLayerEvidenceError, match=error):
        four.build_four_layer_run(**inputs)


def test_untrusted_issuer_anchor_not_adopted(monkeypatch):
    inputs = _signed_inputs(monkeypatch)
    monkeypatch.setattr(four, "EXPECTED_TRUST_KEY_ID", "1" * 64)
    with pytest.raises(four.FourLayerEvidenceError, match="anchor_not_trusted_at_pinned_key_id"):
        four.build_four_layer_run(**inputs)


@pytest.mark.parametrize("bad", [
    {"expression": "PrimeQ[174]"},
    {"result": False},
    {"result": "True"},
    {"source": "some-unidentified-provider"},
    {"tool": "anonymous-evaluator"},
])
def test_wolfram_mismatch_abstains_fail_closed(monkeypatch, bad):
    inputs = _signed_inputs(monkeypatch)
    inputs["wolfram_observation"] = {**inputs["wolfram_observation"], **bad}
    with pytest.raises(four.FourLayerEvidenceError):
        four.build_four_layer_run(**inputs)


@pytest.mark.parametrize("bad", [
    [{"url": "http://www.alphaxiv.org/abs/2607.28374", "observedAt": CAPTURED}],
    [{"url": "https://evil.test/abs/2607.28374", "observedAt": CAPTURED}],
    [{"url": "https://www.alphaxiv.org/abs/2607.28374", "observedAt": CAPTURED}] * 2,
    [],
])
def test_research_context_origin_url_policy(monkeypatch, bad):
    inputs = _signed_inputs(monkeypatch)
    inputs["research_refs"] = bad
    with pytest.raises(four.FourLayerEvidenceError):
        four.build_four_layer_run(**inputs)


@pytest.mark.parametrize("key", [
    "bundleSha256", "receiptSha256", "truthBoundary", "spaceRevision",
    "runId", "claim", "signedReceipt", "research", "wolfram",
])
def test_mutated_bound_run_record_is_rejected(monkeypatch, key):
    run = _run(monkeypatch)
    tampered = copy.deepcopy(run)
    if isinstance(tampered[key], dict):
        tampered[key]["unexpectedTamper"] = True
    elif isinstance(tampered[key], list):
        tampered[key].append({"url": "https://arxiv.org/abs/1234.56789", "observedAt": CAPTURED})
    else:
        tampered[key] = str(tampered[key]) + "tampered"
    with pytest.raises(four.FourLayerEvidenceError):
        four.validate_four_layer_run(tampered)


def test_live_cag_transport_receipt_is_explicitly_unverified_not_semantic_truth(monkeypatch):
    inputs = _signed_inputs(monkeypatch)
    inputs["wolfram_observation"] = {
        **inputs["wolfram_observation"],
        "tool": "WolframCAG",
        "providerReceipt": {
            "component": "WolframLanguageComputation",
            "status": "SUCCEEDED_UNVERIFIED",
            "requestSha256": "a" * 64,
            "responseSha256": "b" * 64,
            "normalizedResult": "True",
            "truthBoundary": "provider_transport_not_semantic_truth",
        },
    }
    record = four.build_four_layer_run(**inputs)
    assert four.validate_four_layer_run(record)
    row = four.build_four_layer_public_row(record)
    assert row["gateReport"]["passed"] is True
    assert row["truthBoundary"]["wolframObservationCryptographicallyAuthenticated"] is False
    assert row["truthBoundary"]["spaceRevisionCryptographicallySignedInReceipt"] is False
    assert row["fourLayerRunRecord"]["wolfram"]["providerReceipt"]["status"] == "SUCCEEDED_UNVERIFIED"
    assert scan_public_payload([row])["findingCount"] == 0
    for changed in ({"status": "PROVEN"}, {"normalizedResult": "False"}, {"rawBody": "NOT_ALLOWED"}):
        tampered = copy.deepcopy(inputs)
        tampered["wolfram_observation"]["providerReceipt"].update(changed)
        with pytest.raises(four.FourLayerEvidenceError):
            four.build_four_layer_run(**tampered)


def test_claim_specific_method_and_range_enforced(monkeypatch):
    inputs = _signed_inputs(monkeypatch)
    inputs["claim"] = "18446744073709551629 is prime"
    with pytest.raises(four.FourLayerEvidenceError):
        four.build_four_layer_run(**inputs)
    assert four._prime_64(2) is True
    assert four._prime_64(1) is False
    assert four._prime_64(2**64 - 1) is False


def test_publication_plan_is_staging_only_and_rights_gated(monkeypatch):
    row = four.build_four_layer_public_row(_run(monkeypatch))
    rights_text = "Authorized only for one exact public-safe four-layer formal evidence run to personal Thorsu staging."
    rights = {
        "schemaVersion": "sovereign.hf-publication-rights.v1",
        "status": "AUTHORIZED",
        "rightsHolder": "Owner",
        "authorizedEntity": "Sovereign Evidence Observatory staging publisher",
        "purpose": "Publish verified public-safe research evidence",
        "scope": "single case, staging only",
        "licenseId": "other",
        "authorizedTarget": four.DATASET_ID,
        "authorizedRevision": "staging-atlas",
        "authorizedCaseIds": [row["caseId"]],
        "authorizationRef": "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        "authorizationText": rights_text,
        "authorizationSha256": sha256_text(rights_text),
        "conditions": ["staging only", "public-safe signed receipts", "no secret material"],
    }
    plan = build_huggingface_publish_plan(
        rows=[row], repo_id=four.DATASET_ID, revision="staging-atlas", license_rights=rights
    )
    assert plan["repoId"] == four.DATASET_ID
    assert plan["revision"] == "staging-atlas"
    assert plan["privacyScan"]["findingCount"] == 0
    with pytest.raises(RuntimeError, match="huggingface_direct_main_publish_forbidden"):
        build_huggingface_publish_plan(
            rows=[row], repo_id=four.DATASET_ID, revision="main", license_rights=rights
        )
    rights["status"] = "UNAUTHORIZED"
    with pytest.raises(RuntimeError):
        build_huggingface_publish_plan(
            rows=[row], repo_id=four.DATASET_ID, revision="staging-atlas", license_rights=rights
        )
