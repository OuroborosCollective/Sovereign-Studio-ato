"""Deterministic Bitcoin transaction/UTXO graph primitives.

This module is the canonical, dependency-free representation used by the
research retrieval lane. It does not decide ownership, attribution or identity.
It records transaction structure, explicit prevout links and, when enriched
with prevout values, exact fee conservation.

The graph is append-only at the storage boundary: callers may stream records
into an external canonical store, while this module only normalizes and hashes
the records. No network, filesystem, clock or random access is used here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import hashlib
import json
import math
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

SATOSHIS_PER_BTC = 100_000_000
_MAX_SCRIPT_LEN = 10_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SCRIPT_TYPES = (
    "p2pk",
    "p2pkh",
    "p2sh",
    "p2wpkh",
    "p2wsh",
    "p2tr",
    "multisig",
    "nulldata",
    "nonstandard",
    "unknown",
)


class BitcoinGraphContractError(ValueError):
    """Raised when a canonical Bitcoin graph object violates its contract."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return _sha256(canonical_json(value))


def _require_sha256(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise BitcoinGraphContractError(f"{label} must be a lowercase SHA-256")
    return normalized


def _require_non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BitcoinGraphContractError(f"{label} must be a non-negative integer")
    return value


def _script_type(value: str) -> str:
    normalized = str(value or "unknown").strip().lower()
    return normalized if normalized in _SCRIPT_TYPES else "unknown"


def _btc_to_sat(value: Any) -> int:
    """Convert a BTC decimal to satoshis without floating-point rounding."""
    try:
        scaled = (
            Decimal(str(value))
            .quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
            * Decimal(SATOSHIS_PER_BTC)
        )
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BitcoinGraphContractError("invalid BTC amount") from exc
    if scaled != scaled.to_integral_value():
        raise BitcoinGraphContractError("BTC amount cannot be represented in whole satoshis")
    return int(scaled)


@dataclass(frozen=True, slots=True)
class PrevoutRef:
    txid: str
    vout: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "txid", _require_sha256(self.txid, "txid"))
        object.__setattr__(self, "vout", _require_non_negative_int(self.vout, "vout"))

    @property
    def key(self) -> str:
        return f"{self.txid}:{self.vout}"


@dataclass(frozen=True, slots=True)
class BitcoinInput:
    input_index: int
    prevout: PrevoutRef | None
    sequence: int
    script_type: str = "unknown"
    value_sat: int | None = None
    prevout_height: int | None = None
    script_bytes: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "input_index", _require_non_negative_int(self.input_index, "input_index")
        )
        if self.prevout is None:
            if self.value_sat is not None:
                raise BitcoinGraphContractError("coinbase input cannot carry value_sat")
        else:
            object.__setattr__(self, "value_sat", _require_non_negative_int(
                self.value_sat, "value_sat"
            ) if self.value_sat is not None else None)
            if self.prevout_height is not None:
                object.__setattr__(
                    self, "prevout_height",
                    _require_non_negative_int(self.prevout_height, "prevout_height"),
                )
        object.__setattr__(
            self, "sequence", _require_non_negative_int(self.sequence, "sequence")
        )
        object.__setattr__(self, "script_type", _script_type(self.script_type))
        object.__setattr__(
            self, "script_bytes", _require_non_negative_int(self.script_bytes, "script_bytes")
        )
        if self.script_bytes > _MAX_SCRIPT_LEN:
            raise BitcoinGraphContractError("script_bytes exceeds safety bound")

    @property
    def is_coinbase(self) -> bool:
        return self.prevout is None


@dataclass(frozen=True, slots=True)
class BitcoinOutput:
    vout: int
    value_sat: int
    script_type: str = "unknown"
    script_bytes: int = 0
    address: str | None = None
    pubkey: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "vout", _require_non_negative_int(self.vout, "vout"))
        object.__setattr__(
            self, "value_sat", _require_non_negative_int(self.value_sat, "value_sat")
        )
        object.__setattr__(self, "script_type", _script_type(self.script_type))
        object.__setattr__(
            self, "script_bytes", _require_non_negative_int(self.script_bytes, "script_bytes")
        )
        if self.script_bytes > _MAX_SCRIPT_LEN:
            raise BitcoinGraphContractError("script_bytes exceeds safety bound")

    @property
    def outpoint(self) -> str:
        return f"{self.vout}"


