"""Pure, non-production AREKappa IR helpers.

This module has no network, database, clock, random, or filesystem effects.
It accepts exact scaled integers only and emits canonical JSON bytes.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping, Sequence
import unicodedata

KAPPA_SCALE = 1_000_000


def normalize_weights_largest_remainder(weights: Sequence[int], scale: int = KAPPA_SCALE) -> tuple[int, ...]:
    """Normalize non-negative integer weights to exactly ``scale`` units.

    Ties are resolved by ascending index. No floating-point operation is used.
    """
    if not isinstance(scale, int) or isinstance(scale, bool) or scale <= 0:
        raise ValueError("scale must be a positive integer")
    values = tuple(weights)
    if not values:
        raise ValueError("weights must not be empty")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
        raise ValueError("weights must contain non-negative integers only")
    total = sum(values)
    if total <= 0:
        raise ValueError("weight sum must be positive")

    numerators = tuple(value * scale for value in values)
    floors = [numerator // total for numerator in numerators]
    remaining = scale - sum(floors)
    order = sorted(range(len(values)), key=lambda index: (-(numerators[index] % total), index))
    for index in order[:remaining]:
        floors[index] += 1
    return tuple(floors)


def matrix_vector_product(matrix: Sequence[Sequence[int]], vector: Sequence[int]) -> tuple[int, ...]:
    rows = tuple(tuple(row) for row in matrix)
    values = tuple(vector)
    if not rows or not values or any(len(row) != len(values) for row in rows):
        raise ValueError("matrix and vector dimensions must be non-empty and compatible")
    if any(not isinstance(value, int) or isinstance(value, bool) for row in rows for value in row):
        raise ValueError("matrix values must be integers")
    if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
        raise ValueError("vector values must be integers")
    return tuple(sum(coefficient * value for coefficient, value in zip(row, values)) for row in rows)


def _normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise ValueError("floats are forbidden in canonical AREKappa JSON")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("canonical JSON object keys must be strings")
            normalized[unicodedata.normalize("NFC", key)] = _normalize_json(child)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json(child) for child in value]
    raise ValueError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    normalized = _normalize_json(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()
