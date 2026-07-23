"""Sovereign integration of the Revolver v3 free-route core.

Provider credentials, billing, authentication and route truth remain owned by
the Sovereign/PostgreSQL direct-FreeLLM contract. This module only plans and
executes verified free route magazines supplied by the caller.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence


class RevolverExhausted(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RevolverProfile:
    profile_key: str = "default-free"
    mode: str = "sequential"
    race_n: int = 3
    timeout_ms: int = 30_000
    token_budget: int = 32_000
    required_capabilities: tuple[str, ...] = ("chat",)
    preferred_route_ids: tuple[str, ...] = ()
    route_weights_ppm: Mapping[str, int] = field(default_factory=dict)
    structured_repair_attempts: int = 1
    semantic_cache_enabled: bool = False
    revision: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "RevolverProfile":
        row = dict(value or {})
        mode = str(row.get("mode") or "sequential").lower()
        if mode not in {"sequential", "weighted", "race"}:
            mode = "sequential"
        weights = row.get("routeWeights") or {}
        return cls(
            profile_key=str(row.get("profileKey") or "default-free")[:120],
            mode=mode,
            race_n=max(1, min(int(row.get("raceN") or 3), 8)),
            timeout_ms=max(1000, min(int(row.get("timeoutMs") or 30000), 120000)),
            token_budget=max(128, min(int(row.get("tokenBudget") or 32000), 256000)),
            required_capabilities=tuple(row.get("requiredCapabilities") or ["chat"]),
            preferred_route_ids=tuple(row.get("preferredRouteIds") or [])[:64],
            route_weights_ppm={
                str(key): max(0, min(int(weight), 1_000_000))
                for key, weight in dict(weights).items()
                if str(key) and int(weight) > 0
            },
            structured_repair_attempts=max(0, min(int(row.get("structuredRepairAttempts") or 1), 3)),
            semantic_cache_enabled=bool(row.get("semanticCacheEnabled", False)),
            revision=max(1, int(row.get("revision") or 1)),
        )


@dataclass(frozen=True, slots=True)
class RevolverAttempt:
    route: Mapping[str, Any]
    number: int
    outcome: str
    latency_ms: int
    payload: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    blocker: str = ""
    schema_valid: bool | None = None


@dataclass(frozen=True, slots=True)
class RevolverResult:
    response: Mapping[str, Any]
    selected_route: Mapping[str, Any]
    attempts: tuple[RevolverAttempt, ...]
    request_id: str
    mode: str


def _route_id(route: Mapping[str, Any]) -> str:
    return str(route.get("id") or "")


def _model_id(route: Mapping[str, Any]) -> str:
    return str(route.get("model_id") or route.get("modelId") or "")


def _config(route: Mapping[str, Any]) -> dict[str, Any]:
    value = route.get("config")
    return dict(value) if isinstance(value, Mapping) else {}


def eligible_free_routes(routes: Iterable[Mapping[str, Any]], capabilities: Iterable[str]) -> list[dict[str, Any]]:
    required = {str(item).lower() for item in capabilities if str(item)}
    result = []
    for source in routes:
        route = dict(source)
        config = _config(route)
        route_capabilities = {str(item).lower() for item in config.get("capabilities", ["chat"])}
        transport = str(
            route.get("runtime_kind")
            or route.get("runtimeKind")
            or config.get("transport")
            or route.get("provider")
            or ""
        ).strip().lower()
        if route.get("disabled") or transport != "freellm":
            continue
        if str(config.get("billingCategory") or config.get("billingClass") or "") != "free":
            continue
        if str(config.get("fundingMode") or "") != "verified_zero_cost":
            continue
        if str(config.get("executionProfile") or "") != "free_single_agent":
            continue
        if not config.get("pricingVerified") or not config.get("canaryVerified"):
            continue
        if not required.issubset(route_capabilities):
            continue
        result.append(route)
    return result


def plan_routes(routes: Iterable[Mapping[str, Any]], profile: RevolverProfile, request_id: str) -> list[dict[str, Any]]:
    planned = eligible_free_routes(routes, profile.required_capabilities)
    preferred = {value: index for index, value in enumerate(profile.preferred_route_ids)}
    planned.sort(key=lambda route: (
        preferred.get(_route_id(route), len(preferred)),
        int(route.get("priority") or 0),
        _model_id(route).casefold(),
    ))
    if profile.mode == "weighted" and planned:
        weights = [max(0, int(profile.route_weights_ppm.get(_route_id(route), 0))) for route in planned]
        total = sum(weights)
        if total:
            point = int.from_bytes(
                hashlib.sha256(f"{request_id}:{profile.revision}".encode()).digest()[:8], "big"
            ) % total
            cursor = 0
            selected = planned[0]
            for route, weight in zip(planned, weights):
                cursor += weight
                if point < cursor:
                    selected = route
                    break
            planned = [selected, *[route for route in planned if _route_id(route) != _route_id(selected)]]
    return planned


def validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    expected = schema.get("type")
    checks = {
        "object": lambda item: isinstance(item, dict), "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str), "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool), "null": lambda item: item is None,
    }
    if expected in checks and not checks[expected](value):
        return [f"{path}: expected {expected}"]
    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: enum mismatch")
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), Mapping) else {}
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        for key, item in value.items():
            if isinstance(properties.get(key), Mapping):
                errors.extend(validate_schema(item, properties[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: additional property")
    if isinstance(value, list) and isinstance(schema.get("items"), Mapping):
        for index, item in enumerate(value[:1000]):
            errors.extend(validate_schema(item, schema["items"], f"{path}[{index}]"))
    return errors[:100]


class Revolver:
    def __init__(self, call: Callable[[Mapping[str, Any], Mapping[str, Any], float], tuple[Any, Mapping[str, Any], str]], record: Callable[[RevolverAttempt, str, RevolverProfile], None] | None = None):
        self.call, self.record = call, record

    def _attempt(self, route: Mapping[str, Any], payload: Mapping[str, Any], number: int, profile: RevolverProfile, schema: Mapping[str, Any] | None = None) -> RevolverAttempt:
        started = time.monotonic()
        response, evidence, error = self.call(route, payload, profile.timeout_ms / 1000)
        data = response if isinstance(response, Mapping) else {}
        ok = bool(data) and not error
        schema_valid = None
        blocker = str(error or "")[:240]
        if ok and schema is not None:
            try:
                content = data["choices"][0]["message"]["content"]
                issues = validate_schema(json.loads(content), schema)
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                issues = ["$: invalid JSON"]
            schema_valid = not issues
            blocker = "; ".join(issues[:3])[:240]
        outcome = "success" if ok and schema_valid is not False else "schema_invalid" if ok else "failure"
        attempt = RevolverAttempt(route, number, outcome, int((time.monotonic()-started)*1000), data, dict(evidence), blocker, schema_valid)
        if self.record:
            self.record(attempt, str(payload.get("request_id") or ""), profile)
        return attempt

    def chat(self, messages: Sequence[Mapping[str, Any]], routes: Iterable[Mapping[str, Any]], profile: RevolverProfile, request_id: str = "", max_tokens: int = 1000, schema: Mapping[str, Any] | None = None) -> RevolverResult:
        rid = request_id or str(uuid.uuid4())
        planned = plan_routes(routes, profile, rid)
        if not planned:
            raise RevolverExhausted("no verified free route")
        payload_base = {"messages": list(messages), "max_tokens": max(1, min(int(max_tokens), 32000)), "stream": False, "request_id": rid}
        attempts: list[RevolverAttempt] = []
        if profile.mode != "race":
            for number, route in enumerate(planned, 1):
                attempt = self._attempt(route, {**payload_base, "model": _model_id(route)}, number, profile, schema)
                attempts.append(attempt)
                if attempt.outcome == "success":
                    return RevolverResult(attempt.payload, route, tuple(attempts), rid, profile.mode)
            raise RevolverExhausted(attempts[-1].blocker or "free routes exhausted")
        selected = planned[:profile.race_n]
        executor = ThreadPoolExecutor(max_workers=len(selected), thread_name_prefix="free-revolver-v3")
        futures = {
            executor.submit(self._attempt, route, {**payload_base, "model": _model_id(route)}, number, profile, schema): route
            for number, route in enumerate(selected, 1)
        }
        try:
            pending = set(futures)
            deadline = time.monotonic() + profile.timeout_ms / 1000
            while pending and time.monotonic() < deadline:
                done, pending = wait(pending, timeout=max(0, deadline-time.monotonic()), return_when=FIRST_COMPLETED)
                for future in done:
                    attempt = future.result()
                    attempts.append(attempt)
                    if attempt.outcome == "success":
                        for loser in pending:
                            loser.cancel()
                        return RevolverResult(attempt.payload, attempt.route, tuple(attempts), rid, "race")
            raise RevolverExhausted("race produced no valid response")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

