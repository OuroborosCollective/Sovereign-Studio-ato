"""Optional live ScaNN runtime adapter for Bitcoin vectors.

The canonical BitcoinScann bridge remains usable without importing ScaNN. This
module is the optional runtime binding used when the ScaNN wheel is installed.
It builds a squared-L2 index over the deterministic feature vectors and emits
only candidate IDs/scores to the exact-rescore boundary.
"""

from __future__ import annotations

import math
from typing import Sequence

from .bitcoin_scann import AnnCandidate, BitcoinVectorRecord, rescore_ann_candidates
from .scann_manifest import DistanceMetric


class BitcoinScannRuntimeError(RuntimeError):
    """Raised when the optional ScaNN runtime is unavailable or invalid."""


def build_live_searcher(
    records: Sequence[BitcoinVectorRecord],
    *,
    default_k: int = 20,
    training_sample_size: int = 100_000,
    leaves_to_search: int | None = None,
    reorder_candidates: int | None = None,
):
    """Build a real ScaNN searcher and return an ANN callable.

    The callable is deliberately shaped like AnnSearcher and does not expose
    ScaNN objects to the evidence layer. ScaNN remains replaceable infrastructure.
    """
    if not records:
        raise BitcoinScannRuntimeError("at least one vector record is required")
    if isinstance(default_k, bool) or not isinstance(default_k, int) or default_k < 1:
        raise BitcoinScannRuntimeError("default_k must be a positive integer")

    try:
        import numpy as np
        import scann
    except ImportError as exc:
        raise BitcoinScannRuntimeError("ScaNN runtime is not installed") from exc

    ids = tuple(record.record_id for record in records)
    matrix = np.asarray([record.vector for record in records], dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != len(ids):
        raise BitcoinScannRuntimeError("ScaNN matrix shape is invalid")

    dimension = int(matrix.shape[1])
    if dimension == 0:
        raise BitcoinScannRuntimeError("ScaNN vectors must have non-zero dimension")

    builder = scann.scann_ops_pybind.builder(matrix, min(default_k, len(ids)), "squared_l2")
    if len(ids) >= 100_000:
        num_leaves = max(2, int(math.sqrt(len(ids))))
        leaf_search = leaves_to_search or max(1, min(num_leaves, int(math.sqrt(num_leaves))))
        builder = builder.tree(
            num_leaves=num_leaves,
            num_leaves_to_search=leaf_search,
            training_sample_size=min(training_sample_size, len(ids)),
        )
    if len(ids) < 10_000:
        builder = builder.score_brute_force()
    else:
        builder = builder.score_ah(2)
        builder = builder.reorder(
            reorder_candidates or min(len(ids), max(default_k * 5, default_k))
        )
    searcher = builder.build(docids=list(ids))

    def search(query: Sequence[float], k: int):
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise BitcoinScannRuntimeError("k must be a positive integer")
        requested = min(k, len(ids))
        query_array = np.asarray(tuple(float(value) for value in query), dtype=np.float32)
        if query_array.ndim != 1 or int(query_array.shape[0]) != dimension:
            raise BitcoinScannRuntimeError("query dimension does not match ScaNN index")
        search_kwargs = {"final_num_neighbors": requested}
        if leaves_to_search is not None and len(ids) >= 100_000:
            search_kwargs["leaves_to_search"] = leaves_to_search
        neighbors, distances = searcher.search(query_array, **search_kwargs)
        candidates = []
        for rank, (docid, score) in enumerate(zip(neighbors, distances), start=1):
            if isinstance(docid, (int,)):
                record_id = ids[int(docid)]
            else:
                record_id = str(docid)
            if record_id not in ids:
                raise BitcoinScannRuntimeError(
                    "ScaNN returned an unknown document identifier"
                )
            candidates.append(
                AnnCandidate(
                    record_id=record_id,
                    ann_score=float(score),
                    ann_rank=rank,
                )
            )
        return tuple(candidates)

    return search


def search_with_exact_rescore(
    query: Sequence[float],
    records: Sequence[BitcoinVectorRecord],
    searcher,
    *,
    k: int = 20,
):
    """Run live ScaNN retrieval and route candidates through exact rescore."""
    mapping = {record.record_id: record for record in records}
    ann_candidates = searcher(query, k)
    return rescore_ann_candidates(
        query,
        mapping,
        ann_candidates,
        metric=DistanceMetric.COSINE,
        k=k,
    )


__all__ = [
    "BitcoinScannRuntimeError",
    "build_live_searcher",
    "search_with_exact_rescore",
]
