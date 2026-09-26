"""Bounded Wolfram CAG expressions for deterministic Bitcoin graph checks.

The graph remains the source of truth. Wolfram is a supplemental mathematical
counter-check over small integer observations derived from canonical records.
The expression builder is allow-listed and accepts no arbitrary code.

No credentials, raw prompts, tx bodies or wall-clock values are included.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any


class BitcoinWolframContractError(ValueError):
    """Raised when a Wolfram verification observation is invalid."""


class BitcoinCheck(str, Enum):
    FEE_CONSERVATION = "fee_conservation"
    EDGE_CHRONOLOGY = "edge_chronology"
    UNIQUE_SPEND = "unique_spend"
    VECTOR_DISTANCE = "vector_distance"


@dataclass(frozen=True, slots=True)
class FeeObservation:
    input_value_sat: int
    output_value_sat: int
    fee_sat: int

    def __post_init__(self) -> None:
        for name in ("input_value_sat", "output_value_sat", "fee_sat"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BitcoinWolframContractError(f"{name} must be a non-negative integer")
        if self.output_value_sat + self.fee_sat > self.input_value_sat:
            raise BitcoinWolframContractError("output + fee cannot exceed input")


@dataclass(frozen=True, slots=True)
class ChronologyObservation:
    created_height: int
    spend_height: int

    def __post_init__(self) -> None:
        for name in ("created_height", "spend_height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BitcoinWolframContractError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class UniqueSpendObservation:
    spend_count: int

    def __post_init__(self) -> None:
        if isinstance(self.spend_count, bool) or not isinstance(self.spend_count, int) or self.spend_count < 0:
            raise BitcoinWolframContractError("spend_count must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class VectorDistanceObservation:
    query: tuple[int, ...]
    candidate: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.query or len(self.query) != len(self.candidate):
            raise BitcoinWolframContractError("vectors must have equal non-zero dimension")
        if len(self.query) > 256:
            raise BitcoinWolframContractError("vector dimension exceeds safety bound")
        for value in (*self.query, *self.candidate):
            if isinstance(value, bool) or not isinstance(value, int):
                raise BitcoinWolframContractError("vector components must be integers")


def _wl_integer(value: int) -> str:
    return str(int(value))


def build_wolfram_expression(
    check: BitcoinCheck,
    observation: FeeObservation | ChronologyObservation | UniqueSpendObservation | VectorDistanceObservation,
) -> str:
    """Build one allow-listed Wolfram Language expression."""
    if check is BitcoinCheck.FEE_CONSERVATION and isinstance(observation, FeeObservation):
        return (
            "FullSimplify["
            f"{_wl_integer(observation.input_value_sat)} == "
            f"{_wl_integer(observation.output_value_sat)} + "
            f"{_wl_integer(observation.fee_sat)}]"
        )

    if check is BitcoinCheck.EDGE_CHRONOLOGY and isinstance(observation, ChronologyObservation):
        return (
            "FullSimplify["
            f"{_wl_integer(observation.spend_height)} > "
            f"{_wl_integer(observation.created_height)}]"
        )

    if check is BitcoinCheck.UNIQUE_SPEND and isinstance(observation, UniqueSpendObservation):
        return f"FullSimplify[{_wl_integer(observation.spend_count)} == 1]"

    if check is BitcoinCheck.VECTOR_DISTANCE and isinstance(observation, VectorDistanceObservation):
        q = "{" + ",".join(_wl_integer(value) for value in observation.query) + "}"
        c = "{" + ",".join(_wl_integer(value) for value in observation.candidate) + "}"
        return f"FullSimplify[Norm[{q} - {c}, 2]]"

    raise BitcoinWolframContractError("observation type does not match the requested check")


def evaluate_local(check: BitcoinCheck, observation: Any) -> bool | int | float:
    """Deterministic local reference used to compare a real Wolfram result."""
    if check is BitcoinCheck.FEE_CONSERVATION and isinstance(observation, FeeObservation):
        return observation.input_value_sat == observation.output_value_sat + observation.fee_sat
    if check is BitcoinCheck.EDGE_CHRONOLOGY and isinstance(observation, ChronologyObservation):
        return observation.spend_height > observation.created_height
    if check is BitcoinCheck.UNIQUE_SPEND and isinstance(observation, UniqueSpendObservation):
        return observation.spend_count == 1
    if check is BitcoinCheck.VECTOR_DISTANCE and isinstance(observation, VectorDistanceObservation):
        total = sum((a - b) ** 2 for a, b in zip(observation.query, observation.candidate))
        return total ** 0.5
    raise BitcoinWolframContractError("observation type does not match the requested check")


def build_cag_countercheck(check: BitcoinCheck, observation: Any) -> dict[str, Any]:
    """Create a secret-free, bounded request description for the existing CAG lane."""
    expression = build_wolfram_expression(check, observation)
    return {
        "component_id": "wolfram.cag.compute",
        "result_type": "structured_fact" if check is not BitcoinCheck.VECTOR_DISTANCE else "numeric_approximation",
        "domain": "bitcoin",
        "operation": check.value,
        "expression": expression,
        "truth_boundary": "supplemental_countercheck",
    }


_SAFE_TXID = re.compile(r"^[0-9a-f]{64}$")


def evidence_binding(check: BitcoinCheck, observation: Any, txids: tuple[str, ...]) -> dict[str, Any]:
    """Bind the counter-check to canonical transaction identifiers without storing bodies."""
    if not txids or any(not _SAFE_TXID.fullmatch(item) for item in txids):
        raise BitcoinWolframContractError("txids must be lowercase SHA-256 identifiers")
    return {
        "check": check.value,
        "txids": tuple(txids),
        "observation_hash": _observation_hash(observation),
        "truth_boundary": "supplemental_countercheck",
    }


def _observation_hash(observation: Any) -> str:
    import hashlib
    import json
    if hasattr(observation, "__dict__"):
        body = observation.__dict__
    else:
        body = {
            name: getattr(observation, name)
            for name in getattr(observation, "__dataclass_fields__", {})
        }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "BitcoinWolframContractError",
    "BitcoinCheck",
    "FeeObservation",
    "ChronologyObservation",
    "UniqueSpendObservation",
    "VectorDistanceObservation",
    "build_wolfram_expression",
    "evaluate_local",
    "build_cag_countercheck",
    "evidence_binding",
]