@dataclass(frozen=True, slots=True)
class BitcoinTransaction:
    txid: str
    block_height: int
    block_hash: str
    block_time: int
    version: int
    locktime: int
    inputs: tuple[BitcoinInput, ...]
    outputs: tuple[BitcoinOutput, ...]
    weight: int | None = None
    virtual_size: int | None = None
    coinbase: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "txid", _require_sha256(self.txid, "txid"))
        object.__setattr__(
            self, "block_height", _require_non_negative_int(self.block_height, "block_height")
        )
        object.__setattr__(self, "block_hash", _require_sha256(self.block_hash, "block_hash"))
        object.__setattr__(
            self, "block_time", _require_non_negative_int(self.block_time, "block_time")
        )
        object.__setattr__(
            self, "version", int(self.version)
        )
        object.__setattr__(
            self, "locktime", _require_non_negative_int(self.locktime, "locktime")
        )
        if self.weight is not None:
            object.__setattr__(self, "weight", _require_non_negative_int(self.weight, "weight"))
        if self.virtual_size is not None:
            object.__setattr__(
                self, "virtual_size", _require_non_negative_int(self.virtual_size, "virtual_size")
            )
        if not self.outputs:
            raise BitcoinGraphContractError("transaction must have at least one output")
        if tuple(item.input_index for item in self.inputs) != tuple(range(len(self.inputs))):
            raise BitcoinGraphContractError("input_index values must be contiguous from zero")
        if tuple(item.vout for item in self.outputs) != tuple(range(len(self.outputs))):
            raise BitcoinGraphContractError("vout values must be contiguous from zero")
        derived_coinbase = any(item.is_coinbase for item in self.inputs)
        if self.coinbase != derived_coinbase:
            raise BitcoinGraphContractError("coinbase flag must match input structure")
        if self.coinbase and len(self.inputs) != 1:
            raise BitcoinGraphContractError("coinbase transaction must have exactly one input")
        if not self.coinbase and not self.inputs:
            raise BitcoinGraphContractError("non-coinbase transaction must have inputs")

    @property
    def input_value_sat(self) -> int | None:
        if self.coinbase:
            return None
        if any(item.value_sat is None for item in self.inputs):
            return None
        return sum(int(item.value_sat) for item in self.inputs if item.value_sat is not None)

    @property
    def output_value_sat(self) -> int:
        return sum(item.value_sat for item in self.outputs)

    @property
    def fee_sat(self) -> int | None:
        input_value = self.input_value_sat
        if input_value is None:
            return None
        fee = input_value - self.output_value_sat
        if fee < 0:
            raise BitcoinGraphContractError("output value exceeds input value")
        return fee

    @property
    def fee_rate_sat_vb(self) -> float | None:
        if self.fee_sat is None or self.virtual_size in (None, 0):
            return None
        return self.fee_sat / self.virtual_size

    def canonical_body(self) -> dict[str, Any]:
        return {
            "block_hash": self.block_hash,
            "block_height": self.block_height,
            "block_time": self.block_time,
            "coinbase": self.coinbase,
            "inputs": [
                {
                    "input_index": item.input_index,
                    "prevout": (
                        {"txid": item.prevout.txid, "vout": item.prevout.vout}
                        if item.prevout else None
                    ),
                    "sequence": item.sequence,
                    "script_type": item.script_type,
                    "value_sat": item.value_sat,
                    "prevout_height": item.prevout_height,
                    "script_bytes": item.script_bytes,
                }
                for item in self.inputs
            ],
            "locktime": self.locktime,
            "outputs": [
                {
                    "vout": item.vout,
                    "value_sat": item.value_sat,
                    "script_type": item.script_type,
                    "script_bytes": item.script_bytes,
                    "address": item.address,
                    "pubkey": item.pubkey,
                }
                for item in self.outputs
            ],
            "txid": self.txid,
            "version": self.version,
            "virtual_size": self.virtual_size,
            "weight": self.weight,
        }

    @property
    def content_hash(self) -> str:
        return canonical_sha256(self.canonical_body())


