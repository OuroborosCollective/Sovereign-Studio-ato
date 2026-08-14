# Sovereign Neuro-Architecture Foundation v1

## Status

This document defines the canonical foundation and the **repository-implemented Sovereign MCP runtime slice** built on it. The slice is part of the existing FastMCP process and Docker build; it does not create a second MCP server, registry, code server, approval system, provider route, or effect executor.

Repository implementation and tests do not prove that a particular image is deployed. Current activation must be read from `neuro_runtime_contract_status` and corroborated with the immutable image revision, MCP protocol/registry, container, and PatchMon readbacks. Until those agree, the correct status is `TESTED_AT_REVISION` or `DEPLOYED_UNVERIFIED`, never assumed production health.

The biological names in this document are explanatory aliases. Canonical software ownership remains technical and explicit.

## Non-negotiable project isolation

- **Sovereign Studio ATO** may use neuroanatomical terminology as an orchestration, observability, evidence, correction, and safety model.
- **Arelorian Wasd** remains a separate repository, runtime, persistence domain, and deterministic truth system.
- No shared database ownership, state authority, container identity, migration ownership, or canonical event stream is introduced.
- In Arelorian Wasd, LLMs, embeddings, vector retrieval, probabilistic ranking, and persistent memory remain outside the Tick/Chunk/Kappa-1000 truth boundary.

## Evidence classes

| Class | Meaning |
|---|---|
| E0 | Pure metaphor with no scientific equivalence claim |
| E1 | Plausible functional analogy, explicitly limited |
| E2 | Broadly supported functional neuroscience statement |
| E3 | Documented anatomical connection or circuit relationship |
| E4 | Reproducible formal or measured property with a defined method |

A software alias must never be upgraded from E0/E1 to E2-E4 merely because the implementation is working.

## Scientific grounding used for this foundation

### Connectome and network model

The NIH Human Connectome Project mapped macroscale structural and functional brain connectivity and established that architecture must be modeled as connected networks rather than isolated boxes. The software consequence is a directed multigraph with typed edges, not a one-region/one-function lookup table.

Primary reference:

- https://www.nimh.nih.gov/research/research-funded-by-nimh/research-initiatives/human-connectome-project-hcp

### Thalamus

The thalamus consists of many nuclei with differentiated sensory, motor, limbic, arousal, memory, and cortical relay relationships. Treating it as one undifferentiated gateway would be scientifically misleading.

Software interpretation: `neuro.thalamic-router` classifies and routes validated events but does not decide domain truth.

References:

- https://www.ncbi.nlm.nih.gov/books/NBK542184/
- https://www.ncbi.nlm.nih.gov/books/NBK549908/

### Hypothalamus

Hypothalamic nuclei regulate endocrine, autonomic, and homeostatic functions and connect with the brainstem, cortex, hippocampus, amygdala, thalamus, pituitary, and retina through distinct pathways.

Software interpretation: `neuro.homeostasis-controller` observes capacity, latency, queue pressure, health, and safety thresholds. It may throttle or quarantine but cannot fabricate a healthy result.

Reference:

- https://www.ncbi.nlm.nih.gov/books/NBK525993/

### Amygdala

The amygdala is a collection of nuclei connected with cortical, hypothalamic, thalamic, hippocampal, pallidal, and striatal systems. It participates in salience, stress-related responses, learning, memory, attention, and behavioral regulation. It is not a simple binary fear switch.

Software interpretation: `neuro.reversible-safety-reflex` may produce only bounded, reversible protection after source authenticity, revision binding, and replay checks.

Reference:

- https://www.ncbi.nlm.nih.gov/books/NBK537102/

### Hippocampal and medial temporal systems

Memory processing involves registration, storage, retrieval, and connections with wider cortical and limbic systems. The hippocampus is not equivalent to a vector database.

Software interpretation: `neuro.evidence-consolidation` persists provenance-bound evidence and references. Vector similarity remains a non-canonical side channel.

