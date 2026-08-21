"""Secret-free partner analysis ledger for Wolfram CAG.

The ledger records reproducible technical evidence requested for the Wolfram
partner handoff. It never stores raw provider bodies, prompts, Authorization
headers or chain-of-thought. ``created_at`` is metadata only and is excluded
from causal identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "sovereign.wolfram-cag-partner-analysis.v1"
CONTRACT_VERSION = "wolfram-cag-v1-2026-08-21"
VERDICTS = frozenset({"SUPPORTED", "CONTRADICTED", "INCONCLUSIVE", "UNAVAILABLE"})
DOCUMENTATION_CLASSES = frozenset({
    "PRIVATE_PROVIDER_EVIDENCE",
    "PARTNER_REPORTABLE",
    "PUBLIC_DERIVED_RECEIPT",
    "HF_PUBLISHED_VERIFIED",
})
_COMPONENTS = frozenset({
    "WolframLanguageHints",
    "WolframLanguageComputation",
    "WolframAlphaResults",
    "WolframAlphaContext",
})
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_SECRET = re.compile(
    r"(?:Authorization\s*:\s*\S+|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S{4,}|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]+ KEY-----)",
    re.IGNORECASE,
)


class PartnerAnalysisError(ValueError):
    pass


def _clean_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())[:limit]
    if _SECRET.search(text):
        raise PartnerAnalysisError("secret-shaped material is forbidden in partner analysis records")
    return text


def _clean_optional_id(value: Any) -> str | None:
    text = _clean_text(value, limit=160)
    if not text:
        return None
    if not _PROVIDER_ID.fullmatch(text):
        raise PartnerAnalysisError("provider identity has an invalid shape")
    return text


def _sha(value: Any, *, required: bool = False) -> str | None:
    text = _clean_text(value, limit=80).casefold()
    if not text:
        if required:
            raise PartnerAnalysisError("required SHA-256 is missing")
        return None
    if not _HEX64.fullmatch(text):
        raise PartnerAnalysisError("expected a lowercase SHA-256")
    return text


def _revision(value: Any) -> str | None:
    text = _clean_text(value, limit=80).casefold()
    if not text:
        return None
    if not _HEX40.fullmatch(text):
        raise PartnerAnalysisError("revision must be an exact 40-character Git SHA")
    return text


def _clean_list(values: Sequence[Any] | None, *, limit: int = 32) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        raise PartnerAnalysisError("analysis list fields must be arrays")
    result = sorted({_clean_text(value, limit=600) for value in values if _clean_text(value, limit=600)})
    return result[:limit]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def build_partner_analysis_record(
    *,
    component: str,
    normalized_question: str,
    normalized_input_sha256: str,
    provider_response_sha256: str | None,
    credential_fingerprint_sha256: str | None,
    verdict: str,
    derived_conclusion: str,
    repository_revision: str | None = None,
    runtime_revision: str | None = None,
    provider_request_id: str | None = None,
    provider_response_uuid: str | None = None,
    documentation_class: str = "PARTNER_REPORTABLE",
    assumptions: Sequence[str] | None = None,
    limitations: Sequence[str] | None = None,
    source_refs: Sequence[str] | None = None,
    evidence_passport_hash: str | None = None,
    hf_publication_ref: str | None = None,
    hf_target_revision: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    selected_component = _clean_text(component, limit=120)
    if selected_component not in _COMPONENTS:
        raise PartnerAnalysisError("unknown CAG component")
    selected_verdict = _clean_text(verdict, limit=40).upper()
    if selected_verdict not in VERDICTS:
        raise PartnerAnalysisError("invalid CAG verdict")
    selected_class = _clean_text(documentation_class, limit=64).upper()
    if selected_class not in DOCUMENTATION_CLASSES:
        raise PartnerAnalysisError("invalid documentation class")
    question = _clean_text(normalized_question, limit=8_192)
    conclusion = _clean_text(derived_conclusion, limit=8_192)
    if not question or not conclusion:
        raise PartnerAnalysisError("normalized question and derived conclusion are required")
    if selected_verdict in {"SUPPORTED", "CONTRADICTED"} and not provider_response_sha256:
        raise PartnerAnalysisError("positive/negative semantic verdict requires provider evidence")
    if selected_class == "HF_PUBLISHED_VERIFIED" and (not hf_publication_ref or not hf_target_revision):
        raise PartnerAnalysisError("HF_PUBLISHED_VERIFIED requires publication and target readback")

    causal = {
        "schemaVersion": SCHEMA_VERSION,
        "cagComponent": selected_component,
        "cagContractVersion": CONTRACT_VERSION,
        "repositoryRevision": _revision(repository_revision),
        "runtimeRevision": _revision(runtime_revision),
        "normalizedQuestion": question,
        "normalizedInputSha256": _sha(normalized_input_sha256, required=True),
        "providerRequestId": _clean_optional_id(provider_request_id),
        "providerResponseUuid": _clean_optional_id(provider_response_uuid),
        "providerResponseSha256": _sha(provider_response_sha256),
        "credentialFingerprintSha256": _sha(credential_fingerprint_sha256),
        "verdict": selected_verdict,
        "derivedConclusion": conclusion,
        "documentationClass": selected_class,
        "assumptions": _clean_list(assumptions),
        "limitations": _clean_list(limitations),
        "sourceRefs": _clean_list(source_refs, limit=64),
        "evidencePassportHash": _sha(evidence_passport_hash),
        "hfPublicationRef": _clean_text(hf_publication_ref, limit=500) or None,
        "hfTargetRevision": _clean_text(hf_target_revision, limit=200) or None,
    }
    record_sha256 = hashlib.sha256(_canonical_json(causal).encode("utf-8")).hexdigest()
    return {
        **causal,
        "analysisId": f"cag-analysis-{record_sha256[:24]}",
        "analysisRecordSha256": record_sha256,
        "createdAt": _clean_text(created_at, limit=80) or None,
    }


def public_partner_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return fields safe for partner handoff; credential fingerprints stay private."""
    return {
        key: value
        for key, value in dict(record).items()
        if key not in {"credentialFingerprintSha256"}
    }