@dataclass(frozen=True, slots=True)
class BitcoinBlock:
    height: int
    block_hash: str
    previous_block_hash: str | None
    timestamp: int
    nonce: int
    bits: str
    transactions: tuple[BitcoinTransaction, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "height", _require_non_negative_int(self.height, "height"))
        object.__setattr__(self, "block_hash", _require_sha256(self.block_hash, "block_hash"))
        if self.previous_block_hash:
            object.__setattr__(
                self, "previous_block_hash",
                _require_sha256(self.previous_block_hash, "previous_block_hash"),
            )
        object.__setattr__(self, "timestamp", _require_non_negative_int(self.timestamp, "timestamp"))
        object.__setattr__(self, "nonce", _require_non_negative_int(self.nonce, "nonce"))
        if not self.transactions:
            raise BitcoinGraphContractError("block must contain at least one transaction")
        heights = {tx.block_height for tx in self.transactions}
        hashes = {tx.block_hash for tx in self.transactions}
        if heights != {self.height} or hashes != {self.block_hash}:
            raise BitcoinGraphContractError("transaction block binding mismatch")

    @property
    def coinbase(self) -> BitcoinTransaction:
        if not self.transactions[0].coinbase:
            raise BitcoinGraphContractError("first transaction is not coinbase")
        if sum(1 for tx in self.transactions if tx.coinbase) != 1:
            raise BitcoinGraphContractError("block must contain exactly one coinbase transaction")
        return self.transactions[0]


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str
    target: str
    relation: str

    def canonical_body(self) -> dict[str, str]:
        return {
            "relation": self.relation,
            "source": self.source,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    blocks: tuple[BitcoinBlock, ...]
    edges: tuple[GraphEdge, ...]

    @property
    def content_hash(self) -> str:
        payload = {
            "blocks": [
                {
                    "height": block.height,
                    "block_hash": block.block_hash,
                    "previous_block_hash": block.previous_block_hash,
                    "timestamp": block.timestamp,
                    "nonce": block.nonce,
                    "bits": block.bits,
                    "transactions": [tx.content_hash for tx in block.transactions],
                }
                for block in self.blocks
            ],
            "edges": [edge.canonical_body() for edge in self.edges],
        }
        return canonical_sha256(payload)


PrevoutResolver = Callable[[str, int], Mapping[str, Any] | None]


def transaction_from_rpc(
    tx: Mapping[str, Any],
    *,
    block_height: int,
    block_hash: str,
    block_time: int,
    prevout_resolver: PrevoutResolver | None = None,
) -> BitcoinTransaction:
    txid = str(tx.get("txid") or tx.get("hash") or "").lower()
    vins = list(tx.get("vin") or ())
    vouts = list(tx.get("vout") or ())
    inputs: list[BitcoinInput] = []
    for index, item in enumerate(vins):
        coinbase = "coinbase" in item
        if coinbase:
            script_sig = item.get("scriptsig") or item.get("scriptSig") or {}
            script_hex = str(script_sig.get("hex") or "")
            inputs.append(
                BitcoinInput(
                    input_index=index,
                    prevout=None,
                    sequence=int(item.get("sequence", 0)),
                    script_type="unknown",
                    script_bytes=len(script_hex) // 2,
                )
            )
            continue

        prev_txid = str(item.get("txid") or "").lower()
        prev_vout = int(item.get("vout", 0))
        resolved = prevout_resolver(prev_txid, prev_vout) if prevout_resolver else None
        prev_value = None if resolved is None else resolved.get("value_sat")
        prev_height = None if resolved is None else resolved.get("block_height")
        script_pubkey = {} if resolved is None else (resolved.get("script_pubkey") or {})
        inputs.append(
            BitcoinInput(
                input_index=index,
                prevout=PrevoutRef(prev_txid, prev_vout),
                sequence=int(item.get("sequence", 0)),
                script_type=str(script_pubkey.get("type") or "unknown"),
                value_sat=(int(prev_value) if prev_value is not None else None),
                prevout_height=(int(prev_height) if prev_height is not None else None),
                script_bytes=len(str(script_pubkey.get("hex") or "")) // 2,
            )
        )

    outputs: list[BitcoinOutput] = []
    for index, item in enumerate(vouts):
        script = item.get("scriptPubKey") or item.get("script_pub_key") or {}
        addresses = tuple(script.get("addresses") or ())
        address = str(addresses[0]) if addresses else None
        outputs.append(
            BitcoinOutput(
                vout=index,
                value_sat=(
                    _btc_to_sat(item.get("value"))
                    if "value" in item
                    else int(item.get("value_sat", 0))
                ),
                script_type=str(script.get("type") or "unknown"),
                script_bytes=len(str(script.get("hex") or "")) // 2,
                address=address,
                pubkey=(
                    str(script.get("pubkey") or "")
                    if script.get("pubkey") else None
                ),
            )
        )

    return BitcoinTransaction(
        txid=txid,
        block_height=block_height,
        block_hash=block_hash,
        block_time=block_time,
        version=int(tx.get("version", 0)),
        locktime=int(tx.get("locktime", 0)),
        inputs=tuple(inputs),
        outputs=tuple(outputs),
        weight=(int(tx["weight"]) if tx.get("weight") is not None else None),
        virtual_size=(
            int(tx["vsize"]) if tx.get("vsize") is not None else
            int(tx["virtual_size"]) if tx.get("virtual_size") is not None else None
        ),
        coinbase=any(item.is_coinbase for item in inputs),
    )


def block_from_rpc(
    block: Mapping[str, Any],
    *,
    prevout_resolver: PrevoutResolver | None = None,
) -> BitcoinBlock:
    tx_payload = list(block.get("tx") or ())
    transactions = tuple(
        tx if isinstance(tx, BitcoinTransaction) else transaction_from_rpc(
            tx,
            block_height=int(block["height"]),
            block_hash=str(block["hash"]).lower(),
            block_time=int(block["time"]),
            prevout_resolver=prevout_resolver,
        )
        for tx in tx_payload
    )
    return BitcoinBlock(
        height=int(block["height"]),
        block_hash=str(block["hash"]).lower(),
        previous_block_hash=(
            str(block["previousblockhash"]).lower()
            if block.get("previousblockhash") else None
        ),
        timestamp=int(block["time"]),
        nonce=int(block.get("nonce", 0)),
        bits=str(block.get("bits") or ""),
        transactions=transactions,
    )


def graph_edges(blocks: Iterable[BitcoinBlock]) -> tuple[GraphEdge, ...]:
    """Construct deterministic Block -> TX -> Output -> spending-TX edges."""
    edges: list[GraphEdge] = []
    for block in blocks:
        block_node = f"b:{block.height}:{block.block_hash}"
        for tx in block.transactions:
            tx_node = f"t:{tx.txid}"
            edges.append(GraphEdge(block_node, tx_node, "contains"))
            for output in tx.outputs:
                out_node = f"o:{tx.txid}:{output.vout}"
                edges.append(GraphEdge(tx_node, out_node, "creates"))
            for item in tx.inputs:
                if item.prevout is None:
                    continue
                prev_node = f"o:{item.prevout.txid}:{item.prevout.vout}"
                edges.append(GraphEdge(prev_node, tx_node, "spent_by"))
    edges.sort(key=lambda edge: (edge.source, edge.relation, edge.target))
    return tuple(edges)


def build_snapshot(blocks: Sequence[BitcoinBlock]) -> GraphSnapshot:
    ordered = tuple(sorted(blocks, key=lambda item: item.height))
    for previous, current in zip(ordered, ordered[1:]):
        if current.height == previous.height + 1 and current.previous_block_hash != previous.block_hash:
            raise BitcoinGraphContractError("contiguous blocks must link by previous_block_hash")
    return GraphSnapshot(blocks=ordered, edges=graph_edges(ordered))


def _entropy(values: Sequence[int]) -> float:
    if not values:
        return 0.0
    total = sum(values)
    if total <= 0:
        return 0.0
    result = 0.0
    for value in values:
        if value <= 0:
            continue
        probability = value / total
        result -= probability * math.log2(probability)
    return result


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def transaction_feature_vector(tx: BitcoinTransaction) -> tuple[float, ...]:
    """Return a fixed 40-dimensional structural vector for ScaNN."""
    input_values = [item.value_sat for item in tx.inputs if item.value_sat is not None]
    output_values = [item.value_sat for item in tx.outputs]
    fee_sat = tx.fee_sat or 0
    max_value = SATOSHIS_PER_BTC * 21_000_000
    normalized_inputs = [value / max_value for value in input_values]
    normalized_outputs = [value / max_value for value in output_values]

    script_input_counts = Counter(item.script_type for item in tx.inputs)
    script_output_counts = Counter(item.script_type for item in tx.outputs)
    input_one_hot = [
        script_input_counts.get(kind, 0) / max(1, len(tx.inputs))
        for kind in _SCRIPT_TYPES
    ]
    output_one_hot = [
        script_output_counts.get(kind, 0) / max(1, len(tx.outputs))
        for kind in _SCRIPT_TYPES
    ]

    vector = [
        math.log1p(len(tx.inputs)),
        math.log1p(len(tx.outputs)),
        math.log1p(tx.output_value_sat) / math.log1p(max_value),
        math.log1p(tx.input_value_sat or 0) / math.log1p(max_value),
        math.log1p(fee_sat) / math.log1p(max_value),
        math.log1p(tx.fee_rate_sat_vb or 0.0),
        math.log1p(tx.virtual_size or 0.0),
        math.log1p(tx.weight or 0.0),
        float(tx.version) / 3.0,
        float(tx.locktime > 0),
        float(tx.coinbase),
        _ratio(len(tx.inputs), len(tx.outputs)),
        _ratio(tx.output_value_sat, tx.input_value_sat or 1),
        _entropy([int(value) for value in input_values]),
        _entropy([int(value) for value in output_values]),
        min(normalized_inputs, default=0.0),
        max(normalized_inputs, default=0.0),
        min(normalized_outputs, default=0.0),
        max(normalized_outputs, default=0.0),
    ]
    vector.extend(input_one_hot)
    vector.extend(output_one_hot)
    while len(vector) < 40:
        vector.append(0.0)
    result = tuple(float(value) for value in vector[:40])
    norm = math.sqrt(sum(value * value for value in result))
    if norm == 0.0:
        return result
    return tuple(value / norm for value in result)


def transaction_fingerprint(tx: BitcoinTransaction) -> dict[str, Any]:
    """Return exact structural fields kept alongside a similarity vector."""
    return {
        "txid": tx.txid,
        "block_height": tx.block_height,
        "coinbase": tx.coinbase,
        "input_count": len(tx.inputs),
        "output_count": len(tx.outputs),
        "input_value_sat": tx.input_value_sat,
        "output_value_sat": tx.output_value_sat,
        "fee_sat": tx.fee_sat,
        "fee_rate_sat_vb": tx.fee_rate_sat_vb,
        "input_script_types": tuple(item.script_type for item in tx.inputs),
        "output_script_types": tuple(item.script_type for item in tx.outputs),
        "content_hash": tx.content_hash,
    }


__all__ = [
    "SATOSHIS_PER_BTC",
    "BitcoinGraphContractError",
    "BitcoinInput",
    "BitcoinOutput",
    "BitcoinTransaction",
    "BitcoinBlock",
    "PrevoutRef",
    "GraphEdge",
    "GraphSnapshot",
    "PrevoutResolver",
    "canonical_json",
    "canonical_sha256",
    "transaction_from_rpc",
    "block_from_rpc",
    "graph_edges",
    "build_snapshot",
    "transaction_feature_vector",
    "transaction_fingerprint",
]
