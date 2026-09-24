"""Bitcoin-specific bridge between the canonical graph and ScaNN.

ScaNN is treated strictly as an approximate candidate generator. This module
keeps the canonical vectors and exact rescoring outside the ANN engine so a
high similarity score can never become evidence by itself.

No ScaNN import is required here. An injected ANN callable can be backed by the
existing ScaNN index builder, allowing the repository's revision-bound manifest
and exact reference path to remain the authoritative retrieval contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Callable, Mapping, Sequence

from .scann_manifest import DistanceMetric
from .scann_exact_rescore import exact_distance, normalize_vector


class BitcoinScannContractError(ValueError):
    """Raised when a Bitcoin similarity boundary is invalid."""


Vector = tuple[float, ...]
AnnSearcher = Callable[[Sequence[float], int], Sequence[tuple[str, float]]]


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class BitcoinVectorRecord:
    record_id: str
    vector: Vector
    content_hash: str

    def __post_init__(self) -> None:
        if not self.record_id:
            raise BitcoinScannContractError("record_id must not be empty")
        if len(self.vector) == 0:
            raise BitcoinScannContractError("vector must not be empty")
        if len(self.content_hash) != 64:
            raise BitcoinScannContractError("content_hash must be a SHA-256")
        if any(not math.isfinite(float(value)) for value in self.vector):
            raise BitcoinScannContractError("vector values must be finite")

    @property
    def vector_hash(self) -> str:
        return _canonical_sha256([float(value) for value in self.vector])


@dataclass(frozen=True, slots=True)
class AnnCandidate:
    record_id: str
    ann_score: float
    ann_rank: int

    def __post_init__(self) -> None:
        if not self.record_id:
            raise BitcoinScannContractError("candidate record_id must not be empty")
        if not math.isfinite(float(self.ann_score)):
            raise BitcoinScannContractError("ANN score must be finite")
        if self.ann_rank < 1:
            raise BitcoinScannContractError("ann_rank must be >= 1")


@dataclass(frozen=True, slots=True)
class ExactRescoredCandidate:
    record_id: str
    ann_rank: int
    ann_score: float
    exact_distance: float
    exact_rank: int


@dataclass(frozen=True, slots=True)
class SimilarityReceipt:
    query_hash: str
    metric: str
    requested_k: int
    ann_count: int
    exact_count: int
    candidates: tuple[ExactRescoredCandidate, ...]
    source_vector_count: int
    receipt_hash: str

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.record_id for item in self.candidates)


def _validate_vectors(
    query: Sequence[float],
    records: Mapping[str, BitcoinVectorRecord],
) -> int:
    dimension = len(query)
    if dimension == 0:
        raise BitcoinScannContractError("query vector must not be empty")
    if any(not math.isfinite(float(value)) for value in query):
        raise BitcoinScannContractError("query vector values must be finite")
    for record in records.values():
        if len(record.vector) != dimension:
            raise BitcoinScannContractError(
                f"dimension mismatch for {record.record_id}: "
                f"query={dimension} vector={len(record.vector)}"
            )
    return dimension


def exact_rank_all(
    query: Sequence[float],
    records: Mapping[str, BitcoinVectorRecord],
    *,
    metric: DistanceMetric = DistanceMetric.COSINE,
    k: int,
) -> tuple[ExactRescoredCandidate, ...]:
    """Compute the deterministic reference ranking over every canonical vector."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise BitcoinScannContractError("k must be a positive integer")
    _validate_vectors(query, records)
    query_vector = tuple(float(value) for value in query)
    scored = [
        (record_id, exact_distance(query_vector, record.vector, metric))
        for record_id, record in records.items()
    ]
    scored.sort(key=lambda item: (item[1], item[0]))
    selected = scored[:k]
    return tuple(
        ExactRescoredCandidate(
            record_id=record_id,
            ann_rank=0,
            ann_score=0.0,
            exact_distance=distance,
            exact_rank=index,
        )
        for index, (record_id, distance) in enumerate(selected, start=1)
    )


