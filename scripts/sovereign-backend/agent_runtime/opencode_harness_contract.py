"""Truth contract for the optional OpenCode SDK coding harness.

This module deliberately does *not* add OpenCode to ``AGENT_EXECUTORS``.  It
binds a persisted Sovereign OpenRouter route to the OpenCode model namespace
and validates an external SDK canary receipt.  Promotion to a mutating agent
executor remains blocked until a separate tool-mutation canary exists.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from llm_transport import OPENROUTER_BASE_URL, OPENROUTER_TRANSPORT, route_config, route_transport

OPENCODE_HARNESS = "opencode-sdk"
OPENCODE_CANARY_RECEIPT_SCHEMA = "sovereign.opencode-sdk-canary-receipt.v1"
OX_ALPHA_PROVIDER_MODEL = "stealth/ox-alpha"
OX_ALPHA_OPENCODE_MODEL = f"openrouter/{OX_ALPHA_PROVIDER_MODEL}"


def opencode_model_for_openrouter(provider_model: str) -> str:
    clean = str(provider_model or "").strip()
    if not clean or "/" not in clean:
        return ""
    return f"openrouter/{clean}"


def _canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def _provider_policy_is_private(config: dict[str, Any]) -> bool:
    policy = config.get("providerPolicy") if isinstance(config.get("providerPolicy"), dict) else {}
    return (
        policy.get("require_parameters") is True
        and policy.get("allow_fallbacks") is False
        and str(policy.get("data_collection") or "").strip().lower() == "deny"
        and policy.get("zdr") is True
    )


def _route_is_direct_verified_openrouter(route: dict[str, Any]) -> bool:
    config = route_config(route)
    return (
        bool(route.get("enabled"))
        and route_transport(route) == OPENROUTER_TRANSPORT
        and str(config.get("apiBase") or "").rstrip("/") == OPENROUTER_BASE_URL
        and config.get("direct") is True
        and config.get("catalogVerified") is True
        and config.get("transportCanaryVerified") is True
        and config.get("selectable") is True
        and _provider_policy_is_private(config)
    )


def build_opencode_harness_binding(
    route: dict[str, Any],
    canary_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind one exact Sovereign route to OpenCode and fail closed on evidence.

    ``structuredCanaryVerified`` only proves SDK server health plus a structured
    model round-trip.  ``executorEligible`` intentionally remains false until a
    future receipt proves bounded tool mutation in an isolated workspace.
    """

    config = route_config(route)
    provider_model = str(config.get("providerModel") or "").strip()
    opencode_model = opencode_model_for_openrouter(provider_model)
    blockers: list[str] = []

    if not _route_is_direct_verified_openrouter(route):
        blockers.append("route_not_direct_verified_private_openrouter")
    if not provider_model:
        blockers.append("provider_model_missing")
    if not opencode_model:
        blockers.append("opencode_model_binding_invalid")

    receipt = canary_receipt if isinstance(canary_receipt, dict) else None
    receipt_sha256 = _canonical_sha256(receipt) if receipt else None
    structured_verified = False
    tool_mutation_verified = False

    if receipt is None:
        blockers.append("opencode_sdk_canary_missing")
    else:
        if receipt.get("schemaVersion") != OPENCODE_CANARY_RECEIPT_SCHEMA:
            blockers.append("opencode_sdk_canary_schema_mismatch")
        if receipt.get("harness") != OPENCODE_HARNESS:
            blockers.append("opencode_sdk_canary_harness_mismatch")
        if receipt.get("transport") != OPENROUTER_TRANSPORT:
            blockers.append("opencode_sdk_canary_transport_mismatch")
        if str(receipt.get("providerModel") or "") != provider_model:
            blockers.append("opencode_sdk_canary_provider_model_mismatch")
        if str(receipt.get("opencodeModel") or "") != opencode_model:
            blockers.append("opencode_sdk_canary_model_binding_mismatch")
        if receipt.get("serverHealthy") is not True:
            blockers.append("opencode_sdk_server_health_unverified")
        if receipt.get("structuredOutputVerified") is not True:
            blockers.append("opencode_sdk_structured_output_unverified")

        structured_verified = not any(blocker.startswith("opencode_sdk_") for blocker in blockers)
        tool_mutation_verified = receipt.get("toolMutationVerified") is True
        if not tool_mutation_verified:
            blockers.append("opencode_tool_mutation_canary_missing")

    return {
        "schemaVersion": "sovereign.opencode-harness-binding.v1",
        "harness": OPENCODE_HARNESS,
        "routeId": str(route.get("id") or ""),
        "transport": OPENROUTER_TRANSPORT,
        "providerModel": provider_model,
        "opencodeModel": opencode_model,
        "structuredCanaryVerified": structured_verified,
        "toolMutationVerified": tool_mutation_verified,
        "executorEligible": not blockers,
        "canaryReceiptSha256": receipt_sha256,
        "blockers": blockers,
    }


def build_ox_alpha_harness_candidate(route: dict[str, Any] | None, canary_receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an exact Ox Alpha candidate without inventing route availability."""

    if not isinstance(route, dict):
        return {
            "schemaVersion": "sovereign.opencode-harness-binding.v1",
            "harness": OPENCODE_HARNESS,
            "routeId": "",
            "transport": OPENROUTER_TRANSPORT,
            "providerModel": OX_ALPHA_PROVIDER_MODEL,
            "opencodeModel": OX_ALPHA_OPENCODE_MODEL,
            "structuredCanaryVerified": False,
            "toolMutationVerified": False,
            "executorEligible": False,
            "canaryReceiptSha256": None,
            "blockers": ["ox_alpha_verified_route_missing"],
        }

    binding = build_opencode_harness_binding(route, canary_receipt)
    blockers = list(binding["blockers"])
    if binding["providerModel"] != OX_ALPHA_PROVIDER_MODEL:
        blockers.append("ox_alpha_provider_model_mismatch")
    return {**binding, "executorEligible": not blockers, "blockers": blockers}
