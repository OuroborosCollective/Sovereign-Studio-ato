"""Streaming Bitcoin Core -> canonical UTXO/graph ingester.""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from .bitcoin_graph import block_from_rpc
from .bitcoin_rpc import BitcoinCoreRpcClient
from .bitcoin_canonical_store import BitcoinCanonicalStore, BitcoinStoreError


@dataclass(frozen=True, slots=True)
class BitcoinIngestResult:
    start_height: int
    end_height: int
    blocks_ingested: int
    rows: dict[str, int]
    last_block_hash: str


def _snapshot_hash(height: int, block_hash: str) -> str:
    payload = json.dumps(
        {"height": int(height), "block_hash": str(block_hash).lower()},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def ingest_chain(
    client: BitcoinCoreRpcClient,
    store: BitcoinCanonicalStore,
    *,
    start_height: int | None = None,
    end_height: int | None = None,
) -> BitcoinIngestResult:
    """Ingest a contiguous block range with prevouts resolved from the store."""
    store.initialize()
    current = store.latest_height()
    resolved_start = current + 1 if current is not None else 0
    if start_height is not None:
        resolved_start = max(0, int(start_height))
    resolved_end = client.get_block_count() if end_height is None else int(end_height)
    if resolved_end < resolved_start:
        return BitcoinIngestResult(
            start_height=resolved_start,
            end_height=resolved_end,
            blocks_ingested=0,
            rows=store.count_rows(),
            last_block_hash="" if current is None else client.get_block_hash(current),
        )

    blocks_ingested = 0
    last_hash = ""
    for raw_block in client.iter_blocks(
        start_height=resolved_start,
        end_height=resolved_end,
    ):
        with store._connection() as connection_for_resolver:
            block = block_from_rpc(
                raw_block,
                prevout_resolver=lambda txid, vout: store.resolve_prevout_for_ingest(
                    connection_for_resolver, txid, vout
                ),
            )
            digest = _snapshot_hash(block.height, block.block_hash)
            store.ingest_block(block, snapshot_hash=digest)
        blocks_ingested += 1
        last_hash = block.block_hash

    return BitcoinIngestResult(
        start_height=resolved_start,
        end_height=resolved_end,
        blocks_ingested=blocks_ingested,
        rows=store.count_rows(),
        last_block_hash=last_hash,
    )


__all__ = ["BitcoinIngestResult", "ingest_chain"]