Reference:

- https://www.ncbi.nlm.nih.gov/books/NBK482171/

### Basal ganglia

Basal-ganglia circuits participate in action selection, inhibition, motor control, reward, cognition, and loops through thalamic and cortical regions.

Software interpretation: a later `neuro.procedure-selection` lane may rank already authorized procedures, but repeated success does not convert a routine into truth or bypass policy.

References:

- https://www.ncbi.nlm.nih.gov/books/NBK537141/
- https://www.ncbi.nlm.nih.gov/books/NBK536995/

### Cerebellum

The cerebellum coordinates timing, balance, motor learning, and correction by comparing intended movement with incoming feedback. It does not initiate the motor command itself.

Software interpretation: `neuro.execution-correction` compares planned action, authorized action, observed effect, and expected projection. Divergence produces evidence and quarantine, not retrospective success.

References:

- https://www.ncbi.nlm.nih.gov/books/NBK538167/
- https://www.ncbi.nlm.nih.gov/books/NBK542179/

### Distributed cognitive networks

Default-mode, salience, executive, attention, sensory, and motor networks are distributed and dynamic. The default network itself contains multiple interwoven networks. Therefore ATO must avoid assigning planning, salience, introspection, or executive control to one code module solely because of a biological label.

References:

- https://www.nature.com/articles/s41583-019-0212-7
- https://www.nature.com/articles/nrn3857
- https://www.nature.com/articles/s41598-017-16789-1

## Wolfram findings bound to this foundation

Wolfram entity data provides structured surfaces for anatomical structures, neuron types, cognitive tasks, neuronal inputs, neuronal outputs, neurotransmitters, firing properties, and defining criteria.

The first evaluated cerebellum query returned ten neuron classes:

1. Cerebellar deep nucleus principal neuron
2. Cerebellum Golgi cell
3. Cerebellum Lugaro cell
4. Cerebellum Purkinje cell
5. Cerebellum basket cell
6. Cerebellum candelabrum cell
7. Cerebellum granule cell
8. Cerebellum nucleus reciprocal projections neuron
9. Cerebellum stellate cell
10. Cerebellum unipolar brush cell

The result demonstrates why the architecture must not model the cerebellum as one homogeneous unit. Cellular detail remains research data and is not copied directly into runtime control logic.

Wolfram also produced a preliminary software-graph betweenness result in which the routing and deterministic-core nodes were the most central nodes of the small sample graph. This is a design warning, not proof: these nodes require redundancy, bounded responsibility, and explicit failure behavior because an overly central component becomes a control-plane bottleneck.

## Canonical lane model

| Lane | Biological alias | Canonical responsibility | Canonical truth? |
|---|---|---|---|
| `sensory-intake` | peripheral sensory intake | authenticate, validate, canonicalize input | Input evidence only |
| `thalamic-routing` | thalamic relay | classify and route without deciding domain truth | No |
| `reflex-safety` | amygdaloid safety reflex | bounded reversible protection | Only signed protection decision |
| `deterministic-verification` | formal executive verification | revision, policy, hash, sequence, causal and projection checks | Yes |
| `cognitive-side-channel` | distributed cognitive networks | LLM, vector, anomaly and hypothesis generation | Never |
| `evidence` | evidence consolidation | append provenance, hashes, test and readback identities | Yes |
| `persistence` | long-term storage substrate | durable event and projection storage | Storage is not truth by itself |
| `cerebellar-correction` | cerebellar comparison | compare intended, authorized, executed and observed outcomes | Derived verification |
| `motor-authorization` | motor release gate | authorize a real effect only after core proof | Yes |
| `homeostasis` | hypothalamic regulation | health, pressure, rate, backpressure and safe degradation | No fabricated green state |
| `quarantine` | protective isolation | preserve evidence and block propagation | No domain effect |

## Required event identity

