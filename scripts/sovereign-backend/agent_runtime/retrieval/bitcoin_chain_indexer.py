"""Streaming Bitcoin Core -> canonical Bitcoin UTXO/graph indexer."""

from __future__ import annotations

from dataclasses import dataclass

from .bitcoin_rpc import BitcoinCoreRpcClient
from .bitcoin_canonical_store import BitcoinCanonicalStore


class BitcoinIngestError(RuntimeError):
    """Raised when a chain ingest request is invalid."""


@dataclass(frozen=True, slots=True)
class BitcoinIngestResult:
    start_height: int
    end_height: int
    blocks_ingested: int
    rows: dict[str, int]
    last_block_hash: str


def ingest_chain(
    client: BitcoinCoreRpcClient,
    store: BitcoinCanonicalStore,
    *,
    start_height: int | None = None,
    end_height: int | None = None,
) -> BitcoinIngestResult:
    """Ingest a contiguous block range from a real Bitcoin Core node.

    Resume defaults to the block after the persisted height. Reorg recovery is
    explicit: when the canonical store detects a different block at a height,
    callers must locate the common ancestor and invoke rewind_to_height().
    """
    store.initialize()
    persisted_height = store.latest_height()
    resolved_start = (
        int(start_height)
        if start_height is not None
        else (persisted_height + 1 if persisted_height is not None else 0)
    )
    resolved_end = client.get_block_count() if end_height is None else int(end_height)

    if resolved_start < 0 or resolved_end < -1:
        raise BitcoinIngestError("block heights must be >= 0")
    if resolved_end < resolved_start:
        return BitcoinIngestResult(
            start_height=resolved_start,
            end_height=resolved_end,
            blocks_ingested=0,
            rows=store.count_rows(),
            last_block_hash="",
        )

    blocks_ingested = 0
    last_hash = ""
    for raw_block in client.iter_blocks(
        start_height=resolved_start,
        end_height=resolved_end,
    ):
        block = store.ingest_rpc_block(raw_block)
        blocks_ingested += 1
        last_hash = block.block_hash

    return BitcoinIngestResult(
        start_height=resolved_start,
        end_height=resolved_end,
        blocks_ingested=blocks_ingested,
        rows=store.count_rows(),
        last_block_hash=last_hash,
    )


__all__ = ["BitcoinIngestError", "BitcoinIngestResult", "ingest_chain"]
