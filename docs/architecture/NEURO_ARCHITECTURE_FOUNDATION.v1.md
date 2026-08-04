# Sovereign Neuro-Architecture Foundation v1

## Status

This document defines an **inactive architecture foundation**. It does not activate a runtime, replace an existing tool path, modify Docker, deploy to the VPS, authorize effects, or prove production health.

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
- `scripts/neuro-architecture-graph.mjs`

## Failure semantics

| Failure | Required behavior |
|---|---|
| invalid signature or revision | quarantine, append evidence, no effect |
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

## Current implementation boundary

This foundation intentionally does not include:

- Kafka or Redpanda deployment
- database migrations
- live API routes
- WebSocket activation
- Docker inclusion
- VPS changes
- PatchMon mutation
- LLM provider changes
- Quicknode endpoint creation
- Arelorian Wasd code
- merge or main push

## Next implementation slices

1. Expand the scientific source ledger with dated claims, source identity, anatomical level, and uncertainty.
2. Build a machine-readable region/nucleus/pathway graph and distinguish anatomical, functional, modulatory, and metaphorical edges.
3. Add property-based tests for lane transition closure, hash chains, replay, tick monotonicity, and side-channel independence.
4. Integrate read-only architecture sensors and compare the proposed lanes with existing ATO ownership surfaces.
5. Add bounded adapters behind feature flags only after exact-head CI and owner review.
6. Append both continuity ledgers byte-identically before creating a Draft PR.
7. Perform runtime, container, PatchMon, and immutable revision readback only after an approved deployment phase.