def persist_partner_analysis(connection: Any, record: Mapping[str, Any]) -> str:
    """Idempotently persist one already-normalized analysis record."""
    required = {
        "analysisId", "analysisRecordSha256", "schemaVersion", "cagComponent",
        "cagContractVersion", "normalizedQuestion", "normalizedInputSha256",
        "verdict", "derivedConclusion", "documentationClass",
    }
    if not required.issubset(record):
        raise PartnerAnalysisError("analysis record is incomplete")
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO wolfram_cag_analysis_records (
                analysis_id, schema_version, record_sha256, repository_revision,
                runtime_revision, cag_component, cag_contract_version,
                normalized_question, normalized_input_sha256, provider_request_id,
                provider_response_uuid, provider_response_sha256,
                credential_fingerprint_sha256, verdict, documentation_class,
                derived_conclusion, assumptions, limitations, source_refs,
                evidence_passport_hash, hf_publication_ref, hf_target_revision
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s
            )
            ON CONFLICT (record_sha256) DO NOTHING
            """,
            (
                record["analysisId"], record["schemaVersion"], record["analysisRecordSha256"],
                record.get("repositoryRevision"), record.get("runtimeRevision"), record["cagComponent"],
                record["cagContractVersion"], record["normalizedQuestion"], record["normalizedInputSha256"],
                record.get("providerRequestId"), record.get("providerResponseUuid"),
                record.get("providerResponseSha256"), record.get("credentialFingerprintSha256"),
                record["verdict"], record["documentationClass"], record["derivedConclusion"],
                _canonical_json(record.get("assumptions") or []),
                _canonical_json(record.get("limitations") or []),
                _canonical_json(record.get("sourceRefs") or []),
                record.get("evidencePassportHash"), record.get("hfPublicationRef"),
                record.get("hfTargetRevision"),
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return str(record["analysisId"])


__all__ = [
    "SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "VERDICTS",
    "DOCUMENTATION_CLASSES",
    "PartnerAnalysisError",
    "build_partner_analysis_record",
    "public_partner_projection",
    "persist_partner_analysis",
]
