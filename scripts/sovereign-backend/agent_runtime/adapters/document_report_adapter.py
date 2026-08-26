"""Document/Report Adapter for Sovereign Evidence projection.

This module provides a projecting Document/Report Adapter that transforms verified
Sovereign Evidence from Gate Receipts and Evidence Passports into human-readable
PDF/DOCX reports without generating legal, brand, or evidence truth.

The adapter maintains hard truth boundaries:
- ARTIFACT_RENDERED != LEGALLY_VALID
- ARTIFACT_RENDERED != WOLFRAM_APPROVED
- ARTIFACT_RENDERED != VERIFIED
- ARTIFACT_RENDERED != PUBLISHABLE
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "sovereign.document-adapter.v1"
RENDER_SCHEMA_VERSION = "sovereign.render-receipt.v1"

# Truth boundary constants - these must NEVER be upgraded by rendering
VERDICT_STATES = frozenset({
    "UNVERIFIED_REFERENCE",
    "AUTHORIZED_BRAND_REFERENCE",
    "LEGAL_REVIEWED_TEMPLATE",
    "ARTIFACT_RENDERED",
})

# Forbidden upgrade paths - rendered docs cannot claim these
FORBIDDEN_VERDICTS = frozenset({
    "VERIFIED",
    "PUBLISHABLE",
    "LEGALLY_VALID",
    "WOLFRAM_APPROVED",
    "APPROVED",
})

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z?$")


class DocumentFormat(str, Enum):
    """Supported output formats."""
    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"


class EvidenceReferenceState(str, Enum):
    """Evidence states for external references in documents."""
    UNVERIFIED = "UNVERIFIED_REFERENCE"
    AUTHORIZED = "AUTHORIZED_BRAND_REFERENCE"
    LEGAL_TEMPLATE = "LEGAL_REVIEWED_TEMPLATE"
    RENDERED = "ARTIFACT_RENDERED"


@dataclass(frozen=True)
class RenderReceipt:
    """Receipt for a rendered document artifact."""
    artifact_sha256: str
    render_timestamp: str
    source_receipt_sha256: str
    source_passport_sha256: str
    format: str
    schema_version: str = RENDER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactSha256": self.artifact_sha256,
            "renderTimestamp": self.render_timestamp,
            "sourceReceiptSha256": self.source_receipt_sha256,
            "sourcePassportSha256": self.source_passport_sha256,
            "format": self.format,
            "schemaVersion": self.schema_version,
        }


@dataclass
class DocumentAdapterRequest:
    """Request to render a document from evidence."""
    gate_receipt: dict[str, Any]
    evidence_passport: dict[str, Any]
    format: DocumentFormat = DocumentFormat.PDF
    include_timeline: bool = True
    include_sources: bool = True
    include_receipt_details: bool = True


def _canonical_json(value: Any) -> str:
    """Create canonical JSON for deterministic hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    """Compute SHA-256 hash of a value."""
    text = _canonical_json(value) if not isinstance(value, str) else value
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_receipt(receipt: dict[str, Any]) -> list[str]:
    """Validate gate receipt structure and return errors."""
    errors = []
    if not isinstance(receipt, dict):
        errors.append("receipt_not_object")
        return errors

    # Check required fields
    if "passed" not in receipt:
        errors.append("receipt_missing_passed")
    if "claimSha256" not in receipt:
        errors.append("receipt_missing_claim_sha256")
    if "gateSha256" not in receipt:
        errors.append("receipt_missing_gate_sha256")

    # Validate SHA-256 format if present
    claim_sha = receipt.get("claimSha256", "")
    if claim_sha and not _HEX64.match(claim_sha):
        errors.append("receipt_claim_sha_invalid")

    gate_sha = receipt.get("gateSha256", "")
    if gate_sha and not _HEX64.match(gate_sha):
        errors.append("receipt_gate_sha_invalid")

    return errors


def _validate_passport(passport: dict[str, Any]) -> list[str]:
    """Validate evidence passport structure and return errors."""
    errors = []
    if not isinstance(passport, dict):
        errors.append("passport_not_object")
        return errors

    # Check required fields
    if "schemaVersion" not in passport:
        errors.append("passport_missing_schema")
    if "passportSha256" not in passport:
        errors.append("passport_missing_sha256")

    # Validate SHA-256 format if present
    passport_sha = passport.get("passportSha256", "")
    if passport_sha and not _HEX64.match(passport_sha):
        errors.append("passport_sha_invalid")

    return errors