Every event crossing a canonical boundary must bind at least:

- schema version
- system identity
- exact repository revision
- policy SHA-256
- event identity
- lane
- integer tick
- monotonic sequence
- payload SHA-256
- causal-parent SHA-256
- previous-evidence SHA-256
- producer identity
- canonical/non-canonical classification

The first implementation is located in:

- `src/features/product/runtime/neuroArchitectureContract.ts`
- `backend/agent_runtime/neuro_architecture_contract.py`
- `scripts/sovereign-backend/agent_runtime/neuro_architecture_contract.py`
- `tools/sovereign-chatgpt-mcp/neuro_architecture_contract.py`
- `scripts/neuro-architecture-graph.mjs`

The three Python copies are governed mirrors and must remain byte-identical. The MCP parity test imports the backend owner and MCP mirror and compares both file bytes and canonical envelope output.

## Implemented MCP runtime slice

| Principle | Live-path implementation | Authority boundary |
|---|---|---|
| Event/delta processing | `ChangeEvent`, `DeltaDetector`, `RelevanceGate`, append-only `NeuromorphicLedger`, and incremental tool-outcome projections | Unknown event kinds fail closed; a delta receipt cannot execute an effect |
| Time as data | `TemporalEnvelope` binds integer tick, per-source sequence, UTC event time, and derived `deltaMs`; bounded temporal windows are hash-bound | Wall time is evidence data, not sequence authority |
| Sparse capability gating | The existing live-registry predictive router selects a bounded advisory tool subset; `neuro_event_route_preview` exposes the combined candidate path | The static Teacher catalog is not imported and routing never activates a tool automatically |
| Compute near data | SQLite WAL projections remain beside MCP state; existing repository intelligence continues to query its revision-bound local index and returns bounded snippets/hashes | No second datastore owner or broad data-copy service is introduced |
| Edge/sensor preprocessing | `QuantizedSpikeFilter` performs deterministic integer leak/integrate/fire filtering in preview and produces uncertain, proposal-only output | It is not a sensor authenticity layer and cannot become canonical truth |
| Hybrid two-lane runtime | Sparse routing produces a `CandidateReceipt`; the Foundation lane verifies an allowlisted domain contract and persists a separate hash-chained decision receipt; existing operating-profile, toolchain, broker, and target readback paths remain effect authority | Foundation always returns `mayExecute=false`; tool success is recorded only after the existing call returns and never overrides target readback |

The five additive MCP tools are:

- `neuro_runtime_contract_status`
- `neuro_event_route_preview`
- `neuro_event_commit`
- `teaching_package_assess`
- `teaching_lesson_simulate`

`neuro_event_commit` is an idempotent local-state mutation and therefore remains covered by the existing automatic operating-profile mutation gate and persistent outcome tracker. The other four tools are effect-free and are excluded from both persistent wrappers. More generally, every tool with `readOnlyHint=true` remains free of ranking and neuromorphic state writes. Only mutating outcomes enter the incremental persistent projection; bounded log scans are reserved for startup/crash recovery.

## Foundation verification contract

The Foundation is a deterministic verification adapter, not another event authority. It accepts only explicitly registered domain kinds, verifies the embedded canonical evidence envelope and source `ChangeEvent` hash, and returns one of `accepted`, `quarantined`, or `rejected`. Unknown kinds, stale or malformed bindings, contradictions, unverifiable candidate evidence, and hash mismatches never fall back to a generic accept path.

Foundation decisions and change events use separate SQLite WAL ledgers because they represent different evidence records. Both are transactional, hash-chained, replay-checked, and independently readable. Neither ledger can authorize or perform an external effect.

The two ledgers are not described as one atomic transaction. A durable admission
intent binds the exact preview, classification, live-registry (or canonical
no-registry discard) evidence, Foundation decision, NMC receipt and Foundation
receipt. A crash may leave that intent in `pending`; status reports recovery
pending and an exact retry resumes idempotently. It never fabricates a completed
cross-ledger commit.

