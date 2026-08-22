"""Secret-free partner analysis ledger for Wolfram CAG.

The ledger records reproducible technical evidence requested for the Wolfram
partner handoff. It never stores raw provider bodies, prompts, Authorization
headers or chain-of-thought. ``created_at`` is metadata only and is excluded
from causal identity.

The module also produces the deterministic Wolfram partner handoff pack: a
bounded, secret-free projection of the canonical analysis records. A record
can never promote itself to a more public documentation class; promotion to
``HF_PUBLISHED_VERIFIED`` requires an explicit ``attach_hf_publication`` call
carrying a real target readback. Rendering a human-readable artifact is a
display concern only and never constitutes verification.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "sovereign.wolfram-cag-partner-analysis.v1"
PACK_SCHEMA_VERSION = "sovereign.wolfram-cag-partner-handoff.v1"
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
_METADATA_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
_FAILURE_FAMILY = re.compile(r"^[A-Z0-9_]{1,80}$")
_SECRET = re.compile(
    r"(?:Authorization\s*:\s*\S+|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S{4,}|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]+ KEY-----)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_RAW_PROMPT = re.compile(
    r"(?:chain[- ]of[- ]thought|<\|?(?:im_start|im_end|endoftext)\|?>)",
    re.IGNORECASE,
)
_FORBIDDEN_KEY_MARKERS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "cookie",
    "credential",
    "raw_prompt",
    "prompt_text",
    "chain_of_thought",
)


class PartnerAnalysisError(ValueError):
    pass


def _guard_text(text: str) -> str:
    if _SECRET.search(text) or _EMAIL.search(text) or _RAW_PROMPT.search(text):
        raise PartnerAnalysisError("secret-shaped material is forbidden in partner analysis records")
    return text


def _clean_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())[:limit]
    return _guard_text(text)


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


def _failure_family(value: Any) -> str | None:
    text = _clean_text(value, limit=80).upper()
    if not text:
        return None
    if not _FAILURE_FAMILY.fullmatch(text):
        raise PartnerAnalysisError("failure family has an invalid shape")
    return text


def _clean_list(values: Sequence[Any] | None, *, limit: int = 32) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        raise PartnerAnalysisError("analysis list fields must be arrays")
    result = sorted({_clean_text(value, limit=600) for value in values if _clean_text(value, limit=600)})
    return result[:limit]


def _clean_metadata_map(value: Any, *, label: str) -> dict[str, str]:
    """Bounded flat string map for quota/rate-limit observations."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise PartnerAnalysisError(f"{label} must be an object of scalar observations")
    if len(value) > 16:
        raise PartnerAnalysisError(f"{label} is limited to 16 observations")
    result: dict[str, str] = {}
    for key, item in value.items():
        clean_key = _clean_text(key, limit=80)
        if not clean_key or not _METADATA_KEY.fullmatch(clean_key):
            raise PartnerAnalysisError(f"{label} observation key has an invalid shape")
        if isinstance(item, (Mapping, list, tuple, set)):
            raise PartnerAnalysisError(f"{label} observations must be scalar")
        if isinstance(item, bool):
            result[clean_key] = "true" if item else "false"
        elif item is None:
            continue
        elif isinstance(item, (int, float)):
            result[clean_key] = repr(item)
        else:
            cleaned = _clean_text(item, limit=400)
            if cleaned:
                result[clean_key] = cleaned
    return dict(sorted(result.items()))


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
    sovereign_run_id: str | None = None,
    toolchain_step_id: str | None = None,
    provider_request_id: str | None = None,
    provider_response_uuid: str | None = None,
    documentation_class: str = "PARTNER_REPORTABLE",
    failure_family: str | None = None,
    quota_metadata: Mapping[str, Any] | None = None,
    rate_limit_metadata: Mapping[str, Any] | None = None,
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
        "sovereignRunId": _clean_optional_id(sovereign_run_id),
        "toolchainStepId": _clean_optional_id(toolchain_step_id),
        "normalizedQuestion": question,
        "normalizedInputSha256": _sha(normalized_input_sha256, required=True),
        "providerRequestId": _clean_optional_id(provider_request_id),
        "providerResponseUuid": _clean_optional_id(provider_response_uuid),
        "providerResponseSha256": _sha(provider_response_sha256),
        "credentialFingerprintSha256": _sha(credential_fingerprint_sha256),
        "verdict": selected_verdict,
        "derivedConclusion": conclusion,
        "documentationClass": selected_class,
        "failureFamily": _failure_family(failure_family),
        "quotaMetadata": _clean_metadata_map(quota_metadata, label="quota_metadata"),
        "rateLimitMetadata": _clean_metadata_map(rate_limit_metadata, label="rate_limit_metadata"),
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