def _check_verdict_boundary(receipt: dict[str, Any], passport: dict[str, Any]) -> list[str]:
    """Check that receipt/passport don't contain forbidden verdict upgrades."""
    violations = []

    receipt_verdict = str(receipt.get("verdict", "")).upper()
    passport_verdict = str(passport.get("verdict", "")).upper()

    for verdict in (receipt_verdict, passport_verdict):
        if verdict in FORBIDDEN_VERDICTS:
            violations.append(f"forbidden_verdict_in_source: {verdict}")

    return violations


def _classify_reference_state(claim_text: str, sources: Sequence[dict[str, Any]]) -> EvidenceReferenceState:
    """Classify the evidence reference state based on claim and sources."""
    # If no sources, it's unverified
    if not sources:
        return EvidenceReferenceState.UNVERIFIED

    # Check if all sources have verified provenance
    all_verified = all(
        source.get("provenance", {}).get("verified", False)
        for source in sources
        if isinstance(source, dict)
    )

    if all_verified:
        return EvidenceReferenceState.AUTHORIZED

    # Check for legal review markers
    has_legal = any(
        source.get("evidenceClass") == "legal-reviewed"
        for source in sources
        if isinstance(source, dict)
    )

    if has_legal:
        return EvidenceReferenceState.LEGAL_TEMPLATE

    return EvidenceReferenceState.UNVERIFIED


def render_evidence_report(request: DocumentAdapterRequest) -> tuple[dict[str, Any] | None, list[str]]:
    """Render an evidence report from gate receipt and passport.

    Args:
        request: The document adapter request with evidence inputs

    Returns:
        Tuple of (rendered_document_dict or None, list of errors)
    """
    errors = []

    # Validate gate receipt
    receipt_errors = _validate_receipt(request.gate_receipt)
    errors.extend([f"receipt:{e}" for e in receipt_errors])

    # Validate evidence passport
    passport_errors = _validate_passport(request.evidence_passport)
    errors.extend([f"passport:{e}" for e in passport_errors])

    if errors:
        return None, errors

    # Check verdict boundary
    boundary_violations = _check_verdict_boundary(request.gate_receipt, request.evidence_passport)
    if boundary_violations:
        errors.extend(boundary_violations)
        return None, errors

    # Build the markdown content
    lines = _build_report_content(request)

    # Generate artifact hash
    content_json = _canonical_json(lines)
    artifact_sha256 = hashlib.sha256(content_json.encode("utf-8")).hexdigest()

    # Create render receipt
    render_receipt = RenderReceipt(
        artifact_sha256=artifact_sha256,
        render_timestamp=_utc_now_iso(),
        source_receipt_sha256=request.gate_receipt.get("gateSha256", ""),
        source_passport_sha256=request.evidence_passport.get("passportSha256", ""),
        format=request.format.value,
    )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "content": "\n".join(lines),
        "format": request.format.value,
        "renderReceipt": render_receipt.to_dict(),
        "truthBoundary": {
            "artifactRendered": True,
            "legallyValid": False,
            "verified": False,
            "publishable": False,
            "wolframApproved": False,
        },
    }, []


