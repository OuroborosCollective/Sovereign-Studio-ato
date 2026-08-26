"""Persistent one-request-per-model OpenRouter census evidence.

This module never reads the protected OpenRouter key itself.  The existing
OpenRouter provider runtime owns that boundary and passes a protected value only
to the background census thread.  Raw provider output and raw error bodies are
never written to disk: only bounded metadata and SHA-256 digests are persisted.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

import requests


SCHEMA_VERSION = "sovereign.openrouter-model-census.v1"
TOOL_NAME = "census_ok"
PROMPT = "Call census_ok exactly once with value OK. Do not disclose credentials."
DEFAULT_MAX_OUTPUT_TOKENS = 64
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_PARALLELISM = 4
MAX_PARALLELISM = 4
MAX_MODELS = 700
ALLOWED_CLASSIFICATIONS = frozenset(
    {
        "OBSERVED",
        "BUDGET_EXHAUSTED",
        "OBSERVED_NONCONFORMANT",
        "NO_VISIBLE_OUTPUT",
        "REJECTED",
        "TIMEOUT",
        "UPSTREAM_ERROR",
        "INVALID_RESPONSE",
        "CLIENT_ERROR",
        "INTERRUPTED_UNKNOWN",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHECKPOINT_LOCK = threading.Lock()


class CensusError(RuntimeError):
    def __init__(self, family: str, *, status_code: int = 500) -> None:
        super().__init__(family)
        self.family = str(family)[:120]
        self.status_code = int(status_code)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bounded_nonnegative_int(value: Any) -> int:
    if value in (None, "") or isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, parsed)


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _safe_error_token(value: Any) -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return token[:60]


def _bounded_json_response(response: requests.Response, *, limit: int = 1_000_000) -> dict[str, Any]:
    content_length = _bounded_nonnegative_int(response.headers.get("Content-Length"))
    if content_length > limit:
        raise CensusError("openrouter_census_response_too_large")
    raw = response.raw.read(limit + 1, decode_content=True)
    if len(raw) > limit:
        raise CensusError("openrouter_census_response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CensusError("openrouter_census_response_invalid_json") from exc
    if not isinstance(payload, dict):
        raise CensusError("openrouter_census_response_invalid_shape")
    return payload


def _http_failure_family(status: int) -> str:
    if status in {401, 403}:
        return "openrouter_credentials_rejected"
    if status == 402:
        return "openrouter_account_credits_required"
    if status == 404:
        return "openrouter_no_provider_meets_policy"
    if status == 408:
        return "openrouter_timeout"
    if status == 429:
        return "openrouter_rate_limited"
    if status in {502, 503, 504}:
        return "openrouter_provider_unavailable"
    if status == 400:
        return "openrouter_invalid_request"
    return f"openrouter_provider_http_{status}"[:120]


def _usage(payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    prompt_details = (
        usage.get("prompt_tokens_details")
        if isinstance(usage.get("prompt_tokens_details"), dict)
        else {}
    )
    completion_details = (
        usage.get("completion_tokens_details")
        if isinstance(usage.get("completion_tokens_details"), dict)
        else {}
    )
    cost = _decimal(usage.get("cost"))
    return {
        "promptTokens": _bounded_nonnegative_int(usage.get("prompt_tokens")),
        "cachedPromptTokens": _bounded_nonnegative_int(prompt_details.get("cached_tokens")),
        "completionTokens": _bounded_nonnegative_int(usage.get("completion_tokens")),
        "reasoningTokens": _bounded_nonnegative_int(completion_details.get("reasoning_tokens")),
        "totalTokens": _bounded_nonnegative_int(usage.get("total_tokens")),
        "providerCostUsd": format(cost.normalize(), "f") if cost is not None else None,
    }


def _output_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    finish_reason = str(choice.get("finish_reason") or "")[:80] or None
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []

    expected_tool_present = False
    tool_call_match = False
    arguments_sha256 = None
    for call in tool_calls:
        function = (
            call.get("function")
            if isinstance(call, dict) and isinstance(call.get("function"), dict)
            else {}
        )
        if str(function.get("name") or "") != TOOL_NAME:
            continue
        expected_tool_present = True
        raw_arguments = function.get("arguments")
        if isinstance(raw_arguments, str):
            arguments_sha256 = hashlib.sha256(raw_arguments.encode("utf-8")).hexdigest()
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = None
        elif isinstance(raw_arguments, dict):
            arguments_sha256 = canonical_sha256(raw_arguments)
            arguments = raw_arguments
        else:
            arguments = None
        tool_call_match = bool(
            isinstance(arguments, dict)
            and arguments.get("value") == "OK"
            and set(arguments) == {"value"}
        )
        break

    content = message.get("content")
    content_present = content not in (None, "", [])
    if isinstance(content, str):
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    elif content_present:
        content_sha256 = canonical_sha256(content)
    else:
        content_sha256 = None

    shape = {
        "toolCallCount": len(tool_calls),
        "expectedToolPresent": expected_tool_present,
        "toolCallMatch": tool_call_match,
        "argumentsSha256": arguments_sha256,
        "contentPresent": content_present,
        "contentSha256": content_sha256,
        "finishReason": finish_reason,
    }
    if tool_call_match:
        classification = "OBSERVED"
    elif finish_reason == "length":
        classification = "BUDGET_EXHAUSTED"
    elif content_present or tool_calls:
        classification = "OBSERVED_NONCONFORMANT"
    else:
        classification = "NO_VISIBLE_OUTPUT"
    return {
        **shape,
        "classification": classification,
        "outputSha256": canonical_sha256(shape),
    }


def request_body(
    *,
    model_id: str,
    provider_policy: dict[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model_id,
        "messages": [{"role": "user", "content": PROMPT}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": "Return one bounded route-execution census marker.",
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "string", "enum": ["OK"]}},
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": TOOL_NAME}},
        "max_tokens": int(max_output_tokens),
        "provider": dict(provider_policy),
        "stream": False,
    }


def _base_result(
    model_id: str,
    *,
    classification: str,
    input_sha256: str,
    latency_ms: int,
    failure_family: str | None = None,
    http_status: int | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "modelId": model_id,
        "classification": classification,
        "failureFamily": failure_family,
        "httpStatus": http_status,
        "latencyMs": max(0, int(latency_ms)),
        "requestId": request_id,
        "resolvedModel": None,
        "modelIdentityMatch": None,
        "provider": None,
        "finishReason": None,
        "toolCallCount": 0,
        "expectedToolPresent": False,
        "toolCallMatch": False,
        "argumentsSha256": None,
        "contentPresent": False,
        "contentSha256": None,
        "outputSha256": None,
        "inputSha256": input_sha256,
        "usage": {
            "promptTokens": 0,
            "cachedPromptTokens": 0,
            "completionTokens": 0,
            "reasoningTokens": 0,
            "totalTokens": 0,
            "providerCostUsd": None,
        },
        "requestCount": 1,
        "clientAutomaticRetries": 0,
        "automaticFallback": False,
        "truthVerdict": "NOT_ASSERTED",
        "rawResponsePersisted": False,
        "secretValuesReturned": False,
    }


def request_model_once(
    key: str,
    *,
    model_id: str,
    openrouter_base_url: str,
    request_headers: Callable[[str], dict[str, str]],
    provider_policy: dict[str, Any],
    max_output_tokens: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    body = request_body(
        model_id=model_id,
        provider_policy=provider_policy,
        max_output_tokens=max_output_tokens,
    )
    input_sha256 = canonical_sha256(body)
    endpoint = f"{openrouter_base_url.rstrip('/')}/chat/completions"
    started = time.monotonic()
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.post(
                endpoint,
                headers=request_headers(key),
                json=body,
                timeout=timeout_seconds,
                allow_redirects=False,
                stream=True,
            ) as response:
                latency_ms = int((time.monotonic() - started) * 1000)
                status = int(response.status_code)
                header_request_id = str(
                    response.headers.get("x-request-id")
                    or response.headers.get("X-Request-Id")
                    or ""
                )[:200]
                if status >= 400:
                    return _base_result(
                        model_id,
                        classification="REJECTED",
                        input_sha256=input_sha256,
                        latency_ms=latency_ms,
                        failure_family=_http_failure_family(status),
                        http_status=status,
                        request_id=header_request_id or None,
                    )
                payload = _bounded_json_response(response)
    except requests.Timeout:
        return _base_result(
            model_id,
            classification="TIMEOUT",
            input_sha256=input_sha256,
            latency_ms=int((time.monotonic() - started) * 1000),
            failure_family="openrouter_timeout",
        )
    except requests.RequestException:
        return _base_result(
            model_id,
            classification="UPSTREAM_ERROR",
            input_sha256=input_sha256,
            latency_ms=int((time.monotonic() - started) * 1000),
            failure_family="openrouter_upstream_unavailable",
        )
    except CensusError as exc:
        return _base_result(
            model_id,
            classification="INVALID_RESPONSE",
            input_sha256=input_sha256,
            latency_ms=int((time.monotonic() - started) * 1000),
            failure_family=exc.family,
            http_status=200,
        )
    except Exception as exc:
        return _base_result(
            model_id,
            classification="CLIENT_ERROR",
            input_sha256=input_sha256,
            latency_ms=int((time.monotonic() - started) * 1000),
            failure_family=(
                f"openrouter_census_{_safe_error_token(type(exc).__name__) or 'unknown'}"
            )[:120],
        )

    output = _output_evidence(payload)
    usage = _usage(payload)
    resolved_model = str(payload.get("model") or "")[:240] or None
    provider = str(payload.get("provider") or "")[:160] or None
    request_id = str(payload.get("id") or header_request_id or "")[:200] or None
    return {
        "modelId": model_id,
        "classification": output["classification"],
        "failureFamily": None,
        "httpStatus": 200,
        "latencyMs": latency_ms,
        "requestId": request_id,
        "resolvedModel": resolved_model,
        "modelIdentityMatch": (
            resolved_model == model_id if resolved_model is not None else None
        ),
        "provider": provider,
        "finishReason": output["finishReason"],
        "toolCallCount": output["toolCallCount"],
        "expectedToolPresent": output["expectedToolPresent"],
        "toolCallMatch": output["toolCallMatch"],
        "argumentsSha256": output["argumentsSha256"],
        "contentPresent": output["contentPresent"],
        "contentSha256": output["contentSha256"],
        "outputSha256": output["outputSha256"],
        "inputSha256": input_sha256,
        "usage": usage,
        "requestCount": 1,
        "clientAutomaticRetries": 0,
        "automaticFallback": False,
        "truthVerdict": "NOT_ASSERTED",
        "rawResponsePersisted": False,
        "secretValuesReturned": False,
    }


def catalog_snapshot(
    query: Callable[..., Any],
    *,
    model_id_pattern: re.Pattern[str],
) -> tuple[list[dict[str, Any]], str, str]:
    rows = query(
        """SELECT id::text, model_name, priority, config
           FROM llm_routes
           WHERE disabled=false
             AND lower(COALESCE(runtime_kind, provider))='openrouter'
             AND COALESCE((config->>'selectable')::boolean, false)=true
             AND COALESCE(config->>'billingCategory', '') IN ('standard','premium')
           ORDER BY priority ASC, model_name ASC"""
    ) or []
    if len(rows) > MAX_MODELS:
        raise CensusError("openrouter_census_catalog_too_large", status_code=409)

    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    snapshot_hashes: set[str] = set()
    for row in rows:
        config = row.get("config") if isinstance(row.get("config"), dict) else {}
        model_id = str(config.get("providerModel") or "").strip()
        payload_hash = str(config.get("catalogPayloadSha256") or "").strip().lower()
        snapshot_hash = str(config.get("catalogSnapshotSha256") or "").strip().lower()
        if not model_id_pattern.fullmatch(model_id):
            raise CensusError("openrouter_census_model_identity_invalid", status_code=409)
        if model_id in seen:
            raise CensusError("openrouter_census_duplicate_model", status_code=409)
        if not _SHA256_RE.fullmatch(payload_hash):
            raise CensusError(
                "openrouter_census_catalog_payload_hash_missing", status_code=409
            )
        if not _SHA256_RE.fullmatch(snapshot_hash):
            raise CensusError(
                "openrouter_census_catalog_snapshot_hash_missing", status_code=409
            )
        seen.add(model_id)
        snapshot_hashes.add(snapshot_hash)
        models.append(
            {
                "routeId": str(row.get("id") or "")[:160],
                "modelId": model_id,
                "displayName": str(row.get("model_name") or model_id)[:180],
                "priority": _bounded_nonnegative_int(row.get("priority")),
                "catalogPayloadSha256": payload_hash,
            }
        )
    if not models:
        raise CensusError("openrouter_census_catalog_empty", status_code=409)
    if len(snapshot_hashes) != 1:
        raise CensusError("openrouter_census_catalog_identity_drift", status_code=409)

    model_set_sha256 = canonical_sha256(
        [
            {
                "routeId": model["routeId"],
                "modelId": model["modelId"],
                "catalogPayloadSha256": model["catalogPayloadSha256"],
            }
            for model in models
        ]
    )
    return models, next(iter(snapshot_hashes)), model_set_sha256


def operation_id(
    *,
    source_revision: str,
    image_digest: str,
    catalog_snapshot_sha256: str,
    model_set_sha256: str,
    expected_models: int,
) -> str:
    if not _REVISION_RE.fullmatch(source_revision):
        raise CensusError("openrouter_census_runtime_revision_invalid", status_code=409)
    if not _IMAGE_RE.fullmatch(image_digest):
        raise CensusError("openrouter_census_runtime_image_digest_invalid", status_code=409)
    return canonical_sha256(
        {
            "sourceRevision": source_revision,
            "imageDigest": image_digest,
            "catalogSnapshotSha256": catalog_snapshot_sha256,
            "modelSetSha256": model_set_sha256,
            "expectedModels": int(expected_models),
        }
    )


def evidence_paths(owner_root: Path, operation: str) -> dict[str, Path]:
    if not _SHA256_RE.fullmatch(operation):
        raise CensusError("openrouter_census_operation_id_invalid", status_code=500)
    root = owner_root.resolve()
    directory = (root / "openrouter-census-evidence").resolve()
    if directory.parent != root:
        raise CensusError("openrouter_census_evidence_path_invalid", status_code=500)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return {
        "directory": directory,
        "lock": directory / f"{operation}.lock",
        "state": directory / f"{operation}.state.json",
        "checkpoint": directory / f"{operation}.checkpoint.jsonl",
        "receipt": directory / f"{operation}.receipt.json",
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_state(path: Path, payload: dict[str, Any]) -> None:
    bounded = {
        **payload,
        "updatedAt": utc_now(),
        "secretValuesReturned": False,
    }
    _write_json_atomic(path, bounded)


def read_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CensusError("openrouter_census_state_corrupt") from exc
    if not isinstance(payload, dict):
        raise CensusError("openrouter_census_state_corrupt")
    return payload


def latest_state(owner_root: Path) -> dict[str, Any] | None:
    directory = (owner_root.resolve() / "openrouter-census-evidence").resolve()
    if not directory.is_dir() or directory.parent != owner_root.resolve():
        return None
    candidates = sorted(
        directory.glob("*.state.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:16]
    for path in candidates:
        try:
            state = read_state(path)
        except CensusError:
            continue
        if isinstance(state, dict):
            return state
    return None


def _event_hash(event: dict[str, Any]) -> str:
    return canonical_sha256(event)


def _append_checkpoint(path: Path, event: dict[str, Any]) -> None:
    base = dict(event)
    base["eventSha256"] = _event_hash(base)
    encoded = (json.dumps(base, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    with _CHECKPOINT_LOCK:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)


def _read_checkpoint(path: Path) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    attempted: dict[str, str] = {}
    results: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return attempted, results
    try:
        lines = path.read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise CensusError("openrouter_census_checkpoint_corrupt") from exc
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CensusError("openrouter_census_checkpoint_corrupt") from exc
        if not isinstance(event, dict):
            raise CensusError("openrouter_census_checkpoint_corrupt")
        event_sha = str(event.pop("eventSha256", ""))
        if not _SHA256_RE.fullmatch(event_sha) or canonical_sha256(event) != event_sha:
            raise CensusError("openrouter_census_checkpoint_hash_mismatch")
        event_type = str(event.get("type") or "")
        model_id = str(event.get("modelId") or "")
        if not model_id:
            raise CensusError("openrouter_census_checkpoint_corrupt")
        if event_type == "attempt":
            input_sha256 = str(event.get("inputSha256") or "")
            if not _SHA256_RE.fullmatch(input_sha256):
                raise CensusError("openrouter_census_checkpoint_corrupt")
            attempted[model_id] = input_sha256
        elif event_type == "result":
            result = event.get("result") if isinstance(event.get("result"), dict) else None
            if result is None or str(result.get("modelId") or "") != model_id:
                raise CensusError("openrouter_census_checkpoint_corrupt")
            results[model_id] = result
        else:
            raise CensusError("openrouter_census_checkpoint_corrupt")
    if not set(results).issubset(set(attempted)):
        raise CensusError("openrouter_census_checkpoint_order_invalid")
    return attempted, results


def _interrupted_result(model: dict[str, Any], input_sha256: str) -> dict[str, Any]:
    return {
        **_base_result(
            model["modelId"],
            classification="INTERRUPTED_UNKNOWN",
            input_sha256=input_sha256,
            latency_ms=0,
            failure_family="openrouter_census_interrupted_after_attempt_marker",
        ),
        "providerOutcomeObserved": False,
    }


def execute_census(
    *,
    key: str,
    models: list[dict[str, Any]],
    catalog_snapshot_sha256: str,
    model_set_sha256: str,
    source_revision: str,
    image_digest: str,
    operation: str,
    checkpoint_path: Path,
    receipt_path: Path,
    openrouter_base_url: str,
    request_headers: Callable[[str], dict[str, str]],
    provider_policy: dict[str, Any],
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    parallelism: int = DEFAULT_PARALLELISM,
) -> dict[str, Any]:
    if receipt_path.is_file():
        return load_receipt(receipt_path)
    if not 1 <= len(models) <= MAX_MODELS:
        raise CensusError("openrouter_census_model_count_invalid", status_code=409)
    if not 1 <= int(max_output_tokens) <= DEFAULT_MAX_OUTPUT_TOKENS:
        raise CensusError("openrouter_census_output_budget_invalid", status_code=400)
    if not 5 <= int(timeout_seconds) <= DEFAULT_TIMEOUT_SECONDS:
        raise CensusError("openrouter_census_timeout_budget_invalid", status_code=400)
    if not 1 <= int(parallelism) <= MAX_PARALLELISM:
        raise CensusError("openrouter_census_parallelism_invalid", status_code=400)

    expected_ids = [model["modelId"] for model in models]
    attempted, persisted_results = _read_checkpoint(checkpoint_path)
    if not set(attempted).issubset(set(expected_ids)) or not set(persisted_results).issubset(
        set(expected_ids)
    ):
        raise CensusError("openrouter_census_checkpoint_model_set_mismatch")

    # At-most-once recovery: if a previous process marked an attempt but crashed
    # before recording its result, do not send that model again.  Preserve the
    # uncertainty explicitly instead of silently duplicating a provider request.
    for model in models:
        model_id = model["modelId"]
        if model_id in attempted and model_id not in persisted_results:
            interrupted = {
                **model,
                **_interrupted_result(model, attempted[model_id]),
            }
            _append_checkpoint(
                checkpoint_path,
                {"type": "result", "modelId": model_id, "result": interrupted},
            )
            persisted_results[model_id] = interrupted

    pending_models = [model for model in models if model["modelId"] not in attempted]
    started_at = utc_now()
    start_monotonic = time.monotonic()
    pending_index = 0
    futures: dict[Any, dict[str, Any]] = {}

    def submit_next(executor: ThreadPoolExecutor) -> bool:
        nonlocal pending_index
        if pending_index >= len(pending_models):
            return False
        model = pending_models[pending_index]
        pending_index += 1
        model_id = model["modelId"]
        body = request_body(
            model_id=model_id,
            provider_policy=provider_policy,
            max_output_tokens=max_output_tokens,
        )
        _append_checkpoint(
            checkpoint_path,
            {
                "type": "attempt",
                "modelId": model_id,
                "inputSha256": canonical_sha256(body),
                "catalogPayloadSha256": model["catalogPayloadSha256"],
            },
        )
        attempted[model_id] = canonical_sha256(body)
        future = executor.submit(
            request_model_once,
            key,
            model_id=model_id,
            openrouter_base_url=openrouter_base_url,
            request_headers=request_headers,
            provider_policy=provider_policy,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        futures[future] = model
        return True

    with ThreadPoolExecutor(max_workers=int(parallelism)) as executor:
        for _ in range(min(int(parallelism), len(pending_models))):
            submit_next(executor)
        while futures:
            completed, _ = wait(set(futures), return_when=FIRST_COMPLETED)
            for future in completed:
                model = futures.pop(future)
                model_id = model["modelId"]
                try:
                    result = future.result()
                except Exception as exc:
                    result = _base_result(
                        model_id,
                        classification="CLIENT_ERROR",
                        input_sha256=canonical_sha256(
                            request_body(
                                model_id=model_id,
                                provider_policy=provider_policy,
                                max_output_tokens=max_output_tokens,
                            )
                        ),
                        latency_ms=0,
                        failure_family=(
                            f"openrouter_census_future_{_safe_error_token(type(exc).__name__) or 'unknown'}"
                        )[:120],
                    )
                combined = {**model, **result, "providerOutcomeObserved": True}
                _append_checkpoint(
                    checkpoint_path,
                    {"type": "result", "modelId": model_id, "result": combined},
                )
                persisted_results[model_id] = combined
                submit_next(executor)

    if set(persisted_results) != set(expected_ids):
        raise CensusError("openrouter_census_result_count_mismatch")
    ordered_results = [persisted_results[model_id] for model_id in expected_ids]
    if any(result.get("classification") not in ALLOWED_CLASSIFICATIONS for result in ordered_results):
        raise CensusError("openrouter_census_classification_invalid")

    classifications = Counter(str(result["classification"]) for result in ordered_results)
    interrupted_count = int(classifications.get("INTERRUPTED_UNKNOWN", 0))
    total_cost = Decimal(0)
    cost_observation_count = 0
    for result in ordered_results:
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        cost = _decimal(usage.get("providerCostUsd"))
        if cost is not None:
            total_cost += cost
            cost_observation_count += 1

    request_contract = {
        "promptSha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "toolName": TOOL_NAME,
        "maxOutputTokens": int(max_output_tokens),
        "timeoutSeconds": int(timeout_seconds),
        "parallelism": int(parallelism),
        "providerPolicy": dict(provider_policy),
        "clientAutomaticRetries": 0,
        "oneRequestPerModel": True,
        "recoveryPolicy": "never-retry-attempt-marked-model",
    }
    provider_http_response_count = sum(
        1 for result in ordered_results if result.get("httpStatus") is not None
    )
    receipt = {
        "schemaVersion": SCHEMA_VERSION,
        "recordType": "OPENROUTER_MODEL_CENSUS",
        "operationId": operation,
        "observedAt": started_at,
        "completedAt": utc_now(),
        "durationMs": int((time.monotonic() - start_monotonic) * 1000),
        "sourceRevision": source_revision,
        "imageDigest": image_digest,
        "providerSurface": "openrouter-direct-paid",
        "catalogSnapshotSha256": catalog_snapshot_sha256,
        "modelSetSha256": model_set_sha256,
        "catalogModelCount": len(models),
        "clientRequestAttempts": len(attempted),
        "oneRequestPerModelClientInvariantVerified": bool(
            len(attempted) == len(models)
            and all(result.get("requestCount") == 1 for result in ordered_results)
            and all(result.get("clientAutomaticRetries") == 0 for result in ordered_results)
            and all(result.get("automaticFallback") is False for result in ordered_results)
        ),
        "providerHttpResponsesObserved": provider_http_response_count,
        "allProviderHttpResponsesObserved": provider_http_response_count == len(models),
        "requestContract": request_contract,
        "requestContractSha256": canonical_sha256(request_contract),
        "providerPolicySha256": canonical_sha256(provider_policy),
        "automaticFallback": False,
        "clientAutomaticRetries": 0,
        "truthVerdict": "NOT_ASSERTED",
        "leaderboardEnabled": False,
        "semanticQualityClaimed": False,
        "rawResponsesPersisted": False,
        "secretValuesReturned": False,
        "summary": {
            "classificationCounts": dict(sorted(classifications.items())),
            "http200Count": sum(1 for result in ordered_results if result.get("httpStatus") == 200),
            "toolCallMatchCount": sum(
                1 for result in ordered_results if result.get("toolCallMatch") is True
            ),
            "providerHttpResponseObservedCount": provider_http_response_count,
            "interruptedUnknownCount": interrupted_count,
            "providerCostObservationCount": cost_observation_count,
            "observedProviderCostUsd": format(total_cost.normalize(), "f"),
        },
        "results": ordered_results,
    }
    receipt["receiptSha256"] = canonical_sha256(receipt)
    encoded = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    fd = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        receipt_path.unlink(missing_ok=True)
        raise
    return receipt


def load_receipt(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CensusError("openrouter_census_receipt_corrupt") from exc
    if not isinstance(payload, dict) or payload.get("schemaVersion") != SCHEMA_VERSION:
        raise CensusError("openrouter_census_receipt_schema_invalid")
    receipt_sha = str(payload.get("receiptSha256") or "")
    if not _SHA256_RE.fullmatch(receipt_sha):
        raise CensusError("openrouter_census_receipt_hash_invalid")
    canonical = dict(payload)
    canonical.pop("receiptSha256", None)
    if canonical_sha256(canonical) != receipt_sha:
        raise CensusError("openrouter_census_receipt_hash_mismatch")
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    if len(results) != int(payload.get("catalogModelCount") or -1):
        raise CensusError("openrouter_census_receipt_result_count_mismatch")
    return payload