def assert_partner_safe(value: Any, *, path: str = "$") -> None:
    """Redaction gate: hard-reject secret/PII/raw-prompt material in a projection.

    Walks the complete outgoing structure. Forbidden key markers (credentials,
    tokens, raw prompts, chain-of-thought) and secret-shaped values (Authorization
    headers, bearer tokens, API keys, PEM blocks, emails, prompt markers) abort
    the partner/public projection instead of leaking downstream.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.casefold()
            for marker in _FORBIDDEN_KEY_MARKERS:
                if marker in lowered:
                    raise PartnerAnalysisError(
                        f"forbidden key marker {marker!r} at {path}.{key_text}"
                    )
            assert_partner_safe(item, path=f"{path}.{key_text}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_partner_safe(item, path=f"{path}[{index}]")
    elif isinstance(value, str):
        _guard_text(value)


def _require_record(record: Mapping[str, Any]) -> None:
    required = {
        "analysisId", "analysisRecordSha256", "schemaVersion", "cagComponent",
        "cagContractVersion", "normalizedQuestion", "normalizedInputSha256",
        "verdict", "derivedConclusion", "documentationClass",
    }
    if not isinstance(record, Mapping) or not required.issubset(record):
        raise PartnerAnalysisError("analysis record is incomplete")


def build_partner_handoff_pack(
    records: Sequence[Mapping[str, Any]],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic Wolfram partner handoff pack.

    The same canonical record set always yields the same ``packSha256``,
    independent of input ordering and of ``createdAt``/``generated_at``
    metadata. Only public partner projections enter the pack; the redaction
    gate runs over the complete pack body before it is returned.
    """
    projections: list[dict[str, Any]] = []
    for record in records:
        _require_record(record)
        projections.append(public_partner_projection(record))
    projections.sort(key=lambda item: (str(item["analysisRecordSha256"]), str(item["analysisId"])))

    verdict_counts: dict[str, int] = {}
    for projection in projections:
        verdict = str(projection["verdict"])
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    unresolved = sorted({
        limitation
        for projection in projections
        if projection["verdict"] in {"INCONCLUSIVE", "UNAVAILABLE"}
        for limitation in projection.get("limitations") or []
    })
    observations = [
        {
            "analysisRecordSha256": projection["analysisRecordSha256"],
            "quotaMetadata": dict(projection.get("quotaMetadata") or {}),
            "rateLimitMetadata": dict(projection.get("rateLimitMetadata") or {}),
        }
        for projection in projections
        if projection.get("quotaMetadata") or projection.get("rateLimitMetadata")
    ]
    hf_publications = [
        {
            "analysisRecordSha256": projection["analysisRecordSha256"],
            "hfPublicationRef": projection["hfPublicationRef"],
            "hfTargetRevision": projection["hfTargetRevision"],
        }
        for projection in projections
        if projection["documentationClass"] == "HF_PUBLISHED_VERIFIED"
    ]

    body: dict[str, Any] = {
        "schemaVersion": PACK_SCHEMA_VERSION,
        "cagContractVersion": CONTRACT_VERSION,
        "recordCount": len(projections),
        "summary": {
            "verdictCounts": verdict_counts,
            "components": sorted({str(p["cagComponent"]) for p in projections}),
            "documentationClasses": sorted({str(p["documentationClass"]) for p in projections}),
            "failureFamilies": sorted({
                str(p["failureFamily"]) for p in projections if p.get("failureFamily")
            }),
        },
        "analyses": projections,
        "quotaObservations": observations,
        "limits": sorted({
            limitation
            for projection in projections
            for limitation in projection.get("limitations") or []
        }),
        "unresolvedQuestions": unresolved,
        "evidencePassportRefs": sorted({
            str(p["evidencePassportHash"]) for p in projections if p.get("evidencePassportHash")
        }),
        "hfPublications": hf_publications,
        "truthNotice": (
            "This handoff pack is a deterministic projection of canonical CAG analysis "
            "records. Rendering or exporting it is a display concern and never "
            "constitutes verification."
        ),
    }
    hashable = {
        **body,
        "analyses": [
            {key: value for key, value in projection.items() if key != "createdAt"}
            for projection in projections
        ],
    }
    pack_sha256 = hashlib.sha256(_canonical_json(hashable).encode("utf-8")).hexdigest()
    pack = {**body, "packSha256": pack_sha256, "generatedAt": _clean_text(generated_at, limit=80) or None}
    assert_partner_safe(pack)
    return pack


