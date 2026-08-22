"""Internal, secret-free runtime endpoints for Wolfram CAG live evidence.

CAG provider credentials, Wolfram Cloud secured-authentication credentials and
partner/public projections are deliberately separate trust domains. Fixed CAG
canaries remain non-semantic transport checks. The Wolfram Cloud extension may
render the already-redacted partner pack into one fixed private notebook and
perform bounded read-only Bitcoin mainnet queries; no transaction mutation,
signing or submission capability is exposed here.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import re
from typing import Any, Callable

from flask import jsonify, request

from agent_runtime.adapters.wolfram_agenttools import (
    WOLFRAM_CAG_COMPONENT_MAP,
    WolframCagError,
    execute_live_cag_request,
    resolve_cag_credentials,
)
from agent_runtime.wolfram_cag_partner_ledger import (
    CONTRACT_VERSION,
    build_partner_analysis_record,
    build_partner_handoff_pack,
    load_partner_analyses,
    persist_partner_analysis,
    public_partner_projection,
    render_partner_handoff_markdown,
)

ConnectionFactory = Callable[[], Any]
_REVISION = re.compile(r"^[0-9a-f]{40}$")

_CAG_CANARIES: dict[str, dict[str, Any]] = {
    "wolfram.cag.hints": {"context": "Find Wolfram Language code that computes 2+2."},
    "wolfram.cag.compute": {"code": "2+2", "maxChars": 256, "timeConstraint": 10},
    "wolfram.cag.results": {"input": "2+2"},
    "wolfram.cag.context": {"context": "What is 2+2?", "count": 1},
}


def _service_authorized() -> bool:
    expected = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
    supplied = request.headers.get("X-Sovereign-Owner-Request-Key", "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _revision() -> str | None:
    value = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip().casefold()
    return value if _REVISION.fullmatch(value) else None


def _input_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _close(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def _selected_components(value: Any) -> list[str]:
    if value in (None, []):
        return list(_CAG_CANARIES)
    if not isinstance(value, list) or not value or len(value) > len(_CAG_CANARIES):
        raise ValueError("components must be a non-empty bounded array")
    selected: list[str] = []
    for item in value:
        capability_id = str(item or "").strip()
        if capability_id not in _CAG_CANARIES:
            raise ValueError("components contains an unknown CAG capability")
        if capability_id not in selected:
            selected.append(capability_id)
    return selected


def _cloud_notebook_status() -> dict[str, Any]:
    try:
        from agent_runtime.wolfram_partner_notebook import wolfram_cloud_notebook_status

        return wolfram_cloud_notebook_status()
    except Exception as exc:
        return {
            "configured": False,
            "credentialFilesValid": False,
            "targetPath": None,
            "targetPathValid": False,
            "authenticated": False,
            "syncExecuted": False,
            "errorFamily": "CLOUD_NOTEBOOK_STATUS",
            "message": type(exc).__name__,
            "secretValuesReturned": False,
        }


def cag_runtime_status() -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    for capability_id, component in WOLFRAM_CAG_COMPONENT_MAP.items():
        credential_configured = False
        credential_error_family: str | None = None
        try:
            credential_configured = resolve_cag_credentials(capability_id=capability_id) is not None
        except WolframCagError as exc:
            credential_error_family = exc.family.value
        components.append({
            "capabilityId": capability_id,
            "component": component.component,
            "method": component.method,
            "endpoint": component.base_url,
            "expectedContentType": component.expected_content_type,
            "credentialConfigured": credential_configured,
            "credentialErrorFamily": credential_error_family,
        })
    return {
        "ok": True,
        "status": "WOLFRAM_CAG_RUNTIME_STATUS",
        "contractVersion": CONTRACT_VERSION,
        "sourceRevision": _revision(),
        "components": components,
        "cloudNotebook": _cloud_notebook_status(),
        "bitcoinReadback": {
            "network": "Bitcoin-Mainnet",
            "operations": ["network", "block", "transaction"],
            "readOnly": True,
            "transactionMutationAvailable": False,
        },
        "providerCanaryExecuted": False,
        "runtimeVerified": False,
        "secretValuesReturned": False,
    }


def run_cag_canaries(*, get_connection: ConnectionFactory, components: list[str] | None = None) -> dict[str, Any]:
    selected = _selected_components(components)
    revision = _revision()
    results: list[dict[str, Any]] = []
    documentation_ok = True
    connection = None
    try:
        connection = get_connection()
        for capability_id in selected:
            payload = dict(_CAG_CANARIES[capability_id])
            component = WOLFRAM_CAG_COMPONENT_MAP[capability_id]
            normalized_input_sha256 = _input_sha256(payload)
            try:
                receipt = execute_live_cag_request(capability_id=capability_id, payload=payload)
                record = build_partner_analysis_record(
                    component=component.component,
                    normalized_question=json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")),
                    normalized_input_sha256=normalized_input_sha256,
                    provider_response_sha256=receipt.response_hash,
                    credential_fingerprint_sha256=receipt.credential_hash,
                    verdict="INCONCLUSIVE",
                    derived_conclusion=(
                        "Provider transport and response-schema canary succeeded; "
                        "no semantic claim was evaluated by this canary."
                    ),
                    repository_revision=revision,
                    runtime_revision=revision,
                    provider_request_id=receipt.request_id or None,
                    provider_response_uuid=receipt.response_uuid or None,
                    documentation_class="PARTNER_REPORTABLE",
                    quota_metadata=(
                        {"quotaRemaining": receipt.quota_remaining} if receipt.quota_remaining else None
                    ),
                    rate_limit_metadata=(
                        {"rateLimitRemaining": receipt.rate_limit_remaining}
                        if receipt.rate_limit_remaining else None
                    ),
                    limitations=[
                        "Provider success remains SUCCEEDED_UNVERIFIED until immutable runtime and PatchMon/Docker readback are bound.",
                        "This fixed canary does not promote any semantic claim to SUPPORTED.",
                    ],
                    source_refs=["wolfram-official-cag-v1-contract"],
                    created_at=_now(),
                )
                persist_partner_analysis(connection, record)
                results.append({
                    "capabilityId": capability_id,
                    "component": component.component,
                    "status": receipt.status.value,
                    "responseStatus": receipt.response_status,
                    "requestHash": receipt.request_hash,
                    "responseHash": receipt.response_hash,
                    "responseUuid": receipt.response_uuid or None,
                    "requestId": receipt.request_id or None,
                    "rateLimitRemaining": receipt.rate_limit_remaining or None,
                    "quotaRemaining": receipt.quota_remaining or None,
                    "analysis": public_partner_projection(record),
                    "analysisPersisted": True,
                })
            except WolframCagError as exc:
                record = build_partner_analysis_record(
                    component=component.component,
                    normalized_question=json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")),
                    normalized_input_sha256=normalized_input_sha256,
                    provider_response_sha256=None,
                    credential_fingerprint_sha256=None,
                    verdict="UNAVAILABLE",
                    derived_conclusion=(
                        f"CAG canary did not produce usable provider evidence; failure family {exc.family.value}."
                    ),
                    repository_revision=revision,
                    runtime_revision=revision,
                    provider_request_id=exc.request_id or None,
                    provider_response_uuid=exc.response_uuid or None,
                    documentation_class="PARTNER_REPORTABLE",
                    failure_family=exc.family.value,
                    limitations=["No semantic claim may be supported or contradicted without usable provider evidence."],
                    source_refs=["wolfram-official-cag-v1-contract"],
                    created_at=_now(),
                )
                persist_partner_analysis(connection, record)
                results.append({
                    "capabilityId": capability_id,
                    "component": component.component,
                    "status": "FAILED",
                    "error": exc.public_payload(),
                    "analysis": public_partner_projection(record),
                    "analysisPersisted": True,
                })
    except Exception as exc:
        documentation_ok = False
        results.append({
            "status": "DOCUMENTATION_PERSISTENCE_FAILED",
            "errorFamily": "ANALYSIS_LEDGER_PERSISTENCE",
            "message": type(exc).__name__,
            "analysisPersisted": False,
        })
    finally:
        if connection is not None:
            _close(connection)

    all_provider_success = bool(results) and all(
        result.get("status") == "SUCCEEDED_UNVERIFIED" for result in results
    )
    return {
        "ok": all_provider_success and documentation_ok,
        "status": (
            "WOLFRAM_CAG_CANARIES_SUCCEEDED_UNVERIFIED"
            if all_provider_success and documentation_ok
            else "WOLFRAM_CAG_CANARIES_INCOMPLETE"
        ),
        "contractVersion": CONTRACT_VERSION,
        "sourceRevision": revision,
        "results": results,
        "documentationPersisted": documentation_ok and all(
            result.get("analysisPersisted") is True for result in results
        ),
        "providerCanaryExecuted": True,
        "runtimeVerified": False,
        "secretValuesReturned": False,
        "truthNotice": (
            "Provider canary success is not runtime verification; immutable image, "
            "PatchMon, Docker and exact revision readback remain separate gates."
        ),
    }


def build_partner_report(*, get_connection: ConnectionFactory) -> dict[str, Any]:
    """Deterministic partner handoff pack over all persisted analysis records."""
    connection = None
    try:
        connection = get_connection()
        records = load_partner_analyses(connection)
    except Exception as exc:
        return {
            "ok": False,
            "status": "WOLFRAM_CAG_PARTNER_REPORT_FAILED",
            "errorFamily": "ANALYSIS_LEDGER_READBACK",
            "message": type(exc).__name__,
            "secretValuesReturned": False,
        }
    finally:
        if connection is not None:
            _close(connection)
    try:
        pack = build_partner_handoff_pack(records, generated_at=_now())
        markdown = render_partner_handoff_markdown(pack)
    except Exception as exc:
        return {
            "ok": False,
            "status": "WOLFRAM_CAG_PARTNER_REPORT_FAILED",
            "errorFamily": "ANALYSIS_LEDGER_REDACTION",
            "message": type(exc).__name__,
            "secretValuesReturned": False,
        }
    return {
        "ok": True,
        "status": "WOLFRAM_CAG_PARTNER_REPORT",
        "contractVersion": CONTRACT_VERSION,
        "sourceRevision": _revision(),
        "pack": pack,
        "markdown": markdown,
        "recordCount": pack["recordCount"],
        "secretValuesReturned": False,
        "truthNotice": (
            "The partner report is a redaction-gated projection of persisted analysis "
            "records; a successful render is never a verification."
        ),
    }


def build_partner_notebook_preview(*, get_connection: ConnectionFactory) -> dict[str, Any]:
    report = build_partner_report(get_connection=get_connection)
    if not report.get("ok"):
        return report
    try:
        from agent_runtime.wolfram_partner_notebook import build_partner_notebook_projection

        projection = build_partner_notebook_projection(report["pack"])
    except Exception as exc:
        return {
            "ok": False,
            "status": "WOLFRAM_CLOUD_NOTEBOOK_PREVIEW_FAILED",
            "errorFamily": getattr(exc, "family", "NOTEBOOK_PROJECTION"),
            "message": type(exc).__name__,
            "secretValuesReturned": False,
        }
    return {
        "ok": True,
        "status": "WOLFRAM_CLOUD_NOTEBOOK_PREVIEW",
        "sourceRevision": _revision(),
        "projection": projection,
        "notebookProjectionSha256": projection["notebookProjectionSha256"],
        "cloudWriteExecuted": False,
        "secretValuesReturned": False,
        "truthNotice": "Notebook preview is a deterministic projection only; no Wolfram Cloud write or readback occurred.",
    }


def sync_partner_notebook_report(*, get_connection: ConnectionFactory) -> dict[str, Any]:
    report = build_partner_report(get_connection=get_connection)
    if not report.get("ok"):
        return report
    try:
        from agent_runtime.wolfram_partner_notebook import sync_partner_notebook

        return sync_partner_notebook(report["pack"])
    except Exception as exc:
        return {
            "ok": False,
            "status": "WOLFRAM_CLOUD_NOTEBOOK_SYNC_FAILED",
            "errorFamily": getattr(exc, "family", "CLOUD_NOTEBOOK_SYNC"),
            "message": type(exc).__name__,
            "secretValuesReturned": False,
        }


def run_bitcoin_research_readback(body: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) - {"operation", "identifier", "properties"}:
        return {
            "ok": False,
            "status": "WOLFRAM_BITCOIN_READBACK_FAILED",
            "errorFamily": "READBACK_SCHEMA",
            "message": "invalid_request",
            "secretValuesReturned": False,
        }
    try:
        from agent_runtime.wolfram_blockchain_readback import run_bitcoin_readback

        return run_bitcoin_readback(
            operation=body.get("operation"),
            identifier=body.get("identifier"),
            properties=body.get("properties"),
        )
    except Exception as exc:
        return {
            "ok": False,
            "status": "WOLFRAM_BITCOIN_READBACK_FAILED",
            "errorFamily": getattr(exc, "family", "BLOCKCHAIN_READBACK"),
            "message": type(exc).__name__,
            "secretValuesReturned": False,
        }


def register_wolfram_cag_runtime(app: Any, *, get_connection: ConnectionFactory) -> None:
    @app.route("/api/internal/wolfram-cag/status", methods=["GET"])
    def _status():
        if not _service_authorized():
            return jsonify({"ok": False, "error": "service_unauthorized"}), 401
        return jsonify(cag_runtime_status()), 200

    @app.route("/api/internal/wolfram-cag/canary", methods=["POST"])
    def _canary():
        if not _service_authorized():
            return jsonify({"ok": False, "error": "service_unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or set(body) - {"components"}:
            return jsonify({"ok": False, "error": "invalid_request"}), 400
        try:
            selected = _selected_components(body.get("components"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        result = run_cag_canaries(get_connection=get_connection, components=selected)
        return jsonify(result), (200 if result.get("ok") else 409)

    @app.route("/api/internal/wolfram-cag/partner-report", methods=["GET"])
    def _partner_report():
        if not _service_authorized():
            return jsonify({"ok": False, "error": "service_unauthorized"}), 401
        result = build_partner_report(get_connection=get_connection)
        return jsonify(result), (200 if result.get("ok") else 500)

    @app.route("/api/internal/wolfram-cag/partner-notebook", methods=["GET"])
    def _partner_notebook_preview():
        if not _service_authorized():
            return jsonify({"ok": False, "error": "service_unauthorized"}), 401
        result = build_partner_notebook_preview(get_connection=get_connection)
        return jsonify(result), (200 if result.get("ok") else 500)

    @app.route("/api/internal/wolfram-cag/partner-notebook/sync", methods=["POST"])
    def _partner_notebook_sync():
        if not _service_authorized():
            return jsonify({"ok": False, "error": "service_unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        if body != {}:
            return jsonify({"ok": False, "error": "invalid_request"}), 400
        result = sync_partner_notebook_report(get_connection=get_connection)
        return jsonify(result), (200 if result.get("ok") else 409)

    @app.route("/api/internal/wolfram-cag/blockchain/readback", methods=["POST"])
    def _blockchain_readback():
        if not _service_authorized():
            return jsonify({"ok": False, "error": "service_unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        result = run_bitcoin_research_readback(body)
        return jsonify(result), (200 if result.get("ok") else 409)


__all__ = [
    "build_partner_notebook_preview",
    "build_partner_report",
    "cag_runtime_status",
    "register_wolfram_cag_runtime",
    "run_bitcoin_research_readback",
    "run_cag_canaries",
    "sync_partner_notebook_report",
]
