"""Four-layer Observatory evidence binding. Pure contracts; no network writes.

A signed Space receipt and a Wolfram MCP observation are different evidence
sources. Notion/alphaXiv are provenance/context, never authorities for runtime.
The public case must still pass the existing rights, privacy and HF readback gates.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime
from typing import Any

from evidence_observatory_contracts import (
    build_evidence_passport, canonical_json, evaluate_evidence_case,
    normalized_claim, sha256_json, sha256_text,
)

SCHEMA_VERSION = "sovereign.evidence-four-layer-run.v1"
SPACE_ID = "Thorsu/sovereign-evidence-observatory"
DATASET_ID = "Thorsu/sovereign-evidence-observatory"
# Independently checked against the pinned public Space issuer_trust_anchor.json.
# Key rotation requires an explicit reviewed release; never adopt a receipt key as trust.
EXPECTED_TRUST_KEY_ID = "7fc8cdc997b1fadc4c0b183789fd191e790fa12d8e470e9ba7a3d9de6c39b685"
TRUTH_BOUNDARY = "signed_execution_receipt_and_independent_formal_reference_are_not_general_semantic_truth"
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_PRIME = re.compile(r"^([0-9]+) is prime$", re.I)
_ARXIV = re.compile(r"^https://(?:www\.)?(?:alphaxiv\.org|arxiv\.org)/abs/([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?/?$")
MAX_BYTES = 150_000


class FourLayerEvidenceError(ValueError):
    """Fail-closed validation error for unverifiable four-layer inputs."""


def _require(cond: bool, failure: str) -> None:
    if not cond:
        raise FourLayerEvidenceError(failure)


def _timestamp(value: Any) -> str:
    _require(isinstance(value, str) and len(value) <= 40, "timestamp_missing_or_unbounded")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(dt.tzinfo is not None, "timestamp_timezone_required")
    except (ValueError, TypeError) as exc:
        raise FourLayerEvidenceError("timestamp_invalid") from exc
    return value


def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA64.fullmatch(value) is not None


def _prime_64(n: int) -> bool:
    """Deterministic Miller-Rabin for integer 0 <= n < 2^64."""
    _require(0 <= n < 2**64, "formal_input_outside_64bit")
    if n < 2:
        return False
    small = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    if n in small:
        return True
    if any(n % p == 0 for p in small):
        return False
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 325, 9375, 28178, 450775, 9780504, 1795265022):
        if a % n == 0:
            continue
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _verify_signed_receipt(claim: str, receipt: dict[str, Any], anchor: dict[str, Any]) -> bool:
    """Validate exact Proof Router V2 hashing and detached Ed25519 signature.

    The external anchor MUST be obtained at the pinned Hub Space revision.
    Never trust a public key merely embedded in the receipt itself.
    """
    _require(isinstance(anchor, dict) and isinstance(receipt, dict), "receipt_or_anchor_not_object")
    _require(anchor.get("schemaVersion") == "sovereign.proof-router-issuer-trust-anchor.v1", "anchor_schema")
    _require(anchor.get("algorithm") == "Ed25519", "anchor_algorithm")
    _require(anchor.get("privateKeyPublished") is False, "anchor_private_key_boundary")
    public_b64 = anchor.get("publicKeyBase64")
    _require(isinstance(public_b64, str), "anchor_public_key_missing")
    try:
        raw = base64.b64decode(public_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise FourLayerEvidenceError("anchor_public_key_decode") from exc
    _require(len(raw) == 32, "anchor_public_key_length")
    _require(hashlib.sha256(raw).hexdigest() == anchor.get("keyId"), "anchor_key_id_mismatch")
    _require(anchor["keyId"] == EXPECTED_TRUST_KEY_ID, "anchor_not_trusted_at_pinned_key_id")
    _require(receipt.get("schemaVersion") == "sovereign.proof-router-receipt.v2", "receipt_schema")
    _require(receipt.get("truthNotInferredFromAgreement") is True, "agreement_truth_boundary")
    _require(receipt.get("route") == "formal computation", "formal_route_required")
    _require(receipt.get("claim") == normalized_claim(claim), "receipt_exact_claim_text_mismatch")
    _require(receipt.get("claimSha256") == sha256_text(normalized_claim(claim)), "receipt_claim_mismatch")
    _require(receipt.get("verifierAuthority") == "bounded-local-deterministic", "receipt_verifier_authority")
    _require(isinstance(receipt.get("implementationVersion"), str) and receipt["implementationVersion"], "receipt_implementation_missing")
    _require(receipt.get("method") == "deterministic-primality-64bit", "receipt_method_mismatch")
    prime = _PRIME.fullmatch(normalized_claim(claim))
    _require(prime is not None, "receipt_claim_not_replayable_prime")
    _require(
        receipt.get("wolframVerificationExpression") == f"VerificationTest[PrimeQ[{int(prime.group(1))}], True]",
        "receipt_wolfram_reference_mismatch",
    )
    issuer = receipt.get("issuer")
    _require(isinstance(issuer, dict) and issuer.get("status") == "SIGNED", "receipt_unsigned")
    _require(issuer.get("algorithm") == "Ed25519", "receipt_issuer_algorithm")
    _require(issuer.get("keyId") == anchor["keyId"], "issuer_anchor_key_mismatch")
    _require(issuer.get("publicKeyBase64") == public_b64, "issuer_embedded_key_mismatch")
    receipt_sha = receipt.get("receiptSha256")
    _require(_sha(receipt_sha), "receipt_sha_invalid")
    to_hash = dict(receipt)
    to_hash.pop("receiptSha256", None)
    to_hash.pop("issuerSignatureBase64", None)
    _require(sha256_json(to_hash) == receipt_sha, "receipt_hash_mismatch")
    signature_b64 = receipt.get("issuerSignatureBase64")
    _require(isinstance(signature_b64, str), "receipt_signature_missing")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(raw).verify(signature, bytes.fromhex(receipt_sha))
    except Exception as exc:
        raise FourLayerEvidenceError("receipt_signature_invalid_or_crypto_unavailable") from exc
    return True


def build_four_layer_run(
    *, claim: str, space_revision: str, receipt: dict[str, Any], trust_anchor: dict[str, Any],
    wolfram_observation: dict[str, Any], research_refs: list[dict[str, Any]],
    captured_at: str,
) -> dict[str, Any]:
    """Bind independently acquired evidence. No implied live transport.

    Input origin is the operator's responsibility; this layer validates the
    Space signature, receipt replay, Wolfram expression/value relationship
    and research-record provenance. A Wolfram result here remains a reported
    observation unless separate provider-authentication evidence is supplied.
    """
    claim = normalized_claim(claim)
    _require(0 < len(claim.encode("utf-8")) <= 2000, "claim_invalid_or_unbounded")
    _require(isinstance(space_revision, str) and _SHA40.fullmatch(space_revision) is not None, "space_revision_invalid")
    _timestamp(captured_at)
    _require(len(canonical_json(receipt).encode("utf-8")) < MAX_BYTES, "receipt_unbounded")
    _verify_signed_receipt(claim, receipt, trust_anchor)
    # Drop descriptive secret metadata; publishable records contain only the
    # immutable public trust anchor, not private key names or environment hints.
    public_anchor = {
        "schemaVersion": trust_anchor["schemaVersion"],
        "algorithm": trust_anchor["algorithm"],
        "keyId": trust_anchor["keyId"],
        "publicKeyBase64": trust_anchor["publicKeyBase64"],
        "privateKeyPublished": False,
    }

    match = _PRIME.fullmatch(claim)
    _require(match is not None, "replay_unsupported_formal_claim")
    n = int(match.group(1))
    observed = _prime_64(n)
    _require(receipt.get("asserted") is True, "receipt_asserted_mismatch")
    _require(receipt.get("observed") is observed, "receipt_replay_observation_mismatch")
    verdict = "SUPPORTED" if observed else "REFUTED"
    _require(receipt.get("verdict") == ("PROVEN" if observed else "CONTRADICTED"), "receipt_verdict_replay_mismatch")

    _require(isinstance(wolfram_observation, dict), "wolfram_observation_required")
    expected_expression = f"PrimeQ[{n}]"
    _require(wolfram_observation.get("expression") == expected_expression, "wolfram_query_mismatch")
    _require(type(wolfram_observation.get("result")) is bool, "wolfram_result_not_boolean")
    _require(wolfram_observation["result"] is observed, "independent_verifier_disagreement")
    _timestamp(wolfram_observation.get("observedAt"))
    _require(wolfram_observation.get("tool") in {"WolframLanguageEvaluator", "WolframContext", "WolframCAG"}, "wolfram_source_invalid")
    _require(wolfram_observation.get("source") == "Wolfram", "wolfram_origin_missing")
    provider = wolfram_observation.get("providerReceipt")
    if wolfram_observation["tool"] == "WolframCAG":
        _require(isinstance(provider, dict), "wolfram_cag_provider_receipt_required")
        _require(provider.get("component") == "WolframLanguageComputation", "wolfram_cag_component")
        _require(provider.get("status") == "SUCCEEDED_UNVERIFIED", "wolfram_cag_transport_status")
        _require(_sha(provider.get("requestSha256")) and _sha(provider.get("responseSha256")), "wolfram_cag_hashes")
        _require(provider.get("normalizedResult") == ("True" if observed else "False"), "wolfram_cag_normalized_mismatch")
        _require(provider.get("truthBoundary") == "provider_transport_not_semantic_truth", "wolfram_cag_truth_boundary")
        # No credentials, raw provider body, arbitrary request text or secret fingerprints.
        _require(set(provider) == {"component", "status", "requestSha256", "responseSha256", "normalizedResult", "truthBoundary"}, "wolfram_cag_receipt_field_boundary")
    else:
        _require(provider is None, "wolfram_unverified_tool_must_not_claim_cag_receipt")
    # An external tool response is observed evidence, not a provider-signed attestation.
    wolfram = {
        "source": "Wolfram",
        "tool": wolfram_observation["tool"],
        "expression": expected_expression,
        "result": observed,
        "observedAt": wolfram_observation["observedAt"],
        "originAuthentication": "NOT_CRYPTOGRAPHICALLY_VERIFIED",
    }
    if provider is not None:
        wolfram["providerReceipt"] = dict(provider)
    wolfram["normalizedObservationSha256"] = sha256_json(wolfram)

    _require(isinstance(research_refs, list) and 1 <= len(research_refs) <= 12, "research_refs_required")
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for reference in research_refs:
        _require(isinstance(reference, dict), "research_ref_not_object")
        url = reference.get("url")
        _require(isinstance(url, str) and _ARXIV.fullmatch(url) is not None, "research_locator_not_allowlisted")
        _require(url not in seen, "research_ref_duplicate")
        seen.add(url)
        _timestamp(reference.get("observedAt"))
        # A paper is methodological context, not proof of a specific number.
        entry = {
            "url": url,
            "observedAt": reference["observedAt"],
            "role": "METHODOLOGICAL_CONTEXT_ONLY",
            "peerReviewStatus": "UNVERIFIED",
        }
        entry["citationRecordSha256"] = sha256_json(entry)
        refs.append(entry)
    refs.sort(key=lambda x: x["url"])
    run = {
        "schemaVersion": SCHEMA_VERSION,
        "claim": claim,
        "claimSha256": sha256_text(claim),
        "spaceId": SPACE_ID,
        "spaceRevision": space_revision,
        "spaceRevisionBinding": "HUB_LIVE_READBACK_NOT_SIGNED_IN_RECEIPT",
        "observatoryImplementationVersion": receipt["implementationVersion"],
        "capturedAt": captured_at,
        "receiptSha256": receipt["receiptSha256"],
        "receiptIssuerKeyId": trust_anchor["keyId"],
        "signedReceipt": receipt,
        "revisionTrustAnchor": public_anchor,
        "signedReceiptAuthenticated": True,
        "formalReplayVerified": True,
        "wolfram": wolfram,
        "research": refs,
        "verdict": verdict,
        "truthBoundary": TRUTH_BOUNDARY,
        "truthNotInferredFromAgreement": True,
    }
    run["runId"] = "obs4-" + sha256_json(run)[:24]
    run["bundleSha256"] = sha256_json(run)
    return run


def validate_four_layer_run(record: dict[str, Any]) -> bool:
    _require(isinstance(record, dict), "run_not_object")
    _require(record.get("schemaVersion") == SCHEMA_VERSION, "run_schema")
    _require(record.get("spaceId") == SPACE_ID, "space_identity")
    _require(record.get("spaceRevisionBinding") == "HUB_LIVE_READBACK_NOT_SIGNED_IN_RECEIPT", "space_revision_binding_overstated")
    _require(record.get("observatoryImplementationVersion") == record.get("signedReceipt", {}).get("implementationVersion"), "implementation_identity_mismatch")
    _require(isinstance(record.get("spaceRevision"), str) and _SHA40.fullmatch(record["spaceRevision"]) is not None, "space_revision")
    _require(_timestamp(record.get("capturedAt")) == record["capturedAt"], "capture_timestamp")
    _require(record.get("truthBoundary") == TRUTH_BOUNDARY, "run_truth_boundary")
    _require(record.get("truthNotInferredFromAgreement") is True, "run_agreement_boundary")
    _require(record.get("signedReceiptAuthenticated") is True and record.get("formalReplayVerified") is True, "run_proof_missing")
    _require(_sha(record.get("claimSha256")) and record["claimSha256"] == sha256_text(normalized_claim(record.get("claim"))), "run_claim_hash")
    _require(_sha(record.get("receiptSha256")) and record.get("receiptIssuerKeyId") == EXPECTED_TRUST_KEY_ID, "run_receipt_identity")
    _require(isinstance(record.get("signedReceipt"), dict) and isinstance(record.get("revisionTrustAnchor"), dict), "run_signed_receipt_missing")
    _verify_signed_receipt(normalized_claim(record["claim"]), record["signedReceipt"], record["revisionTrustAnchor"])
    _require(record["signedReceipt"].get("receiptSha256") == record["receiptSha256"], "run_receipt_digest_disagreement")
    _require(record.get("verdict") in {"SUPPORTED", "REFUTED"}, "run_verdict")
    _require(record["signedReceipt"].get("method") == "deterministic-primality-64bit", "run_formal_method")
    _require(record["signedReceipt"].get("asserted") is True, "run_asserted")
    _require(record["signedReceipt"].get("issuer", {}).get("keyId") == EXPECTED_TRUST_KEY_ID, "run_issuer_key")
    _require(isinstance(record.get("wolfram"), dict), "run_wolfram")
    _require(record["wolfram"].get("originAuthentication") == "NOT_CRYPTOGRAPHICALLY_VERIFIED", "run_wolfram_origin_label")
    wf = dict(record["wolfram"])
    _require(wf.get("source") == "Wolfram", "run_wolfram_source")
    _require(wf.get("tool") in {"WolframLanguageEvaluator", "WolframContext", "WolframCAG"}, "run_wolfram_tool")
    _timestamp(wf.get("observedAt"))
    digest = wf.pop("normalizedObservationSha256", None)
    _require(_sha(digest) and digest == sha256_json(wf), "run_wolfram_hash")
    match = _PRIME.fullmatch(normalized_claim(record["claim"]))
    _require(match is not None, "run_unsupported_replay")
    n = int(match.group(1))
    result = _prime_64(n)
    _require(record["signedReceipt"].get("observed") is result, "run_signed_receipt_replay")
    _require(record["signedReceipt"].get("verdict") == ("PROVEN" if result else "CONTRADICTED"), "run_signed_receipt_verdict")
    _require(wf.get("expression") == f"PrimeQ[{n}]" and wf.get("result") is result, "run_wolfram_replay")
    provider = wf.get("providerReceipt")
    if wf.get("tool") == "WolframCAG":
        _require(isinstance(provider, dict) and set(provider) == {"component", "status", "requestSha256", "responseSha256", "normalizedResult", "truthBoundary"}, "run_cag_provider_receipt")
        _require(provider["component"] == "WolframLanguageComputation" and provider["status"] == "SUCCEEDED_UNVERIFIED", "run_cag_status")
        _require(_sha(provider.get("requestSha256")) and _sha(provider.get("responseSha256")), "run_cag_hash")
        _require(provider["normalizedResult"] == ("True" if result else "False"), "run_cag_result")
        _require(provider["truthBoundary"] == "provider_transport_not_semantic_truth", "run_cag_truth_boundary")
    else:
        _require(provider is None, "run_unverified_tool_provider_boundary")
    _require(record["verdict"] == ("SUPPORTED" if result else "REFUTED"), "run_verdict_replay")
    _require(isinstance(record.get("research"), list) and record["research"], "run_research")
    for ref in record["research"]:
        _require(isinstance(ref, dict) and _ARXIV.fullmatch(str(ref.get("url") or "")) is not None, "run_research_url")
        entry = dict(ref)
        digest = entry.pop("citationRecordSha256", None)
        _require(_sha(digest) and digest == sha256_json(entry), "run_research_hash")
        _require(entry.get("role") == "METHODOLOGICAL_CONTEXT_ONLY" and entry.get("peerReviewStatus") == "UNVERIFIED", "research_cannot_decide_claim")
    _require(isinstance(record.get("runId"), str), "run_id")
    payload = dict(record)
    bundle = payload.pop("bundleSha256", None)
    _require(_sha(bundle) and bundle == sha256_json(payload), "run_bundle_hash_mismatch")
    run_id = payload.pop("runId")
    _require(run_id == "obs4-" + sha256_json(payload)[:24], "run_id_mismatch")
    return True


def build_four_layer_public_row(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a validated run to the existing publisher's gated case format."""
    validate_four_layer_run(record)
    observed_at = record["capturedAt"]
    receipt_id = "space-receipt-" + record["receiptSha256"][:24]
    source_space_id = "space-" + record["receiptSha256"][:24]
    source_wolfram_id = "wolfram-" + record["wolfram"]["normalizedObservationSha256"][:24]
    sources = [
        {
            "id": source_space_id, "sourceType": "runtime",
            "locator": f"https://huggingface.co/spaces/{SPACE_ID}/tree/{record['spaceRevision']}",
            "contentSha256": record["receiptSha256"], "observedAt": observed_at,
            "label": "Signed formal receipt; Space revision separately read from Hub",
            "provenance": {"originFamily": "thorsu-proof-router", "hashScope": "signed-receipt-canonical-body", "spaceRevision": record["spaceRevision"], "revisionBinding": "EXTERNAL_HUB_READBACK_NOT_SIGNED_RECEIPT"},
        },
        {
            "id": source_wolfram_id, "sourceType": "formal",
            "locator": "https://reference.wolfram.com/language/ref/PrimeQ.html",
            "contentSha256": record["wolfram"]["normalizedObservationSha256"],
            "observedAt": record["wolfram"]["observedAt"],
            "label": "Independent Wolfram tool observation (not provider-signed)",
            "provenance": {"originFamily": "wolfram-independent-observation", "hashScope": "normalized-observation"},
        },
    ]
    for index, ref in enumerate(record["research"]):
        sources.append({
            "id": f"research-{index}-{ref['citationRecordSha256'][:12]}", "sourceType": "secondary",
            "locator": ref["url"], "contentSha256": ref["citationRecordSha256"],
            "observedAt": ref["observedAt"], "label": "Methodological related work",
            "provenance": {"originFamily": f"related-work-{index}", "hashScope": "citation-metadata", "decisive": False},
        })
    payload = {
        "claim": record["claim"], "claimSha256": record["claimSha256"], "verdict": record["verdict"],
        "evidenceClass": "formal-computation", "asOf": observed_at, "truthNotInferredFromAgreement": True,
        "method": {"positionTaken": False, "evidenceOnly": True, "independentWolframOriginAuthenticated": False},
        "sources": sources,
        "proofReceipts": [{
            "id": receipt_id, "proofRoute": "formal-computation",
            "receiptSha256": record["receiptSha256"], "integrityValid": True, "authenticated": True,
            "claimBound": True, "replayVerified": True, "decisive": True, "sourceIds": [source_space_id],
            "issuerKeyId": record["receiptIssuerKeyId"], "spaceRevision": record["spaceRevision"],
        }],
        "timeline": [{"id": "observatory-e2e-"+record["runId"], "at": observed_at, "title": "Signed Observatory run captured", "sourceIds": [source_space_id]}],
        "contradictionReview": {"completed": True},
        "sensitivityReview": {"completed": True, "secretsExcluded": True, "redactionsVerified": True},
        "verdictBasis": {"sourceIds": [source_space_id, source_wolfram_id], "proofReceiptIds": [receipt_id]},
        "evidenceNeeded": [],
        "contradictions": [] if record["verdict"] == "SUPPORTED" else [{"id": "claim-refutation", "at": observed_at, "sourceIds": [source_space_id, source_wolfram_id], "summary": "The supplied prime claim is refuted by deterministic replay and Wolfram."}],
    }
    gate = evaluate_evidence_case(payload)
    _require(gate["passed"] is True, "four_layer_case_gate_failed:" + ",".join(gate["blockers"]))
    passport = build_evidence_passport(payload, gate)
    return {
        "schemaVersion": "sovereign.evidence-case.v1", "caseId": record["runId"],
        "projectId": "sovereign-evidence-observatory-four-layer", "title": "Formal claim: " + record["claim"],
        "claim": record["claim"], "claimSha256": record["claimSha256"],
        "verdict": record["verdict"], "evidenceClass": "formal-computation",
        "workflowState": "PUBLISHABLE", "asOf": observed_at,
        "caseSha256": sha256_json({"payload": payload, "gate": gate, "passport": passport}),
        "sources": sources, "timeline": payload["timeline"], "contradictions": payload["contradictions"],
        "evidenceNeeded": [], "verdictBasis": payload["verdictBasis"],
        "proofReceipts": payload["proofReceipts"],
        "gateReport": gate, "evidencePassport": passport, "passportSha256": passport["passportSha256"],
        "method": payload["method"],
        "truthBoundary": {"generalTruth": False, "signedSpaceReceipt": True, "spaceRevisionCryptographicallySignedInReceipt": False, "wolframObservationCryptographicallyAuthenticated": False, "researchContextIsDecisive": False},
        # Retain the complete public-only run object so downstream researchers
        # can replay the bundle, original signature and exact trust anchor.
        "fourLayerRunRecord": record,
        "runBundleSha256": record["bundleSha256"],
    }


__all__ = ["FourLayerEvidenceError", "build_four_layer_run", "validate_four_layer_run", "build_four_layer_public_row",
           "SCHEMA_VERSION", "SPACE_ID", "DATASET_ID"]
