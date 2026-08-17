"""Deterministic contracts for the Sovereign Evidence Observatory.

This module contains no network or database access. It is the truth-boundary
between research candidates and publishable evidence objects.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

SCHEMA_VERSION = "sovereign.evidence-observatory.v1"
CASE_SCHEMA_VERSION = "sovereign.evidence-case.v1"
PASSPORT_SCHEMA_VERSION = "sovereign.evidence-passport.v2"
ARENA_SCHEMA_VERSION = "sovereign.evidence-arena-run.v1"

WORKFLOW_QUARANTINED = "QUARANTINED"
WORKFLOW_PUBLISHABLE = "PUBLISHABLE"
WORKFLOW_PUBLISHED = "PUBLISHED"

VERDICTS = {"SUPPORTED", "REFUTED", "UNPROVEN", "NOT_APPLICABLE"}
EVIDENCE_CLASSES = {
    "formal-computation", "structured-data", "source-provenance",
    "runtime-readback", "science-evidence", "human-review",
}
PROOF_ROUTES = {
    "formal-computation", "structured-data", "source-lineage",
    "runtime-readback", "science-evidence", "human-review",
}
SOURCE_TYPES = {
    "primary", "authoritative", "secondary", "runtime", "structured",
    "formal", "peer-reviewed", "human-review",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalized_claim(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def https_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def safe_json_value(value: Any) -> Any:
    """Bound imported research values and suppress obvious credential fields."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:20_000]
    if isinstance(value, list):
        return [safe_json_value(item) for item in value[:200]]
    if isinstance(value, dict):
        return {
            str(key)[:160]: safe_json_value(item)
            for key, item in list(value.items())[:200]
            if str(key).lower() not in {"token", "secret", "api_key", "apikey", "password"}
        }
    return str(value)[:20_000]


def _source_errors(source: Any) -> list[str]:
    if not isinstance(source, dict):
        return ["source_not_object"]
    errors: list[str] = []
    source_id = str(source.get("id") or "").strip()
    if not source_id:
        errors.append("source_id")
    if str(source.get("sourceType") or "") not in SOURCE_TYPES:
        errors.append("source_type")
    locator = str(source.get("locator") or "").strip()
    if not locator or not https_url(locator):
        errors.append("source_https_locator")
    digest = str(source.get("contentSha256") or "").lower()
    if not SHA256_RE.fullmatch(digest):
        errors.append("source_content_sha256")
    if iso_datetime(source.get("observedAt")) is None:
        errors.append("source_observed_at")
    provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
    if not str(provenance.get("originFamily") or "").strip():
        errors.append("source_origin_family")
    geo = source.get("geo")
    if geo is not None:
        if not isinstance(geo, dict):
            errors.append("source_geo_object")
        else:
            try:
                lat = float(geo.get("lat"))
                lon = float(geo.get("lon"))
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    errors.append("source_geo_range")
            except (TypeError, ValueError):
                errors.append("source_geo_coordinates")
            if str(geo.get("evidenceRole") or "") not in {"material", "context"}:
                errors.append("source_geo_evidence_role")
    return errors


def _receipt_errors(receipt: Any) -> list[str]:
    if not isinstance(receipt, dict):
        return ["receipt_not_object"]
    errors: list[str] = []
    if not str(receipt.get("id") or "").strip():
        errors.append("receipt_id")
    if str(receipt.get("proofRoute") or "") not in PROOF_ROUTES:
        errors.append("receipt_proof_route")
    if not SHA256_RE.fullmatch(str(receipt.get("receiptSha256") or "").lower()):
        errors.append("receipt_sha256")
    for key in ("integrityValid", "authenticated", "claimBound", "replayVerified"):
        if not isinstance(receipt.get(key), bool):
            errors.append(f"receipt_{key}_explicit")
    if receipt.get("integrityValid") is not True:
        errors.append("receipt_integrity_valid")
    if receipt.get("claimBound") is not True:
        errors.append("receipt_claim_bound")
    if receipt.get("replayVerified") is not True:
        errors.append("receipt_replay_verified")
    return errors