def render_partner_handoff_markdown(pack: Mapping[str, Any]) -> str:
    """Render a deterministic human-readable artifact from a handoff pack.

    Render success is not verification; the artifact is a bounded display of
    the pack projection for review by the Wolfram contact.
    """
    if not isinstance(pack, Mapping) or pack.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise PartnerAnalysisError("a handoff pack built by build_partner_handoff_pack is required")
    analyses = list(pack.get("analyses") or [])
    lines = [
        "# Wolfram CAG Partner Handoff Pack",
        "",
        f"- Pack schema: `{pack['schemaVersion']}`",
        f"- CAG contract: `{pack['cagContractVersion']}`",
        f"- Pack SHA-256: `{pack['packSha256']}`",
        f"- Analyses: {pack['recordCount']}",
        "",
        "## Summary",
        "",
    ]
    summary = pack.get("summary") or {}
    verdict_counts = summary.get("verdictCounts") or {}
    if verdict_counts:
        for verdict in sorted(verdict_counts):
            lines.append(f"- {verdict}: {verdict_counts[verdict]}")
    else:
        lines.append("- No verdicts recorded.")
    lines.append("")
    lines.append("Components exercised:")
    for component in summary.get("components") or []:
        lines.append(f"- `{component}`")
    if summary.get("failureFamilies"):
        lines.append("")
        lines.append("Failure families observed:")
        for family in summary["failureFamilies"]:
            lines.append(f"- `{family}`")
    lines.append("")
    lines.append("## Analyses")
    for projection in analyses:
        lines.extend([
            "",
            f"### {projection['analysisId']}",
            "",
            f"- Component: `{projection['cagComponent']}`",
            f"- Verdict: **{projection['verdict']}**",
            f"- Documentation class: `{projection['documentationClass']}`",
            f"- Record SHA-256: `{projection['analysisRecordSha256']}`",
            f"- Normalized question: {projection['normalizedQuestion']}",
            f"- Derived conclusion: {projection['derivedConclusion']}",
        ])
        if projection.get("providerResponseSha256"):
            lines.append(f"- Provider response SHA-256: `{projection['providerResponseSha256']}`")
        if projection.get("evidencePassportHash"):
            lines.append(f"- Evidence passport hash: `{projection['evidencePassportHash']}`")
        if projection.get("hfPublicationRef"):
            lines.append(
                f"- HF publication: `{projection['hfPublicationRef']}` "
                f"at target revision `{projection['hfTargetRevision']}`"
            )
        for label, key in (("Assumptions", "assumptions"), ("Limitations", "limitations"), ("Source refs", "sourceRefs")):
            entries = projection.get(key) or []
            if entries:
                lines.append(f"- {label}:")
                for entry in entries:
                    lines.append(f"  - {entry}")
    observations = pack.get("quotaObservations") or []
    if observations:
        lines.extend(["", "## Quota and rate-limit observations", ""])
        for observation in observations:
            merged = {**(observation.get("quotaMetadata") or {}), **(observation.get("rateLimitMetadata") or {})}
            rendered = ", ".join(f"{key}={value}" for key, value in sorted(merged.items()))
            lines.append(f"- `{observation['analysisRecordSha256']}`: {rendered}")
    if pack.get("unresolvedQuestions"):
        lines.extend(["", "## Limits and unresolved questions", ""])
        for question in pack["unresolvedQuestions"]:
            lines.append(f"- {question}")
    lines.extend(["", "---", "", str(pack.get("truthNotice") or ""), ""])
    rendered = "\n".join(lines)
    assert_partner_safe(rendered)
    return rendered


