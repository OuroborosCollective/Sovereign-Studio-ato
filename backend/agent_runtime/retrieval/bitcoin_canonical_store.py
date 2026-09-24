"""SQLite reference store for the canonical Bitcoin transaction/UTXO graph.

This is a real persistent reference implementation for full-chain ingestion.
It is intentionally separate from the higher-level graph contracts so another
storage backend (PostgreSQL/columnar/KV) can later implement the same semantics.

Invariants:
- block hash is unique per height
- transaction txid is unique
- input prevout is resolved from canonical outputs
- a confirmed output can have at most one confirmed spend
- integer satoshis are stored as INTEGER, never floating-point BTC values
- rewinding is explicit and cascade-safe for chain reorg recovery
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import sqlite3
from typing import Iterator, Mapping

from .bitcoin_graph import BitcoinBlock, BitcoinTransaction, PrevoutRef


class BitcoinStoreError(RuntimeError):
    """Raised when canonical store invariants cannot be satisfied."""


_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS blocks (
    height INTEGER PRIMARY KEY,
    block_hash TEXT NOT NULL UNIQUE,
    previous_block_hash TEXT,
    timestamp INTEGER NOT NULL,
    nonce INTEGER NOT NULL,
    bits TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    txid TEXT PRIMARY KEY,
    block_height INTEGER NOT NULL,
    block_hash TEXT NOT NULL,
    block_time INTEGER NOT NULL,
    version INTEGER NOT NULL,
    locktime INTEGER NOT NULL,
    weight INTEGER,
    virtual_size INTEGER,
    coinbase INTEGER NOT NULL CHECK (coinbase IN (0,1)),
    content_hash TEXT NOT NULL,
    FOREIGN KEY (block_height) REFERENCES blocks(height) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_transactions_height
    ON transactions(block_height);

CREATE TABLE IF NOT EXISTS outputs (
    txid TEXT NOT NULL,
    vout INTEGER NOT NULL,
    value_sat INTEGER NOT NULL CHECK (value_sat >= 0),
    script_type TEXT NOT NULL,
    script_bytes INTEGER NOT NULL CHECK (script_bytes >= 0),
    address TEXT,
    pubkey TEXT,
    spent_by_txid TEXT,
    spent_by_input_index INTEGER,
    PRIMARY KEY (txid, vout),
    FOREIGN KEY (txid) REFERENCES transactions(txid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_outputs_spender
    ON outputs(spent_by_txid, spent_by_input_index);

CREATE TABLE IF NOT EXISTS inputs (
    txid TEXT NOT NULL,
    input_index INTEGER NOT NULL,
    prev_txid TEXT,
    prev_vout INTEGER,
    sequence INTEGER NOT NULL,
    script_type TEXT NOT NULL,
    value_sat INTEGER,
    prevout_height INTEGER,
    script_bytes INTEGER NOT NULL CHECK (script_bytes >= 0),
    PRIMARY KEY (txid, input_index),
    FOREIGN KEY (txid) REFERENCES transactions(txid) ON DELETE CASCADE,
    CHECK (
        (prev_txid IS NULL AND prev_vout IS NULL AND value_sat IS NULL)
        OR
        (prev_txid IS NOT NULL AND prev_vout IS NOT NULL AND value_sat IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_inputs_prevout
    ON inputs(prev_txid, prev_vout);

CREATE TABLE IF NOT EXISTS graph_edges (
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    relation TEXT NOT NULL,
    PRIMARY KEY (source, target, relation)
);

CREATE TABLE IF NOT EXISTS index_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    last_height INTEGER NOT NULL,
    last_block_hash TEXT NOT NULL,
    graph_snapshot_hash TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class StoredPrevout:
    value_sat: int
    block_height: int
    script_pubkey: Mapping[str, object]

    @property
    def spendable(self) -> bool:
        return True


class BitcoinCanonicalStore:
    """Transactional SQLite implementation of the canonical UTXO graph state."""

    def __init__(self, path: str) -> None:
        self._path = path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(_SCHEMA)

    def latest_height(self) -> int | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT last_height FROM index_state WHERE singleton=1"
            ).fetchone()
        return None if row is None else int(row["last_height"])

    def resolve_prevout(self, txid: str, vout: int) -> StoredPrevout | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT o.value_sat, t.block_height, o.script_type, o.script_bytes,
                       o.address, o.pubkey
                FROM outputs AS o
                JOIN transactions AS t ON t.txid = o.txid
                WHERE o.txid=? AND o.vout=?
                """,
                (str(txid).lower(), int(vout)),
            ).fetchone()
        if row is None:
            return None
        return StoredPrevout(
            value_sat=int(row["value_sat"]),
            block_height=int(row["block_height"]),
            script_pubkey={
                "type": str(row["script_type"]),
                "hex": "",
                "addresses": [row["address"]] if row["address"] else [],
                "pubkey": row["pubkey"],
            },
        )

    def _resolve_from_connection(
        self,
        connection: sqlite3.Connection,
        prevout: PrevoutRef,
    ) -> StoredPrevout | None:
        row = connection.execute(
            """
            SELECT o.value_sat, t.block_height, o.script_type, o.address, o.pubkey
            FROM outputs AS o
            JOIN transactions AS t ON t.txid = o.txid
            WHERE o.txid=? AND o.vout=?
            """,
            (prevout.txid, prevout.vout),
        ).fetchone()
        if row is None:
            return None
        return StoredPrevout(
            value_sat=int(row["value_sat"]),
            block_height=int(row["block_height"]),
            script_pubkey={
                "type": str(row["script_type"]),
                "hex": "",
                "addresses": [row["address"]] if row["address"] else [],
                "pubkey": row["pubkey"],
            },
        )

    def resolve_prevout_for_ingest(
        self,
        connection: sqlite3.Connection,
        txid: str,
        vout: int,
    ) -> Mapping[str, object] | None:
        row = connection.execute(
            """
            SELECT o.value_sat, t.block_height, o.script_type, o.address, o.pubkey
            FROM outputs AS o
            JOIN transactions AS t ON t.txid = o.txid
            WHERE o.txid=? AND o.vout=?
            """,
            (str(txid).lower(), int(vout)),
        ).fetchone()
        if row is None:
            return None
        return {
            "value_sat": int(row["value_sat"]),
            "block_height": int(row["block_height"]),
            "script_pubkey": {
                "type": str(row["script_type"]),
                "hex": "",
                "addresses": [row["address"]] if row["address"] else [],
                "pubkey": row["pubkey"],
            },
        }

    def contains_block(self, height: int, block_hash: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM blocks WHERE height=? AND block_hash=?",
                (int(height), str(block_hash).lower()),
            ).fetchone()
        return row is not None

    def ingest_block(
        self,
        block: BitcoinBlock,
        *,
        snapshot_hash: str,
    ) -> None:
        with self._connection() as connection:
            expected_previous = None
            if block.height > 0:
                row = connection.execute(
                    "SELECT block_hash FROM blocks WHERE height=?",
                    (block.height - 1,),
                ).fetchone()
                if row is None:
                    raise BitcoinStoreError(
                        f"cannot ingest height {block.height}: previous block is missing"
                    )
                expected_previous = str(row["block_hash"])
            if expected_previous and block.previous_block_hash != expected_previous:
                raise BitcoinStoreError("block previous_block_hash mismatch")

            existing = connection.execute(
                "SELECT block_hash FROM blocks WHERE height=?",
                (block.height,),
            ).fetchone()
            if existing and str(existing["block_hash"]) != block.block_hash:
                raise BitcoinStoreError(
                    f"height {block.height} already contains another block; rewind required"
                )
            if existing:
                return

            connection.execute(
                """
                INSERT INTO blocks(height, block_hash, previous_block_hash, timestamp, nonce, bits)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    block.height,
                    block.block_hash,
                    block.previous_block_hash,
                    block.timestamp,
                    block.nonce,
                    block.bits,
                ),
            )

            for tx in block.transactions:
                connection.execute(
                    """
                    INSERT INTO transactions(
                        txid, block_height, block_hash, block_time, version, locktime,
                        weight, virtual_size, coinbase, content_hash
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        tx.txid,
                        tx.block_height,
                        tx.block_hash,
                        tx.block_time,
                        tx.version,
                        tx.locktime,
                        tx.weight,
                        tx.virtual_size,
                        int(tx.coinbase),
                        tx.content_hash,
                    ),
                )

                for item in tx.inputs:
                    resolved = (
                        self._resolve_from_connection(connection, item.prevout)
                        if item.prevout is not None else None
                    )
                    value_sat = item.value_sat
                    prevout_height = item.prevout_height
                    script_type = item.script_type
                    if item.prevout is not None:
                        if resolved is None:
                            raise BitcoinStoreError(
                                f"missing prevout {item.prevout.key} while ingesting {tx.txid}"
                            )
                        if value_sat is None or value_sat != resolved.value_sat:
                            raise BitcoinStoreError("input value does not match canonical prevout")
                        if prevout_height is None:
                            prevout_height = resolved.block_height
                    connection.execute(
                        """
                        INSERT INTO inputs(
                            txid, input_index, prev_txid, prev_vout, sequence,
                            script_type, value_sat, prevout_height, script_bytes
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            tx.txid,
                            item.input_index,
                            item.prevout.txid if item.prevout else None,
                            item.prevout.vout if item.prevout else None,
                            item.sequence,
                            script_type,
                            value_sat,
                            prevout_height,
                            item.script_bytes,
                        ),
                    )

                for output in tx.outputs:
                    connection.execute(
                        """
                        INSERT INTO outputs(
                            txid, vout, value_sat, script_type, script_bytes, address, pubkey
                        ) VALUES(?,?,?,?,?,?,?)
                        """,
                        (
                            tx.txid,
                            output.vout,
                            output.value_sat,
                            output.script_type,
                            output.script_bytes,
                            output.address,
                            output.pubkey,
                        ),
                    )

                for item in tx.inputs:
                    if item.prevout is None:
                        continue
                    updated = connection.execute(
                        """
                        UPDATE outputs
                        SET spent_by_txid=?, spent_by_input_index=?
                        WHERE txid=? AND vout=?
                          AND spent_by_txid IS NULL
                        """,
                        (
                            tx.txid,
                            item.input_index,
                            item.prevout.txid,
                            item.prevout.vout,
                        ),
                    )
                    if updated.rowcount != 1:
                        raise BitcoinStoreError(
                            f"prevout {item.prevout.key} is missing or already spent"
                        )

                block_node = f"b:{block.height}:{block.block_hash}"
                tx_node = f"t:{tx.txid}"
                connection.execute(
                    "INSERT OR IGNORE INTO graph_edges(source,target,relation) VALUES(?,?,?)",
                    (block_node, tx_node, "contains"),
                )
                for output in tx.outputs:
                    connection.execute(
                        "INSERT OR IGNORE INTO graph_edges(source,target,relation) VALUES(?,?,?)",
                        (tx_node, f"o:{tx.txid}:{output.vout}", "creates"),
                    )
                for item in tx.inputs:
                    if item.prevout is not None:
                        connection.execute(
                            "INSERT OR IGNORE INTO graph_edges(source,target,relation) VALUES(?,?,?)",
                            (
                                f"o:{item.prevout.txid}:{item.prevout.vout}",
                                tx_node,
                                "spent_by",
                            ),
                        )

            connection.execute(
                """
                INSERT INTO index_state(singleton,last_height,last_block_hash,graph_snapshot_hash)
                VALUES(1,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                    last_height=excluded.last_height,
                    last_block_hash=excluded.last_block_hash,
                    graph_snapshot_hash=excluded.graph_snapshot_hash
                """,
                (block.height, block.block_hash, snapshot_hash),
            )

    def rewind_to_height(self, height: int) -> None:
        if height < -1:
            raise BitcoinStoreError("rewind height must be >= -1")
        with self._connection() as connection:
            connection.execute("DELETE FROM blocks WHERE height > ?", (int(height),))
            if height < 0:
                connection.execute("DELETE FROM index_state")
            else:
                row = connection.execute(
                    "SELECT height, block_hash FROM blocks WHERE height=?",
                    (int(height),),
                ).fetchone()
                if row is None:
                    connection.execute("DELETE FROM index_state")
                else:
                    connection.execute(
                        """
                        UPDATE index_state
                        SET last_height=?, last_block_hash=?, graph_snapshot_hash=''
                        WHERE singleton=1
                        """,
                        (int(row["height"]), str(row["block_hash"])),
                    )

    def count_rows(self) -> dict[str, int]:
        with self._connection() as connection:
            result = {}
            for table in ("blocks", "transactions", "inputs", "outputs", "graph_edges"):
                row = connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                result[table] = int(row["c"])
        return result


__all__ = ["BitcoinStoreError", "StoredPrevout", "BitcoinCanonicalStore"]
