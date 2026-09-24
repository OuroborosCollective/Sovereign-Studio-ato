from __future__ import annotations

import math
import pytest

from agent_runtime.retrieval.bitcoin_graph import (
    BitcoinBlock,
    BitcoinInput,
    BitcoinOutput,
    BitcoinTransaction,
    PrevoutRef,
    block_from_rpc,
    build_snapshot,
    canonical_sha256,
    transaction_feature_vector,
)
from agent_runtime.retrieval.bitcoin_scann import (
    AnnCandidate,
    BitcoinVectorRecord,
    BitcoinScannContractError,
    recall_at_k,
    rescore_ann_candidates,
    run_ann_then_exact,
)
from agent_runtime.retrieval.bitcoin_wolfram_contract import (
    BitcoinCheck,
    ChronologyObservation,
    FeeObservation,
    UniqueSpendObservation,
    build_cag_countercheck,
    build_wolfram_expression,
    evaluate_local,
)


def _tx(
    txid: str,
    *,
    height: int,
    block_hash: str,
    inputs: tuple[BitcoinInput, ...],
    outputs: tuple[BitcoinOutput, ...],
    coinbase: bool = False,
) -> BitcoinTransaction:
    return BitcoinTransaction(
        txid=txid,
        block_height=height,
        block_hash=block_hash,
        block_time=1_000_000 + height,
        version=2,
        locktime=0,
        inputs=inputs,
        outputs=outputs,
        virtual_size=100,
        weight=400,
        coinbase=coinbase,
    )


def test_rpc_btc_values_are_converted_to_exact_satoshis() -> None:
    block = block_from_rpc(
        {
            "height": 1,
            "hash": "a" * 64,
            "previousblockhash": "b" * 64,
            "time": 1,
            "nonce": 0,
            "bits": "1d00ffff",
            "tx": [
                {
                    "txid": "c" * 64,
                    "version": 2,
                    "locktime": 0,
                    "vin": [{"coinbase": "0101", "sequence": 0}],
                    "vout": [{"value": "1.23456789", "n": 0, "scriptPubKey": {"type": "p2pk"}}],
                }
            ],
        }
    )
    assert block.coinbase.output_value_sat == 123_456_789


def test_fee_conservation_is_exact_in_satoshis() -> None:
    tx = _tx(
        "c" * 64,
        height=2,
        block_hash="a" * 64,
        inputs=(
            BitcoinInput(0, PrevoutRef("b" * 64, 0), 0, value_sat=5_000_000),
        ),
        outputs=(BitcoinOutput(0, 4_999_000, script_type="p2pkh"),),
    )
    assert tx.input_value_sat == 5_000_000
    assert tx.output_value_sat == 4_999_000
    assert tx.fee_sat == 1_000


def test_graph_snapshot_edges_are_deterministic() -> None:
    tx1 = _tx(
        "1" * 64,
        height=1,
        block_hash="a" * 64,
        inputs=(BitcoinInput(0, None, 0),),
        outputs=(BitcoinOutput(0, 50 * 100_000_000, script_type="p2pk"),),
        coinbase=True,
    )
    tx2 = _tx(
        "2" * 64,
        height=2,
        block_hash="c" * 64,
        inputs=(BitcoinInput(0, PrevoutRef("1" * 64, 0), 0, value_sat=50 * 100_000_000),),
        outputs=(BitcoinOutput(0, 50 * 100_000_000 - 1000, script_type="p2pkh"),),
    )
    b1 = BitcoinBlock(1, "a" * 64, None, 1, 0, "1d00ffff", (tx1,))
    b2 = BitcoinBlock(2, "c" * 64, "a" * 64, 2, 0, "1d00ffff", (tx2,))
    one = build_snapshot((b2, b1))
    two = build_snapshot((b1, b2))
    assert one.content_hash == two.content_hash
    relations = {(edge.source, edge.target, edge.relation) for edge in one.edges}
    assert ("t:" + "1" * 64, "o:" + "1" * 64 + ":0", "creates") in relations
    assert ("o:" + "1" * 64 + ":0", "t:" + "2" * 64, "spent_by") in relations


def test_feature_vector_is_fixed_dimension_and_l2_normalized() -> None:
    tx = _tx(
        "d" * 64,
        height=10,
        block_hash="e" * 64,
        inputs=(
            BitcoinInput(0, PrevoutRef("a" * 64, 0), 1, value_sat=2_000_000),
            BitcoinInput(1, PrevoutRef("b" * 64, 1), 1, value_sat=3_000_000),
        ),
        outputs=(
            BitcoinOutput(0, 4_000_000, script_type="p2wpkh"),
            BitcoinOutput(1, 990_000, script_type="p2tr"),
        ),
    )
    vector = transaction_feature_vector(tx)
    assert len(vector) == 40
    assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0, rel_tol=1e-12)


