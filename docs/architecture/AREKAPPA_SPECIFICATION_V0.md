# AREKappa Specification v0

Status: isolated research specification. It is not a production language, runtime, endpoint, deployment, or truth source.

Base revision: `620f256a401e12cfca980dc7d934da9187af2762`

## 1. Truth boundary

AREKappa separates two domains:

- **Deterministic truth domain:** state, actions, transitions, invariants, evidence, validation results, canonical encodings and receipts.
- **Probabilistic advisory domain:** inference, prediction, anomaly estimates and suggested actions.

Advisory output cannot mutate deterministic state. It must return as an explicit action and pass the same validation and evidence gates as any other action.

## 2. Layer geometry

The immutable axiom layer is `F0`. Runtime information is represented by six layers:

| Layer | Name | Domain |
|---|---|---|
| F0 | Axiom Layer | immutable specification |
| F1 | State Field | deterministic |
| F2 | Temporal Runtime | deterministic |
| F3 | Inference Topology | probabilistic, advisory only |
| F4 | Evidence Tensor | deterministic |
| F5 | Predictive Engine | probabilistic, advisory only |
| F6 | Validation Space | deterministic |

The runtime field is:

`F_t = (F1,F2,F3,F4,F5,F6)_t`

The transition contract is:

`(S_(t+1), O_t, R_t) = delta(S_t, A_t, E_t, V)`

where `V` binds the language, IR and runtime versions.

## 3. Exact Kappa number domain

`K = 1_000_000`

- `KappaPos := Integer[0..K]`
- `KappaSigned := Integer[-K..K]`
- `KappaCount := Integer[0..infinity]`
- `KappaRatio := exact Rational`
- `KappaTime := IntegerNanoseconds`
- `KappaHash := Hash256`

No implicit IEEE-754 floating-point operation is allowed in the truth domain. Conversion, rounding and saturation must be explicit and versioned.

## 4. Canonical normalization

For non-negative integer weights `w_i`, normalization returns `rho_i` such that:

- `rho_i in KappaPos`
- `sum(rho_i) = K`
- allocation uses exact quotient and remainder arithmetic
- residual units use largest remainder
- equal remainders are resolved by canonical layer ID

This algorithm is deterministic and total for a non-empty vector with positive total weight.

## 5. Coupling and information flow

`C` is a `6 x 6` matrix over `KappaSigned`.

`J_t = C_t rho_t`

The raw product is represented in an explicit widened integer domain (`KappaProduct`) before any rescaling. A standard stable profile should satisfy:

`sum_j abs(c_ij) <= K`

for every row. Exceeding this bound is not silently rejected, but is classified as an amplification zone requiring an explicit stability proof.

## 6. Evidence tensor

Evidence is modeled as `R_ijm(t)`:

- `i`: producing layer
- `j`: evaluated layer
- `m`: evidence channel

Initial channels:

`SourceCode, StaticAnalysis, UnitTest, IntegrationTest, RuntimeReadback, DatabaseReadback, ContainerHealth, ExternalReceipt, HumanApproval, Prediction`

Prediction can support an advisory claim, but cannot substitute for runtime, database or container readback.

Contradictory evidence produces an explicit unresolved conflict. It is never averaged into truth.

## 7. Validation spaces

Each validation rule defines a valid set:

`Omega_k = {x | g_k(x) <= 0}`

and a signed distance to its boundary:

`d_k(x) = SignedDistance(x, boundary(Omega_k))`

- positive: valid
- zero: boundary
- negative: invalid
- small positive: warning margin

A hard invariant violation dominates any aggregate score.

## 8. Observer graph

The observer uses a weighted hypergraph `G_t = (V_t,E_t,W_t)` over functions, files, states, actions, endpoints, tables, containers, tests, evidence and invariants.

The observer may use graph distance, reachability, discrepancy, critical subsets, centrality, cycle analysis and curvature-like metrics. These are analysis methods, not historical claims about one universal Erdős formula.

## 9. Canonical IR boundary

The primary product boundary is `kappa IR`, not surface syntax:

`Source -> Language AST -> Semantic Graph -> Topology Graph -> kappa IR -> Validation/Execution -> Receipt -> Target Adapter`

The IR must include:

- explicit types
- effect declarations
- deterministic transition definitions
- advisory projections
- canonical ordering
- exact numeric encodings
- evidence requirements
- invariant identifiers
- source maps and optional syntax trivia

## 10. Research and integration lanes

### Wolfram Research Lane

Allowed:

- symbolic definitions
- exact arithmetic
- normalization reference vectors
- matrix and graph analyses
- proof candidates
- counterexamples
- versioned reference outputs

Forbidden:

- production state mutation
- repository deployment
- database access
- container control
- endpoint publication
- automatic promotion of a result

### AREKappa Integration Lane

Allowed:

- schemas
- parsers for bounded subsets
- semantic graph construction
- IR serialization
- source-preserving metadata
- adapter prototypes
- deterministic fixtures

Forbidden until separately approved and evidenced:

- live execution endpoints
- production imports
- runtime registration
- database persistence
- MCP self-update
- autonomous patch application

## 11. Initial bounded language subsets

Python candidate subset:

- typed pure functions
- integers, booleans, strings and exact rational forms
- dataclasses with explicit fields
- conditions
- statically bounded loops
- explicit result values

TypeScript candidate subset:

- typed pure functions
- bigint and bounded integer wrappers
- interfaces and discriminated unions
- structured objects
- explicit Promise/effect contracts
- explicit Result values

Initially excluded:

- eval or generated execution
- monkey patching
- dynamic imports
- hidden global mutation
- implicit clock/random/network/filesystem effects
- unbounded dynamic Python semantics

## 12. Formal axioms v0

1. Identical canonical inputs, state and version produce identical canonical outputs and receipt hashes.
2. Every effect is explicit, authorized and evidence-bound.
3. Advisory computation cannot directly mutate truth state.
4. Unknown semantics fail closed.
5. Contradictory evidence remains contradictory until resolved by stronger bound evidence.
6. Hard invariant failure cannot be compensated by weighted averages.
7. Canonical serialization is injective over supported IR values.
8. Every rounding, tie-break and ordering rule is explicit and versioned.
9. Research output is not production evidence.
10. No runtime-success claim exists without revision-bound runtime readback.

## 13. Wolfram reference result

A stateless Wolfram Language reference evaluation confirmed for an example vector and coupling matrix:

- Kappa normalization sum exactly `1_000_000`
- largest-remainder allocation exact
- dimensions `6 x 6`, `6`, and `6`
- row L1 coupling bound satisfied
- deterministic layers `{1,2,4,6}`
- advisory layers `{3,5}`

This confirms only the supplied reference construction, not the complete language or runtime.
