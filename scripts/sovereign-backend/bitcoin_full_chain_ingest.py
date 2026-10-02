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

from agent_runtime.retrieval.bitcoin_rpc import BitcoinCoreRpcClient, BitcoinCoreRpcConfig, BitcoinCoreRpcError
from agent_runtime.retrieval.bitcoin_canonical_store import BitcoinCanonicalStore
from agent_runtime.retrieval.bitcoin_chain_indexer import ingest_chain

MAINNET_GENESIS_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"


def check_mainnet(client: BitcoinCoreRpcClient) -> int:
    """Check the source and full-block method before any store mutation."""
    info = client.call("getblockchaininfo")
    if not isinstance(info, dict) or info.get("chain") != "main":
        raise BitcoinCoreRpcError("Bitcoin mainnet is required")
    tip = client.get_block_count()
    genesis = client.get_block(0)
    if genesis.get("hash") != MAINNET_GENESIS_HASH:
        raise BitcoinCoreRpcError("Bitcoin mainnet genesis does not match")
    if not isinstance(genesis.get("tx"), list) or not genesis["tx"] or not all(
        isinstance(tx, dict) for tx in genesis["tx"]
    ):
        raise BitcoinCoreRpcError("RPC must support getblock verbosity 2")
    return tip


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-height", type=int, default=None)
    parser.add_argument("--end-height", type=int, default=None)
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--check-rpc", action="store_true", help="Check mainnet RPC without writing a store")
    parser.add_argument(
        "--store",
        default=os.environ.get("BITCOIN_CANONICAL_STORE", "data/bitcoin/canonical.sqlite"),
    )
    args = parser.parse_args()

    endpoint = os.environ.get("BITCOIN_RPC_URL", "").strip()
    if not endpoint:
        raise SystemExit("BITCOIN_RPC_URL is not configured")

    client = BitcoinCoreRpcClient(BitcoinCoreRpcConfig(
        endpoint=endpoint,
        auth_mode=os.environ.get("BITCOIN_RPC_AUTH_MODE", "basic").strip(),
    ))
    tip = check_mainnet(client)
    if args.check_rpc:
        print("BITCOIN_RPC_PREFLIGHT=PASS")
        print("NETWORK=main")
        print(f"TIP_HEIGHT={tip}")
        print(f"GENESIS_BLOCK_HASH={MAINNET_GENESIS_HASH}")
        return 0

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
    try:
        raise SystemExit(main())
    except BitcoinCoreRpcError as exc:
        raise SystemExit(str(exc)) from None