def test_ann_candidates_are_exactly_rescored() -> None:
    records = {
        "tx:near": BitcoinVectorRecord("tx:near", (1.0, 0.0), "a" * 64),
        "tx:far": BitcoinVectorRecord("tx:far", (0.0, 1.0), "b" * 64),
    }
    receipt = rescore_ann_candidates(
        (1.0, 0.0),
        records,
        (AnnCandidate("tx:far", 0.99, 1), AnnCandidate("tx:near", 0.10, 2)),
        k=2,
    )
    assert receipt.candidate_ids == ("tx:near", "tx:far")
    assert receipt.candidates[0].exact_rank == 1


def test_ann_path_is_only_a_candidate_generator() -> None:
    records = {
        "tx:a": BitcoinVectorRecord("tx:a", (1.0, 0.0), "a" * 64),
        "tx:b": BitcoinVectorRecord("tx:b", (0.0, 1.0), "b" * 64),
    }

    def ann_searcher(query, k):
        return (("tx:b", 0.2), ("tx:a", 0.9))

    receipt = run_ann_then_exact((1.0, 0.0), records, ann_searcher, k=1)
    assert receipt.candidate_ids == ("tx:a",)


def test_unknown_ann_candidate_fails_closed() -> None:
    records = {"tx:a": BitcoinVectorRecord("tx:a", (1.0, 0.0), "a" * 64)}
    with pytest.raises(BitcoinScannContractError, match="not present"):
        rescore_ann_candidates(
            (1.0, 0.0),
            records,
            (("tx:missing", 0.1),),
            k=1,
        )


def test_recall_is_bounded_and_deterministic() -> None:
    assert recall_at_k(("a", "b", "c"), ("b", "a", "d"), 2) == 1.0
    assert recall_at_k(("a",), ("a", "b"), 2) == 0.5


def test_wolfram_fee_expression_and_local_reference_agree() -> None:
    observation = FeeObservation(5_000_000, 4_999_000, 1_000)
    expression = build_wolfram_expression(BitcoinCheck.FEE_CONSERVATION, observation)
    assert expression == "FullSimplify[5000000 == 4999000 + 1000]"
    assert evaluate_local(BitcoinCheck.FEE_CONSERVATION, observation) is True


def test_wolfram_chronology_and_unique_spend_are_bounded() -> None:
    chronology = ChronologyObservation(created_height=100, spend_height=101)
    unique = UniqueSpendObservation(spend_count=1)
    assert evaluate_local(BitcoinCheck.EDGE_CHRONOLOGY, chronology) is True
    assert evaluate_local(BitcoinCheck.UNIQUE_SPEND, unique) is True
    payload = build_cag_countercheck(BitcoinCheck.EDGE_CHRONOLOGY, chronology)
    assert payload["component_id"] == "wolfram.cag.compute"
    assert payload["truth_boundary"] == "supplemental_countercheck"


def test_canonical_hash_does_not_depend_on_mapping_order() -> None:
    first = canonical_sha256({"txid": "a", "fee_sat": 1000})
    second = canonical_sha256({"fee_sat": 1000, "txid": "a"})
    assert first == second


def test_live_scann_adapter_does_not_require_scann_at_import_time() -> None:
    from agent_runtime.retrieval.bitcoin_scann_runtime import BitcoinScannRuntimeError
    assert issubclass(BitcoinScannRuntimeError, RuntimeError)


def test_rpc_config_rejects_non_http_endpoint() -> None:
    from agent_runtime.retrieval.bitcoin_rpc import BitcoinCoreRpcConfig, BitcoinCoreRpcError
    with pytest.raises(BitcoinCoreRpcError, match="HTTP"):
        BitcoinCoreRpcConfig("file:///tmp/bitcoin")


def test_rpc_client_never_constructs_without_credentials() -> None:
    from agent_runtime.retrieval.bitcoin_rpc import BitcoinCoreRpcClient, BitcoinCoreRpcConfig, BitcoinCoreRpcError
    import os
    os.environ.pop("BITCOIN_RPC_USER", None)
    os.environ.pop("BITCOIN_RPC_PASSWORD", None)
    client = BitcoinCoreRpcClient(BitcoinCoreRpcConfig("http://127.0.0.1:8332"))
    with pytest.raises(BitcoinCoreRpcError, match="credentials"):
        client._authorization()