Status opens both ledgers in strict read-only mode and uses their canonical
semantic verifiers, including schema identity, event/receipt chains,
projections, metrics and admission bindings. SQLite `quick_check` alone is not
treated as semantic integrity evidence. Global and tool-outcome event/byte
quotas bound persistent growth; a new admission stops before its intent or
event is written when the global quota is exhausted, while an exact replay
remains readable.

## Failure semantics

| Failure | Required behavior |
|---|---|
| invalid envelope or revision | return bounded quarantine evidence without persistence or effect |
| replay or sequence gap | quarantine, no inferred repair |
| stale policy | block authorization |
| side-channel timeout | continue canonical verification without the suggestion |
| side-channel marked canonical | contract failure |
| motor result diverges | append divergence, halt further effect, require correction |
| runtime readback unavailable | status remains unknown or blocked, never green |
| broker or persistence outage | retain bounded local evidence if supported; otherwise safe halt |

## Quicknode boundary

Quicknode is not part of this foundation. A blockchain endpoint would only be justified for an independently reviewed external anchoring requirement. The attempted endpoint inventory returned HTTP 403 because the configured API key was rejected. No endpoint, security rule, rate limit, chain, or billing state was changed.

## Aha and Speechify boundary

Aha remains a later product/research-organization surface if a concrete connected action becomes available. It is not a truth source.

Speechify is reserved for a later narrated deep dive after the scientific atlas and architecture report are stable. Audio narration is a presentation artifact and does not change evidence status.

## Clean-room and archive provenance

The implementation is a clean-room adaptation of the supplied functional requirements and the repository's existing canonical contracts. No Python bytecode, Docker stack, static 92-action catalog, private prompt, credential, or independently packaged runtime from the supplied archives is copied into the product. The archives contained no accepted license grant for source import, so they remain audit evidence only.

Audit-bound attachment hashes:

- Foundation/Brain candidate: `4178d3139be11ae66f8e0fe89f31595b277f906c8cf060fd16c1f5b0a3f6493d`
- logic-first extension: `13d94b5686e4b990c3ebf7131cd90b3c73f8299de9bcd81498fef85f38ece010`
- Teacher candidate: `0daea330b35c1e2a32fdb22b94e6cfef1d89a1a4d093b9879556e8ce769d9795`
- revision-bound live MCP comparison export: `5b604c4fd7cd80ce21af8dbaaf8b8fc05407ec39158ed8aedb4f85765d38c489`

The neuromorphic-computing preprint informs principle-level hybridization only. It is not treated as proof that this software is biologically equivalent, and no spiking neural network or specialized neuromorphic hardware is claimed.

## Deliberate exclusions and next slices

- No Kafka/Redpanda, second Postgres, second MCP gateway, WebSocket, or new host port.
- No automatic execution from sparse candidates and no bypass of owner approval, exact revision, policy, effect, evidence, or readback gates.
- Teaching accepts only a repository-local regular source whose workspace-safe path, bytes, SHA-256 and excerpt are independently read and bound, its documented license/policy identifiers, and its supported bounded JSON-Schema subset. Remote or otherwise non-local provenance cannot self-assert repository trust; unknown, forbidden, unverifiable or unsupported contracts fail closed.
- No LiteLLM route; paid inference remains direct OpenRouter and free inference remains direct FreeLLM/Revolver.
- No Quicknode endpoint, Aha/Speechify authority, or Arelorian Wasd code/state.
- A real external sensor/edge adapter remains a later, source-authenticated and backpressure-aware slice; the current spike filter is only the deterministic local preprocessing primitive.
- General near-data workers beyond existing Repository Intelligence and local SQLite projections require their own datastore-owner contract.
- Runtime claims require exact-head CI, immutable image publication, controlled deployment, and revision/digest/protocol/registry/container/PatchMon readback.