def evaluate_evidence_case(payload: Any) -> dict[str, Any]:
    """Return a deterministic fail-closed publication gate report.

    Publishability means that the *evidence state* is reproducible. It does not
    mean the claim is necessarily true: a rigorously demonstrated UNPROVEN state
    can pass the publication gate.
    """
    body = payload if isinstance(payload, dict) else {}
    blockers: list[str] = []
    claim = normalized_claim(body.get("claim"))
    if not claim:
        blockers.append("claim_required")
    claim_sha = sha256_text(claim) if claim else ""
    declared_claim_sha = str(body.get("claimSha256") or "").lower()
    if declared_claim_sha != claim_sha:
        blockers.append("claim_fingerprint_mismatch")

    verdict = str(body.get("verdict") or "").upper()
    if verdict not in VERDICTS:
        blockers.append("verdict_invalid")
    evidence_class = str(body.get("evidenceClass") or "")
    if evidence_class not in EVIDENCE_CLASSES:
        blockers.append("evidence_class_invalid")
    if iso_datetime(body.get("asOf")) is None:
        blockers.append("as_of_required")
    if body.get("truthNotInferredFromAgreement") is not True:
        blockers.append("agreement_truth_inference_forbidden")

    method = body.get("method") if isinstance(body.get("method"), dict) else {}
    if method.get("positionTaken") is not False:
        blockers.append("method_must_be_neutral")
    if method.get("evidenceOnly") is not True:
        blockers.append("method_evidence_only_required")

    sources = body.get("sources") if isinstance(body.get("sources"), list) else []
    if not sources:
        blockers.append("source_required")
    source_ids: set[str] = set()
    origin_families: set[str] = set()
    material_geo_count = 0
    for index, source in enumerate(sources):
        for error in _source_errors(source):
            blockers.append(f"source[{index}].{error}")
        if isinstance(source, dict):
            source_id = str(source.get("id") or "").strip()
            if source_id:
                if source_id in source_ids:
                    blockers.append(f"source[{index}].duplicate_id")
                source_ids.add(source_id)
            provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
            origin = str(provenance.get("originFamily") or "").strip()
            if origin:
                origin_families.add(origin)
            geo = source.get("geo") if isinstance(source.get("geo"), dict) else {}
            if geo.get("evidenceRole") == "material":
                material_geo_count += 1

    receipts = body.get("proofReceipts") if isinstance(body.get("proofReceipts"), list) else []
    if not receipts:
        blockers.append("proof_receipt_required")
    receipt_ids: set[str] = set()
    decisive_receipts: set[str] = set()
    authenticated_count = 0
    for index, receipt in enumerate(receipts):
        for error in _receipt_errors(receipt):
            blockers.append(f"proofReceipt[{index}].{error}")
        if isinstance(receipt, dict):
            receipt_id = str(receipt.get("id") or "").strip()
            if receipt_id:
                if receipt_id in receipt_ids:
                    blockers.append(f"proofReceipt[{index}].duplicate_id")
                receipt_ids.add(receipt_id)
            if receipt.get("decisive") is True:
                decisive_receipts.add(receipt_id)
            if receipt.get("authenticated") is True:
                authenticated_count += 1

    timeline = body.get("timeline") if isinstance(body.get("timeline"), list) else []
    for index, event in enumerate(timeline):
        if not isinstance(event, dict):
            blockers.append(f"timeline[{index}].not_object")
            continue
        if iso_datetime(event.get("at")) is None:
            blockers.append(f"timeline[{index}].timestamp")
        bound_sources = [str(item) for item in (event.get("sourceIds") or [])]
        if not bound_sources or any(item not in source_ids for item in bound_sources):
            blockers.append(f"timeline[{index}].source_binding")

    contradictions = body.get("contradictionReview") if isinstance(body.get("contradictionReview"), dict) else {}
    if contradictions.get("completed") is not True and contradictions.get("notApplicable") is not True:
        blockers.append("contradiction_review_required")

    sensitivity = body.get("sensitivityReview") if isinstance(body.get("sensitivityReview"), dict) else {}
    if sensitivity.get("completed") is not True:
        blockers.append("sensitivity_review_required")
    if sensitivity.get("secretsExcluded") is not True:
        blockers.append("secrets_excluded_required")
    if sensitivity.get("redactionsVerified") is not True:
        blockers.append("redactions_verified_required")

    basis = body.get("verdictBasis") if isinstance(body.get("verdictBasis"), dict) else {}
    basis_sources = {str(item) for item in (basis.get("sourceIds") or [])}
    basis_receipts = {str(item) for item in (basis.get("proofReceiptIds") or [])}
    if not basis_sources or not basis_sources.issubset(source_ids):
        blockers.append("verdict_basis_source_binding")
    if not basis_receipts or not basis_receipts.issubset(receipt_ids):
        blockers.append("verdict_basis_receipt_binding")
    if verdict in {"SUPPORTED", "REFUTED"} and not (basis_receipts & decisive_receipts):
        blockers.append("decisive_receipt_required")
    evidence_needed = [str(item).strip() for item in (body.get("evidenceNeeded") or []) if str(item).strip()]
    if verdict == "UNPROVEN" and not evidence_needed:
        blockers.append("unproven_evidence_needed_required")

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "passed": not blockers,
        "blockers": sorted(set(blockers)),
        "claimSha256": claim_sha,
        "verdict": verdict,
        "sourceCount": len(sources),
        "independentOriginCount": len(origin_families),
        "proofReceiptCount": len(receipts),
        "authenticatedReceiptCount": authenticated_count,
        "materialGeoEvidenceCount": material_geo_count,
        "truthNotInferredFromAgreement": body.get("truthNotInferredFromAgreement") is True,
    }
    report["gateSha256"] = sha256_json(report)
    return report


