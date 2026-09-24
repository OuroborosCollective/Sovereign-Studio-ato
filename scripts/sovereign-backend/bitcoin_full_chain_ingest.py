#!/usr/bin/env python3
"""Run a real Bitcoin Core -> canonical UTXO store ingest.

Usage:
  BITCOIN_RPC_URL=... BITCOIN_RPC_USER=... BITCOIN_RPC_PASSWORD=... \
    python scripts/sovereign-backend/bitcoin_full_chain_ingest.py --depth 3

The script never prints credentials. It is intended for an authorized Bitcoin
Core endpoint and writes only to the configured SQLite canonical store.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from agent_runtime.retrieval.bitcoin_rpc import BitcoinCoreRpcClient, BitcoinCoreRpcConfig
from agent_runtime.retrieval.bitcoin_canonical_store import BitcoinCanonicalStore
from agent_runtime.retrieval.bitcoin_chain_indexer import ingest_chain


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-height", type=int, default=None)
    parser.add_argument("--end-height", type=int, default=None)
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument(
        "--store",
        default=os.environ.get("BITCOIN_CANONICAL_STORE", "data/bitcoin/canonical.sqlite"),
    )
    args = parser.parse_args()

    endpoint = os.environ.get("BITCOIN_RPC_URL", "").strip()
    if not endpoint:
        raise SystemExit("BITCOIN_RPC_URL is not configured")

    client = BitcoinCoreRpcClient(BitcoinCoreRpcConfig(endpoint=endpoint))
    tip = client.get_block_count()

    if args.depth is not None:
        if args.depth < 1:
            raise SystemExit("--depth must be >= 1")
        end_height = tip if args.end_height is None else args.end_height
        start_height = max(0, end_height - args.depth + 1)
        if args.start_height is not None:
            start_height = args.start_height
    else:
        start_height = args.start_height
        end_height = args.end_height

    store_path = Path(args.store)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store = BitcoinCanonicalStore(str(store_path))
    result = ingest_chain(
        client,
        store,
        start_height=start_height,
        end_height=end_height,
    )

    print("BITCOIN_CORE_INGEST=PASS")
    print(f"TIP_HEIGHT={tip}")
    print(f"START_HEIGHT={result.start_height}")
    print(f"END_HEIGHT={result.end_height}")
    print(f"BLOCKS_INGESTED={result.blocks_ingested}")
    print(f"LAST_BLOCK_HASH={result.last_block_hash}")
    print(f"ROWS={result.rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
