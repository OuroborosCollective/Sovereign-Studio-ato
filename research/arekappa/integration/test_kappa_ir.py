from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).with_name("kappa_ir.py")
SPEC = importlib.util.spec_from_file_location("arekappa_kappa_ir", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_largest_remainder_matches_wolfram_reference_vector() -> None:
    normalized = MODULE.normalize_weights_largest_remainder((17, 11, 23, 19, 13, 29))
    assert normalized == (151786, 98214, 205357, 169643, 116071, 258929)
    assert sum(normalized) == MODULE.KAPPA_SCALE


def test_ties_are_resolved_by_ascending_index() -> None:
    assert MODULE.normalize_weights_largest_remainder((1, 1, 1), 2) == (1, 1, 0)


def test_matrix_vector_product_preserves_extended_product_space() -> None:
    matrix = ((1_000_000, 0), (250_000, 750_000))
    vector = (400_000, 600_000)
    assert MODULE.matrix_vector_product(matrix, vector) == (400_000_000_000, 550_000_000_000)


def test_canonical_json_is_ordered_unicode_normalized_and_float_free() -> None:
    left = {"z": [2, 1], "a": "e\u0301"}
    right = {"a": "é", "z": [2, 1]}
    assert MODULE.canonical_json_bytes(left) == MODULE.canonical_json_bytes(right)
    assert MODULE.canonical_sha256(left) == MODULE.canonical_sha256(right)
    with pytest.raises(ValueError, match="floats are forbidden"):
        MODULE.canonical_json_bytes({"value": 0.5})


def test_invalid_weight_boundaries_fail_closed() -> None:
    for weights in ((), (0, 0), (1, -1), (True, 1)):
        with pytest.raises(ValueError):
            MODULE.normalize_weights_largest_remainder(weights)