def attach_hf_publication(
    record: Mapping[str, Any],
    *,
    hf_publication_ref: str,
    hf_target_revision: str,
) -> dict[str, Any]:
    """Re-derive a record as ``HF_PUBLISHED_VERIFIED`` after target readback.

    A record never promotes itself; this explicit re-derivation requires the
    publication reference and the exact target revision read back from the
    publication target, and produces a new record with a new causal identity.
    """
    _require_record(record)
    ref = _clean_text(hf_publication_ref, limit=500)
    target = _clean_text(hf_target_revision, limit=200)
    if not ref or not target:
        raise PartnerAnalysisError("HF publication requires publication ref and target readback")
    return build_partner_analysis_record(
        component=str(record["cagComponent"]),
        normalized_question=str(record["normalizedQuestion"]),
        normalized_input_sha256=str(record["normalizedInputSha256"]),
        provider_response_sha256=record.get("providerResponseSha256"),
        credential_fingerprint_sha256=record.get("credentialFingerprintSha256"),
        verdict=str(record["verdict"]),
        derived_conclusion=str(record["derivedConclusion"]),
        repository_revision=record.get("repositoryRevision"),
        runtime_revision=record.get("runtimeRevision"),
        sovereign_run_id=record.get("sovereignRunId"),
        toolchain_step_id=record.get("toolchainStepId"),
        provider_request_id=record.get("providerRequestId"),
        provider_response_uuid=record.get("providerResponseUuid"),
        documentation_class="HF_PUBLISHED_VERIFIED",
        failure_family=record.get("failureFamily"),
        quota_metadata=record.get("quotaMetadata") or None,
        rate_limit_metadata=record.get("rateLimitMetadata") or None,
        assumptions=record.get("assumptions") or None,
        limitations=record.get("limitations") or None,
        source_refs=record.get("sourceRefs") or None,
        evidence_passport_hash=record.get("evidencePassportHash"),
        hf_publication_ref=ref,
        hf_target_revision=target,
        created_at=record.get("createdAt"),
    )


def evidence_passport_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    """Hash-only reference for an Evidence Passport; truth ownership stays here."""
    _require_record(record)
    return {
        "analysisId": str(record["analysisId"]),
        "analysisRecordSha256": str(record["analysisRecordSha256"]),
        "schemaVersion": str(record["schemaVersion"]),
        "verdict": str(record["verdict"]),
        "truthNotice": (
            "Hash reference only; truth ownership remains with the canonical "
            "Wolfram CAG partner analysis ledger."
        ),
    }