def test_sqlite_store_resolves_intra_block_spend_and_enforces_single_spend(tmp_path) -> None:
    from agent_runtime.retrieval.bitcoin_canonical_store import BitcoinCanonicalStore, BitcoinStoreError
    db = tmp_path / "bitcoin.sqlite"
    store = BitcoinCanonicalStore(str(db))
    store.initialize()

    height0 = {
        "height": 0,
        "hash": "b" * 64,
        "time": 0,
        "nonce": 0,
        "bits": "1d00ffff",
        "tx": [{
            "txid": "1" * 64,
            "version": 2,
            "locktime": 0,
            "vin": [{"coinbase": "0101", "sequence": 0}],
            "vout": [{"value": "1.00000000", "n": 0, "scriptPubKey": {"type": "p2pk"}}],
        }],
    }
    height1 = {
        "height": 1,
        "hash": "a" * 64,
        "previousblockhash": "b" * 64,
        "time": 1,
        "nonce": 0,
        "bits": "1d00ffff",
        "tx": [
            {
                "txid": "c" * 64,
                "version": 2,
                "locktime": 0,
                "vin": [{"coinbase": "0202", "sequence": 0}],
                "vout": [{"value": "1.00000000", "n": 0, "scriptPubKey": {"type": "p2pk"}}],
            },
            {
                "txid": "d" * 64,
                "version": 2,
                "locktime": 0,
                "vin": [{"txid": "c" * 64, "vout": 0, "sequence": 1}],
                "vout": [{"value": "0.99999000", "n": 0, "scriptPubKey": {"type": "p2wpkh"}}],
            },
        ],
    }

    store.ingest_rpc_block(height0)
    store.ingest_rpc_block(height1)

    assert store.resolve_prevout("c" * 64, 0).value_sat == 100_000_000
    assert store.resolve_prevout("d" * 64, 0).value_sat == 99_999_000

    duplicate = {
        "height": 2,
        "hash": "e" * 64,
        "previousblockhash": "a" * 64,
        "time": 2,
        "nonce": 0,
        "bits": "1d00ffff",
        "tx": [
            {
                "txid": "9" * 64,
                "version": 2,
                "locktime": 0,
                "vin": [{"coinbase": "0303", "sequence": 0}],
                "vout": [{"value": "1.00000000", "n": 0, "scriptPubKey": {"type": "p2pk"}}],
            },
            {
                "txid": "f" * 64,
                "version": 2,
                "locktime": 0,
                "vin": [{"txid": "c" * 64, "vout": 0, "sequence": 1}],
                "vout": [{"value": "0.99999000", "n": 0, "scriptPubKey": {"type": "p2wpkh"}}],
            },
        ],
    }
    with pytest.raises(BitcoinStoreError, match="already spent"):
        store.ingest_rpc_block(duplicate)


def test_chain_indexer_is_resumable_from_store_height() -> None:
    from agent_runtime.retrieval.bitcoin_chain_indexer import BitcoinIngestResult
    assert BitcoinIngestResult(0, 0, 0, {}, "").blocks_ingested == 0


def test_bitcoin_index_manifest_is_shard_contiguous_and_content_addressed() -> None:
    from agent_runtime.retrieval.bitcoin_index_manifest import (
        BitcoinIndexManifestError,
        BitcoinIndexShardManifest,
        create_manifest,
    )
    shards = (
        BitcoinIndexShardManifest(
            shard_id="shard-0000",
            block_start=0,
            block_end=100,
            transaction_start=0,
            transaction_end=2,
            vector_count=2,
            corpus_hash="a" * 64,
            index_hash="b" * 64,
            index_relative_path="indices/0000",
        ),
        BitcoinIndexShardManifest(
            shard_id="shard-0001",
            block_start=101,
            block_end=200,
            transaction_start=2,
            transaction_end=4,
            vector_count=2,
            corpus_hash="c" * 64,
            index_hash="d" * 64,
            index_relative_path="indices/0001",
        ),
    )
    manifest = create_manifest(
        source_graph_hash="e" * 64,
        corpus_hash="f" * 64,
        source_revision="1" * 40,
        block_start=0,
        block_end=200,
        transaction_count=4,
        vector_dimension=40,
        scann_version="1.4.2",
        distance_metric="squared_l2",
        normalization="l2",
        cpu_architecture="x86_64",
        shard_transaction_limit=2,
        shards=shards,
    )
    assert len(manifest.shards) == 2
    assert len(manifest.manifest_hash) == 64
    assert manifest.manifest_hash == manifest.manifest_hash

    with pytest.raises(BitcoinIndexManifestError, match="contiguous"):
        create_manifest(
            source_graph_hash="e" * 64,
            corpus_hash="f" * 64,
            source_revision="1" * 40,
            block_start=0,
            block_end=200,
            transaction_count=4,
            vector_dimension=40,
            scann_version="1.4.2",
            distance_metric="squared_l2",
            normalization="l2",
            cpu_architecture="x86_64",
            shard_transaction_limit=2,
            shards=(shards[0], BitcoinIndexShardManifest(
                shard_id="shard-0002",
                block_start=101,
                block_end=200,
                transaction_start=3,
                transaction_end=4,
                vector_count=1,
                corpus_hash="c" * 64,
                index_hash="d" * 64,
                index_relative_path="indices/0002",
            )),
        )