def rescore_ann_candidates(
    query: Sequence[float],
    records: Mapping[str, BitcoinVectorRecord],
    ann_candidates: Sequence[AnnCandidate | tuple[str, float]],
    *,
    metric: DistanceMetric = DistanceMetric.COSINE,
    k: int,
) -> SimilarityReceipt:
    """Exact-rescore an ANN candidate set and return a deterministic receipt."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise BitcoinScannContractError("k must be a positive integer")
    _validate_vectors(query, records)

    normalized: list[AnnCandidate] = []
    seen: set[str] = set()
    for index, candidate in enumerate(ann_candidates, start=1):
        if isinstance(candidate, AnnCandidate):
            item = candidate
        else:
            record_id, ann_score = candidate
            item = AnnCandidate(record_id=str(record_id), ann_score=float(ann_score), ann_rank=index)
        if item.record_id in seen:
            continue
        seen.add(item.record_id)
        if item.record_id not in records:
            raise BitcoinScannContractError(
                f"ANN candidate {item.record_id!r} is not present in canonical vectors"
            )
        normalized.append(item)

    query_vector = normalize_vector(query, metric_normalization(metric))
    rescored: list[ExactRescoredCandidate] = []
    for item in normalized:
        distance = exact_distance(query_vector, records[item.record_id].vector, metric)
        rescored.append(
            ExactRescoredCandidate(
                record_id=item.record_id,
                ann_rank=item.ann_rank,
                ann_score=item.ann_score,
                exact_distance=distance,
                exact_rank=0,
            )
        )
    rescored.sort(key=lambda item: (item.exact_distance, item.record_id))
    rescored = [
        ExactRescoredCandidate(
            record_id=item.record_id,
            ann_rank=item.ann_rank,
            ann_score=item.ann_score,
            exact_distance=item.exact_distance,
            exact_rank=index,
        )
        for index, item in enumerate(rescored[:k], start=1)
    ]

    payload = {
        "query_hash": _canonical_sha256([float(value) for value in query_vector]),
        "metric": metric.value,
        "requested_k": k,
        "ann_count": len(normalized),
        "exact_count": len(rescored),
        "source_vector_count": len(records),
        "candidates": [
            {
                "record_id": item.record_id,
                "ann_rank": item.ann_rank,
                "ann_score": item.ann_score,
                "exact_distance": item.exact_distance,
                "exact_rank": item.exact_rank,
            }
            for item in rescored
        ],
    }
    return SimilarityReceipt(
        query_hash=payload["query_hash"],
        metric=metric.value,
        requested_k=k,
        ann_count=len(normalized),
        exact_count=len(rescored),
        candidates=tuple(rescored),
        source_vector_count=len(records),
        receipt_hash=_canonical_sha256(payload),
    )


def metric_normalization(metric: DistanceMetric):
    """Cosine uses L2 normalization; other metrics keep their input scale."""
    from .scann_manifest import Normalization
    return Normalization.L2 if metric is DistanceMetric.COSINE else Normalization.NONE


def recall_at_k(
    ann_ids: Sequence[str],
    exact_ids: Sequence[str],
    k: int,
) -> float:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise BitcoinScannContractError("k must be a positive integer")
    expected = set(exact_ids[:k])
    if not expected:
        return 1.0
    return len(expected.intersection(ann_ids[:k])) / len(expected)


def run_ann_then_exact(
    query: Sequence[float],
    records: Mapping[str, BitcoinVectorRecord],
    searcher: AnnSearcher,
    *,
    metric: DistanceMetric = DistanceMetric.COSINE,
    k: int = 20,
) -> SimilarityReceipt:
    """Use ScaNN only for candidate generation; exact scoring remains canonical."""
    ann_rows = searcher(query, k)
    candidates = tuple(
        AnnCandidate(record_id=str(record_id), ann_score=float(score), ann_rank=index)
        for index, (record_id, score) in enumerate(ann_rows, start=1)
    )
    return rescore_ann_candidates(
        query,
        records,
        candidates,
        metric=metric,
        k=k,
    )


__all__ = [
    "BitcoinScannContractError",
    "BitcoinVectorRecord",
    "AnnCandidate",
    "ExactRescoredCandidate",
    "SimilarityReceipt",
    "exact_rank_all",
    "rescore_ann_candidates",
    "recall_at_k",
    "run_ann_then_exact",
]