def _build_report_content(request: DocumentAdapterRequest) -> list[str]:
    """Build the report content as markdown lines."""
    receipt = request.gate_receipt
    passport = request.evidence_passport

    lines = [
        "# Sovereign Evidence Report",
        "",
        f"**Report Generated**: {_utc_now_iso()}",
        f"**Schema Version**: {SCHEMA_VERSION}",
        "",
        "## Truth Boundary Notice",
        "",
        "This document is a **projection** of verified evidence, not a legal or brand authority.",
        "",
        "- `ARTIFACT_RENDERED` ≠ `LEGALLY_VALID`",
        "- `ARTIFACT_RENDERED` ≠ `VERIFIED`",
        "- `ARTIFACT_RENDERED` ≠ `PUBLISHABLE`",
        "- `ARTIFACT_RENDERED` ≠ `WOLFRAM_APPROVED`",
        "",
        "## Evidence Gate Result",
        "",
    ]

    # Gate receipt status
    passed = receipt.get("passed", False)
    lines.append(f"- **Gate Status**: {'PASSED' if passed else 'FAILED'}")
    lines.append(f"- **Claim SHA-256**: `{receipt.get('claimSha256', 'N/A')}`")
    lines.append(f"- **Gate SHA-256**: `{receipt.get('gateSha256', 'N/A')}`")

    if request.include_receipt_details:
        reason = receipt.get("reason", "N/A")
        lines.append(f"- **Reason**: {reason}")

        evidence_count = receipt.get("evidenceCount", 0)
        lines.append(f"- **Evidence Count**: {evidence_count}")

        placeholder_count = receipt.get("placeholderCount", 0)
        lines.append(f"- **Placeholder Count**: {placeholder_count}")

    lines.append("")

    # Evidence Passport
    lines.extend([
        "## Evidence Passport",
        "",
        f"- **Passport SHA-256**: `{passport.get('passportSha256', 'N/A')}`",
        f"- **Schema Version**: {passport.get('schemaVersion', 'N/A')}",
    ])

    verdict = passport.get("verdict", "UNKNOWN")
    lines.append(f"- **Verdict**: {verdict}")

    receipt_valid = passport.get("proofReceiptValid", False)
    lines.append(f"- **Proof Receipt Valid**: {receipt_valid}")

    lines.append("")

    # Claim information
    claim = receipt.get("claim", {})
    if isinstance(claim, dict):
        lines.extend([
            "## Claim",
            "",
            f"**Claim Text**: {claim.get('text', 'N/A')}",
            f"**Claim SHA-256**: `{claim.get('sha256', 'N/A')}`" if claim.get('sha256') else "",
        ])
        lines.append("")

    # Timeline
    if request.include_timeline:
        timeline = receipt.get("timeline", [])
        if timeline:
            lines.extend([
                "## Timeline",
                "",
            ])
            for event in timeline[:20]:  # Limit to 20 events
                ts = event.get("timestamp", "N/A")
                desc = event.get("description", "")
                lines.append(f"- *{ts}*: {desc}")
            lines.append("")

    # Sources
    if request.include_sources:
        sources = receipt.get("sources", [])
        if sources:
            lines.extend([
                "## Sources",
                "",
            ])
            for source in sources[:20]:  # Limit to 20 sources
                source_id = source.get("id", "N/A")
                source_label = source.get("label", "N/A")
                source_type = source.get("type", "unknown")

                # Classify reference state
                state = _classify_reference_state(
                    source.get("claimText", ""),
                    [source]
                )

                lines.append(f"- **Source {source_id}**: {source_label} ({source_type}) - {state.value}")
            lines.append("")

    # Render receipt
    lines.extend([
        "## Render Receipt",
        "",
        "*This section documents the rendering process for reproducibility.*",
        "",
        f"- **Artifact SHA-256**: (computed after rendering)",
        f"- **Render Timestamp**: {_utc_now_iso()}",
        f"- **Format**: {request.format.value}",
    ])

    return lines


def create_render_receipt(
    artifact_content: str,
    source_receipt_sha256: str,
    source_passport_sha256: str,
    format: DocumentFormat,
) -> RenderReceipt:
    """Create a render receipt for an artifact.

    Args:
        artifact_content: The actual rendered document content
        source_receipt_sha256: SHA-256 of the source gate receipt
        source_passport_sha256: SHA-256 of the source evidence passport
        format: Output format used

    Returns:
        RenderReceipt with computed artifact hash
    """
    artifact_sha256 = hashlib.sha256(artifact_content.encode("utf-8")).hexdigest()

    return RenderReceipt(
        artifact_sha256=artifact_sha256,
        render_timestamp=_utc_now_iso(),
        source_receipt_sha256=source_receipt_sha256,
        source_passport_sha256=source_passport_sha256,
        format=format.value,
    )


# Adapter capability map for integration with Sovereign runtime
DOCUMENT_ADAPTER_CAPABILITIES = {
    "document:render:pdf": "Render evidence to PDF format",
    "document:render:docx": "Render evidence to DOCX format",
    "document:render:markdown": "Render evidence to Markdown format",
    "document:validate:receipt": "Validate gate receipt structure",
    "document:validate:passport": "Validate evidence passport structure",
    "document:check:boundary": "Check verdict boundary compliance",
}