def build_evidence_passport(payload: dict[str, Any], gate_report: dict[str, Any]) -> dict[str, Any]:
    receipts = payload.get("proofReceipts") if isinstance(payload.get("proofReceipts"), list) else []
    integrity = bool(receipts) and all(item.get("integrityValid") is True for item in receipts if isinstance(item, dict))
    authenticated = bool(receipts) and all(item.get("authenticated") is True for item in receipts if isinstance(item, dict))
    claim_bound = bool(receipts) and all(item.get("claimBound") is True for item in receipts if isinstance(item, dict))
    replay = bool(receipts) and all(item.get("replayVerified") is True for item in receipts if isinstance(item, dict))
    passport = {
        "schemaVersion": PASSPORT_SCHEMA_VERSION,
        "proofReceiptValid": bool(gate_report.get("passed")),
        "proofReceiptIntegrityValid": integrity,
        "proofReceiptAuthenticated": authenticated,
        "proofReceiptClaimBound": claim_bound,
        "proofReceiptReplayVerified": replay,
        "receiptTrust": "mixed" if integrity and not authenticated else "authenticated" if authenticated else "unverified",
        "verdict": str(payload.get("verdict") or "").upper(),
        "truthNotInferredFromAgreement": True,
        "claimSha256": gate_report.get("claimSha256"),
        "gateSha256": gate_report.get("gateSha256"),
        "implementationVersion": SCHEMA_VERSION,
    }
    passport["passportSha256"] = sha256_json(passport)
    return passport


