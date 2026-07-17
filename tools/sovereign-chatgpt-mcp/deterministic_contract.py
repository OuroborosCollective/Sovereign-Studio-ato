from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping


KAPPA_SCALE = 1_000_000
MAX_CANONICAL_BYTES = 250_000
MAX_REPLAY_ACTIONS = 100
_STATE_METADATA_FIELDS = frozenset({
    "stateHash", "actionHash", "chainHash", "previousChainHash",
})


def canonical_decimal_to_units(value: str, *, signed: bool = True) -> int:
    raw = unicodedata.normalize("NFC", str(value or "").strip())
    if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", raw):
        raise ValueError("value must be canonical decimal text")
    try:
        decimal_value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("value must be canonical decimal text") from exc
    if not signed and decimal_value < 0:
        raise ValueError("negative values are not allowed")
    scaled = decimal_value * Decimal(KAPPA_SCALE)
    return int(scaled.to_integral_value(rounding="ROUND_DOWN"))


def trunc_div_toward_zero(numerator: int, denominator: int) -> int:
    if denominator == 0:
        raise ZeroDivisionError("division by zero")
    quotient = abs(numerator) // abs(denominator)
    return -quotient if (numerator < 0) ^ (denominator < 0) else quotient


def multiply_fixed(left: int, right: int) -> int:
    return trunc_div_toward_zero(left * right, KAPPA_SCALE)


def divide_fixed(left: int, right: int) -> int:
    return trunc_div_toward_zero(left * KAPPA_SCALE, right)


