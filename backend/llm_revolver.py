"""Deterministic, quota-gated direct-FreeLLM revolver policy.

The module is intentionally side-effect free. PostgreSQL persistence and provider
network calls stay in runtime modules so candidate selection and retry decisions
can be unit-tested without credentials or a running provider.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from llm_cost_policy import BillingPolicyError, FREE_CATEGORY, route_billing_policy
from llm_transport import (
    FREELLM_TRANSPORT,
    LEGACY_LITELLM_TRANSPORT,
    OPENROUTER_TRANSPORT,
    route_is_direct_freellm,
    route_is_openrouter_free,
    route_transport,
    route_transport_diagnostics,
)

_SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RECEIPT_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_FREELLM_RECEIPT_SCHEMA = "sovereign.freellm-route-receipt.v3"
_OPENROUTER_FREE_RECEIPT_SCHEMA = "sovereign.openrouter-free-route-receipt.v1"
_RETRY_WINDOWS_SECONDS = {
    "provider_quota_exhausted": 3600,
    "provider_rate_limited": 60,
    "litellm_upstream_unavailable": 30,
    "openrouter_rate_limited": 60,
    "openrouter_timeout": 30,
    "openrouter_upstream_unavailable": 30,
    "freellm_rate_limited": 60,
    "freellm_timeout": 30,
    "freellm_upstream_unavailable": 30,
}
_BLOCKED_FAILURES = {
    "provider_credentials_rejected",
    "litellm_model_alias_missing",
    "litellm_model_alias_invalid",
    "openrouter_credentials_rejected",
    "freellm_credentials_rejected",
}


def default_quota_scope(
    route_id: Any,
    *,
    transport: str = LEGACY_LITELLM_TRANSPORT,
) -> str:
    """Return an opaque stable fallback scope without exposing route or key material."""
    normalized_transport = route_transport({
        "provider": transport,
        "runtime_kind": transport,
    }) or LEGACY_LITELLM_TRANSPORT
    digest = hashlib.sha256(str(route_id or "missing-route").encode("utf-8")).hexdigest()
    return f"{normalized_transport}:route:{digest[:24]}"


def normalize_quota_scope(value: Any, *, route_id: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return default_quota_scope(route_id)
    if not _SCOPE_RE.fullmatch(candidate):
        raise ValueError(
            "quotaScope muss 8-128 Zeichen lang sein und darf nur Buchstaben, "
            "Zahlen, Punkt, Unterstrich, Doppelpunkt oder Bindestrich enthalten"
        )
    return candidate


def route_quota_scope(route: dict[str, Any]) -> str:
    config = route.get("config") if isinstance(route.get("config"), dict) else {}
    configured = config.get("quotaScope")
    if configured:
        return normalize_quota_scope(configured, route_id=route.get("id"))
    return default_quota_scope(
        route.get("id"),
        transport=route_transport(route) or LEGACY_LITELLM_TRANSPORT,
    )


def _route_receipt_matches_runtime(route: dict[str, Any]) -> bool:
    config = route.get("config") if isinstance(route.get("config"), dict) else {}
    identity = config.get("runtimeIdentity") if isinstance(config.get("runtimeIdentity"), dict) else {}
    receipt = config.get("canaryReceipt") if isinstance(config.get("canaryReceipt"), dict) else {}
    source_revision = str(identity.get("sourceRevision") or "").strip().lower()
    image_digest = str(identity.get("imageDigest") or "").strip().lower()
    current_revision = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip().lower()
    current_digest = os.getenv("SOVEREIGN_IMAGE_DIGEST", "").strip().lower()
    expected_schema = (
        _OPENROUTER_FREE_RECEIPT_SCHEMA
        if route_is_openrouter_free(route)
        else _FREELLM_RECEIPT_SCHEMA
        if route_is_direct_freellm(route)
        else ""
    )
    return (
        bool(expected_schema)
        and identity.get("sourceRevisionVerified") is True
        and identity.get("imageDigestVerified") is True
        and _SOURCE_REVISION_RE.fullmatch(source_revision) is not None
        and _IMAGE_DIGEST_RE.fullmatch(image_digest) is not None
        and source_revision == current_revision
        and image_digest == current_digest
        and str(receipt.get("schemaVersion") or "") == expected_schema
        and receipt.get("generalChatEvidenceVerified") is True
        and (
            route_transport(route) != OPENROUTER_TRANSPORT
            or receipt.get("zeroCostEvidenceVerified") is True
        )
        and _RECEIPT_SHA_RE.fullmatch(str(receipt.get("receiptSha256") or "")) is not None
    )


def verify_free_route_reason(route: dict[str, Any]) -> dict[str, Any]:
    """Return bounded reasons why a free route is or is not execution-eligible."""
    failures: list[str] = []
    transport_diagnostic = route_transport_diagnostics(route)
    if transport_diagnostic.get("ok") is not True:
        failures.append(str(
            transport_diagnostic.get("failureFamily") or "route_transport_invalid"
        ))
    transport = route_transport(route)
    direct_freellm = (
        route_is_direct_freellm(route)
        and transport == FREELLM_TRANSPORT
    )
    openrouter_free = (
        route_is_openrouter_free(route)
        and transport == OPENROUTER_TRANSPORT
    )
    route_family = (
        "FREELLM_FREE"
        if direct_freellm
        else "OPENROUTER_FREE"
        if openrouter_free
        else "UNRESOLVED"
    )
    if not (direct_freellm or openrouter_free):
        failures.append("free_route_family_rejected")

    config = route.get("config") if isinstance(route.get("config"), dict) else {}
    identity = (
        config.get("runtimeIdentity")
        if isinstance(config.get("runtimeIdentity"), dict)
        else {}
    )
    receipt = (
        config.get("canaryReceipt")
        if isinstance(config.get("canaryReceipt"), dict)
        else {}
    )
    source_revision = str(identity.get("sourceRevision") or "").strip().lower()
    image_digest = str(identity.get("imageDigest") or "").strip().lower()
    current_revision = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip().lower()
    current_digest = os.getenv("SOVEREIGN_IMAGE_DIGEST", "").strip().lower()
    expected_schema = (
        _OPENROUTER_FREE_RECEIPT_SCHEMA
        if openrouter_free
        else _FREELLM_RECEIPT_SCHEMA
        if direct_freellm
        else ""
    )
    if identity.get("sourceRevisionVerified") is not True:
        failures.append("free_runtime_source_revision_unverified")
    if _SOURCE_REVISION_RE.fullmatch(source_revision) is None:
        failures.append("free_runtime_source_revision_invalid")
    if _SOURCE_REVISION_RE.fullmatch(current_revision) is None:
        failures.append("free_current_source_revision_unverified")
    elif source_revision != current_revision:
        failures.append("free_runtime_source_revision_mismatch")
    if identity.get("imageDigestVerified") is not True:
        failures.append("free_runtime_image_digest_unverified")
    if _IMAGE_DIGEST_RE.fullmatch(image_digest) is None:
        failures.append("free_runtime_image_digest_invalid")
    if _IMAGE_DIGEST_RE.fullmatch(current_digest) is None:
        failures.append("free_current_image_digest_unverified")
    elif image_digest != current_digest:
        failures.append("free_runtime_image_digest_mismatch")
    if not expected_schema or str(receipt.get("schemaVersion") or "") != expected_schema:
        failures.append("free_canary_receipt_schema_mismatch")
    if receipt.get("generalChatEvidenceVerified") is not True:
        failures.append("free_canary_chat_evidence_missing")
    if openrouter_free and receipt.get("zeroCostEvidenceVerified") is not True:
        failures.append("openrouter_free_zero_cost_evidence_missing")
    if _RECEIPT_SHA_RE.fullmatch(str(receipt.get("receiptSha256") or "")) is None:
        failures.append("free_canary_receipt_sha_invalid")

    quota_evidence = (
        config.get("quotaEvidence")
        if isinstance(config.get("quotaEvidence"), dict)
        else {}
    )
    policy: dict[str, Any] | None = None
    try:
        policy = route_billing_policy(route)
    except BillingPolicyError:
        failures.append("free_billing_policy_invalid")
    if policy is not None:
        if policy["billingCategory"] != FREE_CATEGORY:
            failures.append("free_billing_category_mismatch")
        if policy["fundingMode"] != "provider_free_quota":
            failures.append("free_funding_mode_mismatch")
        if not bool(policy["freeEligible"]):
            failures.append("free_eligibility_missing")
        if not bool(policy["quotaContractVerified"]):
            failures.append("free_quota_contract_missing")
        if int(policy["markupMultiplier"]) != 0:
            failures.append("free_markup_nonzero")
        if int(policy["userChargeCredits"] or 0) != 0:
            failures.append("free_user_charge_nonzero")
    if config.get("canaryVerified") is not True:
        failures.append("free_canary_unverified")
    try:
        confirmation_count = int(config.get("canaryConfirmationCount") or 0)
    except (TypeError, ValueError):
        confirmation_count = -1
    if confirmation_count < 2:
        failures.append("free_double_canary_missing")
    try:
        quota_scope = route_quota_scope(route)
    except ValueError:
        quota_scope = ""
        failures.append("free_quota_scope_invalid")
    if str(quota_evidence.get("scope") or "") != quota_scope:
        failures.append("free_quota_scope_mismatch")
    if str(quota_evidence.get("stateOwner") or "") != "postgresql-revolver-state":
        failures.append("free_quota_state_owner_mismatch")

    return {
        "ok": not failures,
        "routeId": str(route.get("id") or "")[:160],
        "transport": transport,
        "routeFamily": route_family,
        "failureFamilies": list(dict.fromkeys(failures)),
        "secretValuesReturned": False,
    }


def route_is_verified_free(route: dict[str, Any]) -> bool:
    return verify_free_route_reason(route)["ok"] is True


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def _first_number(*values: Any) -> Decimal | None:
    for value in values:
        if value is None:
            continue
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _datetime_rank(value: datetime | None) -> int:
    if value is None:
        return -1
    normalized = value.astimezone(timezone.utc)
    delta = normalized - _UTC_EPOCH
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000) + delta.microseconds


def _quota_rank(
    route: dict[str, Any],
    state: dict[str, Any] | None,
    *,
    primary_id: str,
    now: datetime,
) -> tuple[Any, ...]:
    config = route.get("config") if isinstance(route.get("config"), dict) else {}
    current = state or {}
    remaining = _first_number(
        current.get("quota_remaining"),
        current.get("quotaRemaining"),
        config.get("quotaRemaining"),
    )
    limit = _first_number(
        current.get("quota_limit"),
        current.get("quotaLimit"),
        config.get("quotaLimit"),
    )
    quota_reset = _as_datetime(
        current.get("quota_reset_at") or current.get("quotaResetAt")
    )
    if remaining == 0 and quota_reset is not None and quota_reset <= now:
        remaining = None
        limit = None
    ratio = remaining / limit if remaining is not None and limit and limit > 0 else remaining
    availability = 0 if remaining is not None and remaining > 0 else 2 if remaining == 0 else 1
    cooldown_until = _as_datetime(
        current.get("cooldown_until") or current.get("cooldownUntil")
    )
    status = str(current.get("status") or "ready").strip().lower()
    failure_count = int(
        current.get("consecutive_failures")
        or current.get("consecutiveFailures")
        or 0
    )
    if status == "cooldown" and cooldown_until is not None and cooldown_until <= now:
        failure_count = 0
    last_attempt = _as_datetime(
        current.get("last_attempt_at") or current.get("lastAttemptAt")
    )
    attempt_rank = _datetime_rank(last_attempt)
    latency_ms = _first_number(
        current.get("last_latency_ms"),
        current.get("lastLatencyMs"),
        config.get("canaryLatencyMs"),
    )
    return (
        availability,
        -(ratio if ratio is not None else Decimal(0)),
        failure_count,
        0 if last_attempt is None else 1,
        attempt_rank,
        0 if latency_ms is not None else 1,
        latency_ms if latency_ms is not None else Decimal(0),
        int(route.get("priority") or 0),
        0 if str(route.get("id") or "") == primary_id else 1,
        str(route.get("model_id") or route.get("modelId") or "").casefold(),
        str(route.get("id") or ""),
    )


def _state_available(state: dict[str, Any] | None, now: datetime) -> bool:
    if not state:
        return True
    status = str(state.get("status") or "ready").strip().lower()
    if status == "blocked":
        return False
    remaining = _first_number(
        state.get("quota_remaining"),
        state.get("quotaRemaining"),
    )
    quota_reset = _as_datetime(
        state.get("quota_reset_at") or state.get("quotaResetAt")
    )
    if remaining == 0 and quota_reset is not None and quota_reset > now:
        return False
    cooldown_until = _as_datetime(
        state.get("cooldown_until") or state.get("cooldownUntil")
    )
    if status != "cooldown":
        return True
    return cooldown_until is not None and cooldown_until <= now


def build_revolver_candidates(
    primary: dict[str, Any],
    routes: Iterable[dict[str, Any]],
    *,
    state_by_scope: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return verified free routes, primary first, with one route per quota scope."""
    if not route_is_verified_free(primary):
        return [primary]
    state_by_scope = state_by_scope or {}
    current_time = now or datetime.now(timezone.utc)
    primary_id = str(primary.get("id") or "")
    verified_routes = [
        route for route in routes if route_is_verified_free(route)
    ]
    if not any(str(route.get("id") or "") == primary_id for route in verified_routes):
        verified_routes.append(primary)
    ordered = sorted(
        verified_routes,
        key=lambda route: _quota_rank(
            route,
            state_by_scope.get(route_quota_scope(route)),
            primary_id=primary_id,
            now=current_time,
        ),
    )
    candidates: list[dict[str, Any]] = []
    seen_scopes: set[str] = set()
    for route in ordered:
        if not route_is_verified_free(route):
            continue
        scope = route_quota_scope(route)
        if scope in seen_scopes or not _state_available(state_by_scope.get(scope), current_time):
            continue
        candidates.append(route)
        seen_scopes.add(scope)
    return candidates


def provider_usage_seen(evidence: dict[str, Any]) -> bool:
    """An upstream request id alone is not billable usage evidence."""
    try:
        if int(evidence.get("totalTokens") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    cost = _number(evidence.get("providerCostUsd"))
    return cost is not None and cost > 0


def failure_decision(classified: dict[str, Any], *, usage_seen: bool) -> dict[str, Any]:
    blocker = str(classified.get("blocker") or "provider_rejected")[:120]
    if usage_seen:
        return {
            "blocker": blocker,
            "retryAllowed": False,
            "state": "blocked",
            "cooldownSeconds": 0,
        }
    if blocker in _RETRY_WINDOWS_SECONDS:
        return {
            "blocker": blocker,
            "retryAllowed": True,
            "state": "cooldown",
            "cooldownSeconds": _RETRY_WINDOWS_SECONDS[blocker],
        }
    return {
        "blocker": blocker,
        "retryAllowed": False,
        "state": "blocked" if blocker in _BLOCKED_FAILURES else "ready",
        "cooldownSeconds": 0,
    }
