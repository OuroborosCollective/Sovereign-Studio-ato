"""Internal, secret-free runtime endpoints for Wolfram CAG live evidence.

Only fixed canaries are exposed. Arbitrary CAG prompts are deliberately not an
operator API here: semantic claim verification remains owned by the existing
CAG receipt/evidence lane. The protected provider credential is resolved only
inside ``execute_live_cag_request`` and never enters Flask request/response
payloads.
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
    persist_partner_analysis,
    public_partner_projection,
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
        raw_body = request.get_json(silent=True)
        if raw_body is None:
            body = {}
        elif isinstance(raw_body, dict):
            body = raw_body
        else:
            return jsonify({"ok": False, "error": "invalid_request"}), 400
        if set(body) - {"components"}:
            return jsonify({"ok": False, "error": "invalid_request"}), 400
        try:
            selected = _selected_components(body.get("components"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        result = run_cag_canaries(get_connection=get_connection, components=selected)
        return jsonify(result), (200 if result.get("ok") else 409)


__all__ = [
    "cag_runtime_status",
    "run_cag_canaries",
    "register_wolfram_cag_runtime",
]
