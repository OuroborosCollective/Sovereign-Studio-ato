# Bitcoin Graph × ScaNN × Wolfram Evidence Lane v1

**Status:** IMPLEMENTED_IN_REPOSITORY; live Bitcoin Core, ScaNN index, Wolfram transport and Notion writeback are not yet runtime-verified by this work block.

## Purpose

Build one internal research lane over the Bitcoin blockchain that can ingest the canonical chain once, represent exact transaction/UTXO relationships as a deterministic graph, derive a fixed structural feature vector, use ScaNN to retrieve candidates at scale, exactly rescore them, and use bounded Wolfram CAG computations as supplemental mathematical counter-checks.

The lane is designed for Satoshi/Bitcoin research but does not encode an attribution rule. Similarity, shared control evidence, address reuse, mining patterns, or graph proximity remain observations requiring independent interpretation and evidence.

## Canonical data path

Bitcoin Core
  → canonical block + transaction ingest
  → injected prevout resolver
  → deterministic UTXO / transaction graph
  → exact satoshi amounts, spend edges, chronology and fees when inputs are resolved
  → fixed structural feature vector
  → existing revision-bound ScaNN manifest/index
  → ANN candidate set
  → exact deterministic rescore
  → bounded Wolfram CAG counter-checks
  → evidence receipt / Notion Claims & Evidence Ledger

Bitcoin Core is the live source boundary. Wolfram also exposes Bitcoin blockchain/block/transaction/address analysis capabilities, but the production design keeps the full-node-derived canonical dataset separate from supplemental calculations.

## Truth boundaries

### Bitcoin / graph layer

The graph is the canonical analytical projection. A transaction input points to a previous transaction output. The fee is calculated exactly as: fee_sat = sum(prevout.value_sat) - sum(output.value_sat). That value is unavailable until prevout values are resolved.

BTC decimal strings are converted with exact decimal arithmetic and never by floating-point multiplication.

### ScaNN layer

ScaNN is not a database of blockchain truth. It is a derived approximate vector-search layer. Every candidate remains tied to the existing revision-bound manifest and is exactly rescored against canonical vectors.

The invariant is: ScaNN retrieval is not an evidence verdict.

ANN score is retained only as a retrieval observation. Exact distance is recomputed independently. Candidate recall is measured against the brute-force reference path already present in the repository.

### Wolfram CAG layer

The existing CAG lane is supplemental and explicitly cannot self-assert VERIFIED. Bitcoin-specific expressions therefore operate on small integer observations such as fee conservation, block-height chronology and unique-spend counts.

The expression builder is separate from the transport adapter. A real provider response must later be bound to the real CAG transport receipt; no fake provider result is generated here.

## Feature vector

transaction_feature_vector() produces exactly 40 L2-normalized structural dimensions:

- input/output counts
- input/output/fee value scales
- fee rate, vsize and weight
- version, locktime and coinbase flags
- input/output ratios
- value entropy
- min/max normalized values
- normalized script-type distributions for inputs and outputs

The vector is a search representation, not a replacement for exact fields. The canonical transaction retains txid, block height/hash/time, prevouts, values, scripts, outputs, weight and vsize.

For mining/early-era studies, additional feature families can later include coinbase script bytes, nonce/bits, height/time deltas, spend latency, address reuse counts, consolidation degree, ancestry/descendant depth and graph motifs.

## Provenance contract

A future production search receipt should carry:

- source chain snapshot / block-range identity
- canonical graph snapshot hash
- transaction content hash
- feature-vector hash
- ScaNN manifest ID and total hash
- ANN candidate IDs and scores
- exact-rescore receipt hash
- Wolfram CAG transport receipt hash when a real call is made
- independent evidence references written to the research ledger

Credentials, provider secrets, authorization headers and raw provider payloads do not belong in the research graph.

## Scale strategy

bitcoin_rpc.py fetches full blocks but deliberately does not issue one getrawtransaction request for every input. Historical ingestion should maintain a local canonical UTXO resolver updated as blocks stream in.

This keeps input-value/fee recovery linear in blockchain data instead of turning every input into another network request.

A practical deployment shape is: Bitcoin Core → append-only block store → UTXO state → analytical tables, with graph adjacency, feature vectors and the ScaNN index derived from the same canonical stream.

The storage engine is intentionally not hard-coded. PostgreSQL, DuckDB, ClickHouse, a KV store, object storage or a graph database can sit behind the contracts without changing the truth boundary.

## Initial research corpus

The first benchmark corpus should include the already audited early-chain cases:

- Block 9 reward / 12cb branch
- Block 360 Coinbase and its later consolidation
- Block 496 61-BTC consolidation
- the 12 dormant March-2010 rewards moved on 2026-09-05
- 1BDv and the linked early-address descendants documented in the research archive

The initial question should be structural: which transactions have the closest structural mining/transaction profiles to a selected reference? The result must not automatically become a person-identity or Satoshi attribution claim.

## Current implementation

Canonical modules:

- backend/agent_runtime/retrieval/bitcoin_rpc.py
- backend/agent_runtime/retrieval/bitcoin_graph.py
- backend/agent_runtime/retrieval/bitcoin_scann.py
- backend/agent_runtime/retrieval/bitcoin_wolfram_contract.py

Shipping mirrors:

- scripts/sovereign-backend/agent_runtime/retrieval/bitcoin_rpc.py
- scripts/sovereign-backend/agent_runtime/retrieval/bitcoin_graph.py
- scripts/sovereign-backend/agent_runtime/retrieval/bitcoin_scann.py
- scripts/sovereign-backend/agent_runtime/retrieval/bitcoin_wolfram_contract.py

Regression:

- backend/tests/test_bitcoin_graph_scann_wolfram.py

The existing ScaNN manifest/exact-rescore modules remain the general retrieval infrastructure; this Bitcoin lane specializes them instead of replacing them.

## Verification state

Repository verification in this block is limited to source-level inspection and construction of the isolated feature branch. Runtime verification still requires focused CI, production-mirror parity, a real Bitcoin Core endpoint and canonical UTXO resolver, an actual ScaNN build/readback, a real Wolfram CAG transport receipt, and Notion evidence writeback/readback.

No successful external runtime call is inferred from code existence alone.