def public_case_projection(row: dict[str, Any], *, as_of: datetime | None = None) -> dict[str, Any]:
    payload = dict(row.get("case_payload") or {})
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    timeline = payload.get("timeline") if isinstance(payload.get("timeline"), list) else []
    if as_of is not None:
        sources = [item for item in sources if iso_datetime((item or {}).get("observedAt")) and iso_datetime((item or {}).get("observedAt")) <= as_of]
        visible_ids = {str(item.get("id")) for item in sources if isinstance(item, dict)}
        timeline = [
            item for item in timeline
            if iso_datetime((item or {}).get("at")) and iso_datetime((item or {}).get("at")) <= as_of
            and any(str(source_id) in visible_ids for source_id in ((item or {}).get("sourceIds") or []))
        ]
    material_geo = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        geo = source.get("geo") if isinstance(source.get("geo"), dict) else {}
        if geo.get("evidenceRole") == "material":
            material_geo.append({"sourceId": source.get("id"), "label": source.get("label"), "lat": geo.get("lat"), "lon": geo.get("lon")})
    lineage = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
        origin = str(provenance.get("originFamily") or "unknown")
        lineage.setdefault(origin, []).append(str(source.get("id") or ""))
    return {
        "schemaVersion": CASE_SCHEMA_VERSION,
        "caseId": str(row.get("id") or ""),
        "projectId": row.get("project_id"),
        "title": row.get("title"),
        "claim": row.get("claim"),
        "claimSha256": row.get("claim_sha256"),
        "verdict": row.get("verdict"),
        "evidenceClass": row.get("evidence_class"),
        "workflowState": row.get("workflow_state"),
        "asOf": row.get("as_of").isoformat() if getattr(row.get("as_of"), "isoformat", None) else row.get("as_of"),
        "caseSha256": row.get("case_sha256"),
        "sources": sources,
        "timeline": timeline,
        "contradictions": payload.get("contradictions") or [],
        "evidenceNeeded": payload.get("evidenceNeeded") or [],
        "verdictBasis": payload.get("verdictBasis") or {},
        "sourceLineage": lineage,
        "materialGeoEvidence": material_geo,
        "claimGenealogy": payload.get("claimGenealogy") or [],
        "informationFlow": payload.get("informationFlow") or [],
        "gateReport": row.get("gate_report") or {},
        "evidencePassport": row.get("passport") or {},
        "passportSha256": row.get("passport_sha256"),
    }


def source_dependency_analysis(case: dict[str, Any], source_id: str) -> dict[str, Any]:
    """Simulate removal of one source without recomputing or inventing truth."""
    payload = dict(case.get("case_payload") or case)
    sources = [item for item in (payload.get("sources") or []) if isinstance(item, dict)]
    source_by_id = {str(item.get("id") or ""): item for item in sources if item.get("id")}
    if source_id not in source_by_id:
        raise ValueError("source_not_found")
    removed = source_by_id[source_id]
    remaining = [item for item in sources if str(item.get("id") or "") != source_id]
    remaining_origins = {
        str((item.get("provenance") or {}).get("originFamily") or "")
        for item in remaining
        if isinstance(item.get("provenance"), dict)
        and str((item.get("provenance") or {}).get("originFamily") or "")
    }
    basis = payload.get("verdictBasis") if isinstance(payload.get("verdictBasis"), dict) else {}
    basis_sources = {str(item) for item in (basis.get("sourceIds") or [])}
    basis_receipts = {str(item) for item in (basis.get("proofReceiptIds") or [])}
    dependent_receipts = {
        str(receipt.get("id") or "")
        for receipt in (payload.get("proofReceipts") or [])
        if isinstance(receipt, dict)
        and source_id in {str(item) for item in (receipt.get("sourceIds") or [])}
    }
    timeline_events_lost = sum(
        1 for event in (payload.get("timeline") or [])
        if isinstance(event, dict)
        and source_id in {str(item) for item in (event.get("sourceIds") or [])}
    )
    origin = ""
    if isinstance(removed.get("provenance"), dict):
        origin = str((removed.get("provenance") or {}).get("originFamily") or "")
    result = {
        "schemaVersion": "sovereign.evidence-source-dependency.v1",
        "sourceId": source_id,
        "sourceSha256": str(removed.get("contentSha256") or ""),
        "removedOriginFamily": origin or None,
        "originStillRepresented": bool(origin) and origin in remaining_origins,
        "remainingSourceCount": len(remaining),
        "remainingIndependentOriginCount": len(remaining_origins),
        "verdictBasisSourceRemoved": source_id in basis_sources,
        "dependentProofReceiptIds": sorted(item for item in dependent_receipts if item),
        "verdictBasisReceiptDependencyBroken": bool(dependent_receipts & basis_receipts),
        "timelineEventsAffected": timeline_events_lost,
        "simulationOnly": True,
        "verdictRecomputed": False,
        "truthNotice": "Removing a source measures dependency only; it does not produce a new truth verdict.",
    }
    result["analysisSha256"] = sha256_json(result)
    return result


