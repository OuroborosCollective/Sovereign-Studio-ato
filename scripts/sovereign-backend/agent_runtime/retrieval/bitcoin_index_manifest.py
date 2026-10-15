"""Content-addressed manifest contracts for Bitcoin ScaNN shards.

A Bitcoin mainnet corpus is larger than the existing generic ScaNN manifest
record limit, so Bitcoin uses an explicit shard manifest. Each shard is
individually bounded and hash-bound; the top-level manifest binds chain range,
canonical graph snapshot, vector corpus and all shard identities.

This module is pure stdlib and does not know how ScaNN indices are stored.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


class BitcoinIndexManifestError(ValueError):
    """Raised when a Bitcoin index manifest violates its contract."""


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_hex(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise BitcoinIndexManifestError(f"{label} must be a lowercase SHA-256")
    return normalized


@dataclass(frozen=True, slots=True)
class BitcoinIndexShardManifest:
    shard_id: str
    block_start: int
    block_end: int
    transaction_start: int
    transaction_end: int
    vector_count: int
    corpus_hash: str
    index_hash: str
    index_relative_path: str

    def __post_init__(self) -> None:
        if not self.shard_id or len(self.shard_id) > 128:
            raise BitcoinIndexManifestError("invalid shard_id")
        for name in ("block_start", "block_end", "transaction_start", "transaction_end", "vector_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BitcoinIndexManifestError(f"{name} must be a non-negative integer")
        if self.block_end < self.block_start:
            raise BitcoinIndexManifestError("block range is inverted")
        if self.transaction_end <= self.transaction_start:
            raise BitcoinIndexManifestError("transaction range must be non-empty")
        if self.vector_count != self.transaction_end - self.transaction_start:
            raise BitcoinIndexManifestError("vector_count must equal transaction range size")
        _sha256_hex(self.corpus_hash, "corpus_hash")
        _sha256_hex(self.index_hash, "index_hash")
        if not self.index_relative_path or self.index_relative_path.startswith("/"):
            raise BitcoinIndexManifestError("index_relative_path must be relative")


@dataclass(frozen=True, slots=True)
class BitcoinScannIndexManifest:
    schema_version: str
    chain: str
    source_graph_hash: str
    corpus_hash: str
    source_revision: str
    block_start: int
    block_end: int
    transaction_count: int
    vector_dimension: int
    scann_version: str
    distance_metric: str
    normalization: str
    cpu_architecture: str
    shard_transaction_limit: int
    shards: tuple[BitcoinIndexShardManifest, ...]
    manifest_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "sovereign.bitcoin-scann-index.v1":
            raise BitcoinIndexManifestError("unsupported schema_version")
        if self.chain != "bitcoin-mainnet":
            raise BitcoinIndexManifestError("Bitcoin index manifest must bind bitcoin-mainnet")
        _sha256_hex(self.source_graph_hash, "source_graph_hash")
        _sha256_hex(self.corpus_hash, "corpus_hash")
        if len(self.source_revision) != 40 or any(ch not in "0123456789abcdef" for ch in self.source_revision):
            raise BitcoinIndexManifestError("source_revision must be a lowercase SHA-40")
        if self.block_end < self.block_start:
            raise BitcoinIndexManifestError("top-level block range is inverted")
        if isinstance(self.transaction_count, bool) or self.transaction_count < 0:
            raise BitcoinIndexManifestError("transaction_count must be non-negative")
        if isinstance(self.vector_dimension, bool) or self.vector_dimension < 1 or self.vector_dimension > 4096:
            raise BitcoinIndexManifestError("vector_dimension must be in 1..4096")
        if not self.scann_version:
            raise BitcoinIndexManifestError("scann_version must not be empty")
        if self.distance_metric not in {"cosine", "squared_l2", "l2", "dot_product"}:
            raise BitcoinIndexManifestError("unsupported distance_metric")
        if self.normalization not in {"none", "l2", "l2_squared"}:
            raise BitcoinIndexManifestError("unsupported normalization")
        if not self.cpu_architecture:
            raise BitcoinIndexManifestError("cpu_architecture must not be empty")
        if isinstance(self.shard_transaction_limit, bool) or self.shard_transaction_limit < 1:
            raise BitcoinIndexManifestError("shard_transaction_limit must be positive")

        ordered = tuple(sorted(self.shards, key=lambda shard: shard.transaction_start))
        if ordered != self.shards:
            raise BitcoinIndexManifestError("shards must be transaction-order sorted")
        cursor = 0
        for shard in self.shards:
            if shard.transaction_start != cursor:
                raise BitcoinIndexManifestError("shards must be contiguous from transaction 0")
            if shard.vector_count > self.shard_transaction_limit:
                raise BitcoinIndexManifestError("shard exceeds shard_transaction_limit")
            cursor = shard.transaction_end
        if cursor != self.transaction_count:
            raise BitcoinIndexManifestError("shards do not cover transaction_count")

        expected = self.canonical_body()
        if _sha256(expected) != self.manifest_hash:
            raise BitcoinIndexManifestError("manifest_hash does not match canonical body")

    def canonical_body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "chain": self.chain,
            "source_graph_hash": self.source_graph_hash,
            "corpus_hash": self.corpus_hash,
            "source_revision": self.source_revision,
            "block_start": self.block_start,
            "block_end": self.block_end,
            "transaction_count": self.transaction_count,
            "vector_dimension": self.vector_dimension,
            "scann_version": self.scann_version,
            "distance_metric": self.distance_metric,
            "normalization": self.normalization,
            "cpu_architecture": self.cpu_architecture,
            "shard_transaction_limit": self.shard_transaction_limit,
            "shards": [
                {
                    "shard_id": shard.shard_id,
                    "block_start": shard.block_start,
                    "block_end": shard.block_end,
                    "transaction_start": shard.transaction_start,
                    "transaction_end": shard.transaction_end,
                    "vector_count": shard.vector_count,
                    "corpus_hash": shard.corpus_hash,
                    "index_hash": shard.index_hash,
                    "index_relative_path": shard.index_relative_path,
                }
                for shard in self.shards
            ],
        }


def create_manifest(
    *,
    source_graph_hash: str,
    corpus_hash: str,
    source_revision: str,
    block_start: int,
    block_end: int,
    transaction_count: int,
    vector_dimension: int,
    scann_version: str,
    distance_metric: str,
    normalization: str,
    cpu_architecture: str,
    shard_transaction_limit: int,
    shards: tuple[BitcoinIndexShardManifest, ...],
) -> BitcoinScannIndexManifest:
    body = {
        "schema_version": "sovereign.bitcoin-scann-index.v1",
        "chain": "bitcoin-mainnet",
        "source_graph_hash": _sha256_hex(source_graph_hash, "source_graph_hash"),
        "corpus_hash": _sha256_hex(corpus_hash, "corpus_hash"),
        "source_revision": source_revision,
        "block_start": block_start,
        "block_end": block_end,
        "transaction_count": transaction_count,
        "vector_dimension": vector_dimension,
        "scann_version": scann_version,
        "distance_metric": distance_metric,
        "normalization": normalization,
        "cpu_architecture": cpu_architecture,
        "shard_transaction_limit": shard_transaction_limit,
        "shards": [
            {
                "shard_id": shard.shard_id,
                "block_start": shard.block_start,
                "block_end": shard.block_end,
                "transaction_start": shard.transaction_start,
                "transaction_end": shard.transaction_end,
                "vector_count": shard.vector_count,
                "corpus_hash": shard.corpus_hash,
                "index_hash": shard.index_hash,
                "index_relative_path": shard.index_relative_path,
            }
            for shard in shards
        ],
    }
    return BitcoinScannIndexManifest(
        schema_version=body["schema_version"],
        chain=body["chain"],
        source_graph_hash=body["source_graph_hash"],
        corpus_hash=body["corpus_hash"],
        source_revision=body["source_revision"],
        block_start=body["block_start"],
        block_end=body["block_end"],
        transaction_count=body["transaction_count"],
        vector_dimension=body["vector_dimension"],
        scann_version=body["scann_version"],
        distance_metric=body["distance_metric"],
        normalization=body["normalization"],
        cpu_architecture=body["cpu_architecture"],
        shard_transaction_limit=body["shard_transaction_limit"],
        shards=shards,
        manifest_hash=_sha256(body),
    )


__all__ = [
    "BitcoinIndexManifestError",
    "BitcoinIndexShardManifest",
    "BitcoinScannIndexManifest",
    "create_manifest",
]