def _canonical_value(value: Any, *, path: str = "$") -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise TypeError(
            f"{path} contains a float; use scaled integers or canonical decimal text"
        )
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise TypeError(f"{path} contains a non-string mapping key")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError(
                    f"{path} contains duplicate keys after Unicode normalization"
                )
            normalized[normalized_key] = _canonical_value(
                value[key], path=f"{path}.{normalized_key}"
            )
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _canonical_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{path} contains unsupported type {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    normalized = _canonical_value(value)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(payload) > MAX_CANONICAL_BYTES:
        raise ValueError("canonical payload exceeds the bounded size limit")
    return payload


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def state_sha256(value: Mapping[str, Any]) -> str:
    normalized = _canonical_value(value)
    if not isinstance(normalized, dict):
        raise TypeError("state must be a mapping")
    payload = {
        key: item
        for key, item in normalized.items()
        if key not in _STATE_METADATA_FIELDS
    }
    return canonical_sha256(payload)


def normalize_transition_table(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("transition_table must be a non-empty mapping")
    output: dict[str, dict[str, str]] = {}
    for raw_state, raw_actions in value.items():
        if not isinstance(raw_state, str) or not raw_state.strip():
            raise ValueError("transition state names must be non-empty strings")
        if not isinstance(raw_actions, Mapping) or not raw_actions:
            raise ValueError("each transition state must contain action mappings")
        state = unicodedata.normalize("NFC", raw_state.strip())
        actions: dict[str, str] = {}
        for raw_action, raw_target in raw_actions.items():
            if not isinstance(raw_action, str) or not raw_action.strip():
                raise ValueError("transition action names must be non-empty strings")
            if not isinstance(raw_target, str) or not raw_target.strip():
                raise ValueError("transition targets must be non-empty strings")
            action = unicodedata.normalize("NFC", raw_action.strip())
            target = unicodedata.normalize("NFC", raw_target.strip())
            actions[action] = target
        output[state] = dict(sorted(actions.items()))
    return dict(sorted(output.items()))


def transition_preview(
    current_state: Mapping[str, Any],
    action: Mapping[str, Any],
    transition_table: Mapping[str, Any],
    *,
    expected_version: int | None = None,
    expected_state_hash: str = "",
    engine_version: str = "are-v1",
) -> dict[str, Any]:
    state = _canonical_value(current_state)
    selected_action = _canonical_value(action)
    table = normalize_transition_table(transition_table)
    if not isinstance(state, dict) or not isinstance(selected_action, dict):
        raise TypeError("current_state and action must be mappings")

    current_status = state.get("status")
    action_type = selected_action.get("type")
    if not isinstance(current_status, str) or not current_status:
        raise ValueError("current_state.status is required")
    if not isinstance(action_type, str) or not action_type:
        raise ValueError("action.type is required")

    current_version = state.get("version", 0)
    if (
        not isinstance(current_version, int)
        or isinstance(current_version, bool)
        or current_version < 0
    ):
        raise ValueError("current_state.version must be a non-negative integer")

    current_hash = state_sha256(state)
    if expected_version is not None and current_version != expected_version:
        return {
            "ok": False,
            "allowed": False,
            "status": "VERSION_CONFLICT",
            "currentVersion": current_version,
            "expectedVersion": expected_version,
            "currentStateHash": current_hash,
            "mutationPerformed": False,
        }
    if expected_state_hash and current_hash != expected_state_hash:
        return {
            "ok": False,
            "allowed": False,
            "status": "STATE_HASH_CONFLICT",
            "currentStateHash": current_hash,
            "expectedStateHash": expected_state_hash,
            "mutationPerformed": False,
        }

    target = table.get(current_status, {}).get(action_type)
    if target is None:
        return {
            "ok": False,
            "allowed": False,
            "status": "TRANSITION_NOT_ALLOWED",
            "currentStatus": current_status,
            "actionType": action_type,
            "allowedActions": sorted(table.get(current_status, {})),
            "currentStateHash": current_hash,
            "mutationPerformed": False,
        }

    requested_target = selected_action.get("targetStatus")
    if requested_target is not None and requested_target != target:
        return {
            "ok": False,
            "allowed": False,
            "status": "TARGET_STATUS_MISMATCH",
            "currentStatus": current_status,
            "actionType": action_type,
            "contractTargetStatus": target,
            "requestedTargetStatus": requested_target,
            "currentStateHash": current_hash,
            "mutationPerformed": False,
        }

    patch = selected_action.get("patch", {})
    if not isinstance(patch, dict):
        raise ValueError("action.patch must be a mapping when supplied")
    protected = {
        "status",
        "version",
        "stateHash",
        "actionHash",
        "chainHash",
        "previousChainHash",
    }
    forbidden = sorted(protected.intersection(patch))
    if forbidden:
        raise ValueError(
            f"action.patch contains protected fields: {', '.join(forbidden)}"
        )

    next_state = deepcopy(state)
    for metadata_field in _STATE_METADATA_FIELDS:
        next_state.pop(metadata_field, None)
    for key in sorted(patch):
        next_state[key] = patch[key]
    next_state["status"] = target
    next_state["version"] = current_version + 1

    action_hash = canonical_sha256(selected_action)
    state_hash = state_sha256(next_state)
    previous_chain_hash = str(state.get("chainHash") or "")
    chain_material = {
        "schemaVersion": "sovereign.are-chain.v1",
        "engineVersion": unicodedata.normalize(
            "NFC", engine_version.strip() or "are-v1"
        ),
        "sequence": next_state["version"],
        "previousChainHash": previous_chain_hash,
        "actionHash": action_hash,
        "stateHash": state_hash,
    }
    chain_hash = canonical_sha256(chain_material)

    return {
        "ok": True,
        "allowed": True,
        "status": "TRANSITION_VALIDATED",
        "currentStatus": current_status,
        "nextStatus": target,
        "currentVersion": current_version,
        "nextVersion": next_state["version"],
        "currentStateHash": current_hash,
        "actionHash": action_hash,
        "nextStateHash": state_hash,
        "previousChainHash": previous_chain_hash,
        "chainHash": chain_hash,
        "stateHashContract": "canonical-state-without-chain-metadata",
        "nextState": next_state,
        "mutationPerformed": False,
        "truthNotice": (
            "Pure transition preview only; persistence, effects and runtime success "
            "are not claimed."
        ),
    }


def replay_verify(
    initial_state: Mapping[str, Any],
    actions: list[dict[str, Any]],
    transition_table: Mapping[str, Any],
    *,
    expected_final_state_hash: str = "",
    engine_version: str = "are-v1",
) -> dict[str, Any]:
    if not isinstance(actions, list):
        raise ValueError("actions must be a list")
    if len(actions) > MAX_REPLAY_ACTIONS:
        raise ValueError(
            f"actions exceed the bounded limit of {MAX_REPLAY_ACTIONS}"
        )
    state = _canonical_value(initial_state)
    if not isinstance(state, dict):
        raise ValueError("initial_state must be a mapping")

    steps: list[dict[str, Any]] = []
    for index, action in enumerate(actions, 1):
        result = transition_preview(
            state,
            action,
            transition_table,
            expected_version=state.get("version", 0),
            expected_state_hash=state_sha256(state),
            engine_version=engine_version,
        )
        steps.append(
            {
                "index": index,
                "allowed": bool(result.get("allowed")),
                "status": result.get("status"),
                "actionHash": result.get("actionHash"),
                "stateHash": result.get("nextStateHash"),
                "chainHash": result.get("chainHash"),
            }
        )
        if not result.get("allowed"):
            return {
                "ok": False,
                "status": "REPLAY_BLOCKED",
                "failedStep": index,
                "steps": steps,
                "finalState": state,
                "finalStateHash": state_sha256(state),
                "finalChainHash": state.get("chainHash") or None,
                "stateHashContract": "canonical-state-without-chain-metadata",
                "mutationPerformed": False,
                "crossRuntimeParityProven": False,
            }
        state = result["nextState"]
        state["chainHash"] = result["chainHash"]

    final_hash = state_sha256(state)
    matches = not expected_final_state_hash or final_hash == expected_final_state_hash
    return {
        "ok": matches,
        "status": "REPLAY_VERIFIED" if matches else "FINAL_STATE_HASH_MISMATCH",
        "steps": steps,
        "finalState": state,
        "finalStateHash": final_hash,
        "finalChainHash": state.get("chainHash") or None,
        "stateHashContract": "canonical-state-without-chain-metadata",
        "expectedFinalStateHash": expected_final_state_hash or None,
        "mutationPerformed": False,
        "crossRuntimeParityProven": False,
        "truthNotice": (
            "Python reference replay only. TypeScript/Python bit parity requires "
            "an independent TypeScript run over the same canonical vectors."
        ),
    }
