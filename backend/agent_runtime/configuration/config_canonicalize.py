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
import re
from typing import Any

from .config_sources import RedactedSecret


# Property names that, when assigned dynamically, can hijack object or global
# prototypes. Such keys are never legitimate configuration field names; they
# are rejected in ``merge_values`` so a remote/user-provided source cannot use
# the merge path to pollute prototypes. Mirrors the TypeScript sanitizer in
# ``configCanonicalize.ts`` for cross-language provenance parity.
_PROTO_POLLUTION_KEYS = frozenset({"__proto__", "constructor", "prototype"})


def _is_proto_pollution_key(key: str) -> bool:
    return key in _PROTO_POLLUTION_KEYS


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


def _js_number_str(x: float) -> str:
    """Format a float exactly like JS ``Number.prototype.toString``.

    The TypeScript provenance canonicalizer uses ``String(value)`` (i.e. JS
    ``Number.prototype.toString`` per ECMA-262 6.1.6.1.20). Python's ``str``
    diverges for some floats (e.g. ``1.0`` -> ``"1.0"`` vs JS ``"1"``;
    ``1e20`` -> ``"1e+20"`` vs JS ``"100000000000000000000"``), which breaks
    cross-language provenance hash parity. This helper reproduces the JS
    algorithm from the shortest round-trip digits Python's ``repr`` yields,
    so identical input produces byte-identical canonical output in both
    runtimes. ``str(int)`` already matches JS, so this is only needed for floats.
    """
    if x != x:  # NaN
        return "null"
    if x == math.inf or x == -math.inf:
        return "null"
    if x == 0:  # also covers -0.0
        return "0"

    neg = x < 0
    if neg:
        x = -x

    # Shortest round-trip decimal representation (Python repr is shortest-form).
    r = repr(x)
    if "e" in r or "E" in r:
        mant, exp_s = re.split("[eE]", r)
        exp = int(exp_s)
    else:
        mant, exp = r, 0
    if "." in mant:
        int_part, frac_part = mant.split(".")
    else:
        int_part, frac_part = mant, ""
    digits = int_part + frac_part
    # n = position of the decimal point relative to the start of ``digits``.
    n = len(int_part) + exp
    k = len(digits)
    # Trim trailing zeros (they carry no value); fractional zeros reduce k only.
    s = digits
    trim = len(s) - len(s.rstrip("0"))
    if trim:
        s = s[:-trim]
        k -= trim
    if s == "":
        s = "0"
        k = 1

    # ECMA-262 6.1.6.1.20 number-to-string formatting (n is the decimal
    # exponent, k is the minimal digit count).
    if k <= n <= 21:
        out = s + "0" * (n - k)
    elif 0 < n <= 21:
        out = s[:n] + "." + s[n:]
    elif -6 < n <= 0:
        out = "0." + ("0" * (-n)) + s
    else:
        first = s[0]
        rest = s[1:]
        mantissa = first if rest == "" else first + "." + rest
        e = n - 1
        esign = "+" if e >= 0 else "-"
        out = mantissa + "e" + esign + str(abs(e))

    return ("-" + out) if neg else out


def canonical_json(value: Any) -> str:
    return _serialize_stable(value)


def _serialize_stable(value: Any) -> str:
    # NOTE: serialization rules are mirrored byte-for-byte from the TypeScript
    # ``configCanonicalize.ts`` so that identical input yields identical
    # sha256 hashes across both runtimes (cross-language provenance parity).
    if value is None:
        return "null"
    if isinstance(value, str):
        # JS JSON.stringify emits raw UTF-8 for non-ASCII strings.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _js_number_str(value) if math.isfinite(value) else "null"
    if isinstance(value, RedactedSecret):
        return '{"kind":"secret","redactedId":' + json.dumps(value.redacted_id, ensure_ascii=False) + '}'
    if is_redacted_secret(value):
        return '{"kind":"secret","redactedId":' + json.dumps(value["redactedId"], ensure_ascii=False) + '}'
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_serialize_stable(v) for v in value) + "]"
    if isinstance(value, dict):
        parts = []
        for key in sorted(value.keys()):
            # Python has no `undefined`; None serializes as "null" (matching
            # the TS treatment of null). Keys are JSON-encoded with the same
            # ensure_ascii=False matches JSON.stringify raw UTF-8 semantics.
            parts.append(json.dumps(key, ensure_ascii=False) + ":" + _serialize_stable(value[key]))
        return "{" + ",".join(parts) + "}"
    return "null"


def merge_values(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    base_keys = [k for k in base.keys() if not _is_proto_pollution_key(k)]
    overlay_keys = [k for k in overlay.keys() if not _is_proto_pollution_key(k)]
    # Ordered de-duplicated union of sanitized keys from both sides.
    result_keys = dict.fromkeys(base_keys + overlay_keys)

    entries: list[tuple[str, Any]] = []
    for key in result_keys:
        has_overlay = key in overlay
        if not has_overlay:
            # Not overridden: keep the resolved base value.
            entries.append((key, base[key]))
            continue
        overlay_value = overlay[key]
        # Explicit delete: None removes the key entirely (it is omitted from
        # the result, so ``key not in result``).
        if overlay_value is None:
            continue
        base_value = base.get(key)
        if (
            _is_plain_object(base_value)
            and _is_plain_object(overlay_value)
        ):
            entries.append((key, merge_values(base_value, overlay_value)))
        else:
            # Arrays, scalars, redacted secrets: replace wholesale.
            entries.append((key, overlay_value))
    return dict(entries)


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