def score_arena_response(case: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(case.get("case_payload") or {})
    source_ids = {str(source.get("id")) for source in (payload.get("sources") or []) if isinstance(source, dict) and source.get("id")}
    basis = payload.get("verdictBasis") if isinstance(payload.get("verdictBasis"), dict) else {}
    decisive_source_ids = {str(item) for item in (basis.get("sourceIds") or [])}
    expected_verdict = str(case.get("verdict") or "")
    actual_verdict = str(response_payload.get("verdict") or "").strip().upper()
    citations = [str(item) for item in (response_payload.get("citations") or [])]
    unknown_citations = [item for item in citations if item not in source_ids]
    claims = response_payload.get("claims") if isinstance(response_payload.get("claims"), list) else []
    supported_claims = 0
    unsupported_claims = 0
    for claim in claims:
        refs = {str(item) for item in ((claim or {}).get("sourceIds") or [])} if isinstance(claim, dict) else set()
        if refs and refs.issubset(source_ids):
            supported_claims += 1
        else:
            unsupported_claims += 1
    claim_total = supported_claims + unsupported_claims
    expected_contradictions = {str(item.get("id")) for item in (payload.get("contradictions") or []) if isinstance(item, dict) and item.get("id")}
    returned_contradictions = {str(item) for item in (response_payload.get("contradictionIds") or [])}
    citation_precision = ((len(citations) - len(unknown_citations)) / len(citations)) if citations else 0.0
    basis_coverage = (len(set(citations) & decisive_source_ids) / len(decisive_source_ids)) if decisive_source_ids else 1.0
    unsupported_rate = unsupported_claims / claim_total if claim_total else 0.0
    contradiction_recall = (len(returned_contradictions & expected_contradictions) / len(expected_contradictions)) if expected_contradictions else 1.0
    verdict_correct = actual_verdict == expected_verdict
    abstention_correct = (expected_verdict != "UNPROVEN") or (actual_verdict == "UNPROVEN")
    evidence_adherence = max(0.0, 1.0 - unsupported_rate) * citation_precision if citations else (1.0 if not claims else 0.0)
    overall = (
        (1.0 if verdict_correct else 0.0) * 0.25
        + (1.0 if abstention_correct else 0.0) * 0.20
        + evidence_adherence * 0.20
        + citation_precision * 0.10
        + basis_coverage * 0.10
        + (1.0 - unsupported_rate) * 0.10
        + contradiction_recall * 0.05
    )
    return {
        "schemaVersion": ARENA_SCHEMA_VERSION,
        "verdictCorrect": verdict_correct,
        "abstentionCorrect": abstention_correct,
        "evidenceAdherence": round(evidence_adherence, 6),
        "citationPrecision": round(citation_precision, 6),
        "decisiveBasisCoverage": round(basis_coverage, 6),
        "unsupportedClaimRate": round(unsupported_rate, 6),
        "unsupportedClaimMetricNotice": "Deterministic evidence-bound proxy; not a general hallucination detector.",
        "contradictionRecall": round(contradiction_recall, 6),
        "overallScore": round(overall, 6),
        "truthfulnessRanked": False,
    }