def persist_partner_analysis(connection: Any, record: Mapping[str, Any]) -> str:
    """Idempotently persist one already-normalized analysis record."""
    _require_record(record)
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO wolfram_cag_analysis_records (
                analysis_id, schema_version, record_sha256, repository_revision,
                runtime_revision, sovereign_run_id, toolchain_step_id,
                cag_component, cag_contract_version,
                normalized_question, normalized_input_sha256, provider_request_id,
                provider_response_uuid, provider_response_sha256,
                credential_fingerprint_sha256, verdict, documentation_class,
                derived_conclusion, failure_family, quota_metadata, rate_limit_metadata,
                assumptions, limitations, source_refs,
                evidence_passport_hash, hf_publication_ref, hf_target_revision
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s
            )
            ON CONFLICT (record_sha256) DO NOTHING
            """,
            (
                record["analysisId"], record["schemaVersion"], record["analysisRecordSha256"],
                record.get("repositoryRevision"), record.get("runtimeRevision"),
                record.get("sovereignRunId"), record.get("toolchainStepId"),
                record["cagComponent"], record["cagContractVersion"],
                record["normalizedQuestion"], record["normalizedInputSha256"],
                record.get("providerRequestId"), record.get("providerResponseUuid"),
                record.get("providerResponseSha256"), record.get("credentialFingerprintSha256"),
                record["verdict"], record["documentationClass"], record["derivedConclusion"],
                record.get("failureFamily"),
                _canonical_json(record.get("quotaMetadata") or {}),
                _canonical_json(record.get("rateLimitMetadata") or {}),
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


def _json_column(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def load_partner_analyses(connection: Any) -> list[dict[str, Any]]:
    """Load persisted records ordered by record hash for deterministic reporting."""
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT analysis_id, schema_version, record_sha256, repository_revision,
                   runtime_revision, sovereign_run_id, toolchain_step_id,
                   cag_component, cag_contract_version,
                   normalized_question, normalized_input_sha256, provider_request_id,
                   provider_response_uuid, provider_response_sha256,
                   credential_fingerprint_sha256, verdict, documentation_class,
                   derived_conclusion, failure_family, quota_metadata, rate_limit_metadata,
                   assumptions, limitations, source_refs,
                   evidence_passport_hash, hf_publication_ref, hf_target_revision,
                   created_at
            FROM wolfram_cag_analysis_records
            ORDER BY record_sha256 ASC
            """
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    records: list[dict[str, Any]] = []
    for row in rows:
        created = row[27]
        records.append({
            "analysisId": row[0],
            "schemaVersion": row[1],
            "analysisRecordSha256": row[2],
            "repositoryRevision": row[3],
            "runtimeRevision": row[4],
            "sovereignRunId": row[5],
            "toolchainStepId": row[6],
            "cagComponent": row[7],
            "cagContractVersion": row[8],
            "normalizedQuestion": row[9],
            "normalizedInputSha256": row[10],
            "providerRequestId": row[11],
            "providerResponseUuid": row[12],
            "providerResponseSha256": row[13],
            "credentialFingerprintSha256": row[14],
            "verdict": row[15],
            "documentationClass": row[16],
            "derivedConclusion": row[17],
            "failureFamily": row[18],
            "quotaMetadata": _json_column(row[19]) or {},
            "rateLimitMetadata": _json_column(row[20]) or {},
            "assumptions": _json_column(row[21]) or [],
            "limitations": _json_column(row[22]) or [],
            "sourceRefs": _json_column(row[23]) or [],
            "evidencePassportHash": row[24],
            "hfPublicationRef": row[25],
            "hfTargetRevision": row[26],
            "createdAt": created.isoformat() if hasattr(created, "isoformat") else (str(created) if created else None),
        })
    return records


__all__ = [
    "SCHEMA_VERSION",
    "PACK_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "VERDICTS",
    "DOCUMENTATION_CLASSES",
    "PartnerAnalysisError",
    "build_partner_analysis_record",
    "public_partner_projection",
    "assert_partner_safe",
    "build_partner_handoff_pack",
    "render_partner_handoff_markdown",
    "attach_hf_publication",
    "evidence_passport_reference",
    "persist_partner_analysis",
    "load_partner_analyses",
]
