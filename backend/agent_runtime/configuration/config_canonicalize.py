"""Configuration Provenance - canonicalization & merge semantics.

Mirrors ``src/runtime/config/configCanonicalize.ts``. Deterministic
serialization (sorted keys, stable output) and fixed merge semantics:

  - Object: deep-merge recursively.
  - Array: replace wholesale.
  - null: explicit delete (removes the key).
  - missing/undefined: do not touch the resolved value.
  - RedactedSecret: carried through as a redacted identity.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .config_sources import RedactedSecret


def is_redacted_secret(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return value.get("kind") == "secret" and isinstance(value.get("redactedId"), str)


def _is_plain_object(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if is_redacted_secret(value):
        return False
    return True


def canonical_json(value: Any) -> str:
    return _serialize_stable(value)


def _serialize_stable(value: Any) -> str:
    # NOTE: serialization rules are mirrored byte-for-byte from the TypeScript
    # ``configCanonicalize.ts`` so that identical input yields identical
    # sha256 hashes across both runtimes (cross-language provenance parity).
    if value is None:
        return "null"
    if isinstance(value, str):
        # ensure_ascii=True matches JS JSON.stringify default (escapes non-ASCII).
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value) if math.isfinite(value) else "null"
    if isinstance(value, RedactedSecret):
        return '{"kind":"secret","redactedId":' + json.dumps(value.redacted_id, ensure_ascii=True) + '}'
    if is_redacted_secret(value):
        return '{"kind":"secret","redactedId":' + json.dumps(value["redactedId"], ensure_ascii=True) + '}'
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_serialize_stable(v) for v in value) + "]"
    if isinstance(value, dict):
        parts = []
        for key in sorted(value.keys()):
            # Python has no `undefined`; None serializes as "null" (matching
            # the TS treatment of null). Keys are JSON-encoded with the same
            # ensure_ascii rule as JS JSON.stringify.
            parts.append(json.dumps(key, ensure_ascii=True) + ":" + _serialize_stable(value[key]))
        return "{" + ",".join(parts) + "}"
    return "null"


def merge_values(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = dict(base)
    for key, overlay_value in overlay.items():
        if overlay_value is None:
            # Explicit delete.
            result.pop(key, None)
            continue
        base_value = result.get(key)
        if (
            _is_plain_object(base_value)
            and _is_plain_object(overlay_value)
        ):
            result[key] = merge_values(
                base_value, overlay_value
            )
        else:
            result[key] = overlay_value
    return result


def _short_hash(input_str: str) -> str:
    h1 = 0x811C9DC5
    h2 = 0x1000193
    for ch in input_str:
        c = ord(ch)
        h1 = (h1 ^ c) * 0x01000193 & 0xFFFFFFFF
        h2 = (h2 ^ (c + 0x9E3779B9)) * 0x85EBCA6B & 0xFFFFFFFF
    return f"{h1:08x}{h2:08x}"


_STABLE_HASH_PREFIX = "sch-"


def schema_hash_from_fields(fields: list[dict[str, str]]) -> str:
    sorted_fields = sorted(fields, key=lambda f: f["name"])
    serialized = "|".join(f"{f['name']}:{f['kind']}" for f in sorted_fields)
    return _STABLE_HASH_PREFIX + _short_hash(serialized)


def hash_value(value: Any) -> str:
    data = canonical_json(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_string(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "is_redacted_secret",
    "canonical_json",
    "merge_values",
    "schema_hash_from_fields",
    "hash_value",
    "hash_string",
]
