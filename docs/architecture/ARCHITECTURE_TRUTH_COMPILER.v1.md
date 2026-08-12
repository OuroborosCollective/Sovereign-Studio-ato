# Sovereign Architecture Truth Compiler v1

The **Sovereign Architecture Truth Compiler (SATC)** is a deterministic, pre-effect decision boundary. It does not replace existing repository, workflow, permission, GitHub, deployment, database, or runtime owners. It compiles revision-bound evidence supplied by those owners and evaluates only whether a requested effect may continue on the same revision.

> A successful workflow, a healthy container, a static finding, or an LLM assessment is not an independently verified external effect.

## Contract scope

The v1 contract core is implemented in `tools/sovereign-chatgpt-mcp/architecture_truth_contract.py`. It performs no filesystem inspection, network call, database action, LLM invocation, repository mutation, or effect. The caller must supply independently collected evidence in the following canonical shape.

| Field | Binding rule |
|---|---|
| `repository` | Exact `owner/name` identity shared by policy, evidence, contract, and effect intent. |
| `repositoryRevision` | Full lowercase Git SHA shared by every compiled evidence item. |
| `architecturePolicySha256` | SHA-256 of canonicalized policy data only. |
| `evidenceSha256` | SHA-256 supplied by the independently responsible evidence collector. |
| `contractSha256` | SHA-256 of canonicalized contract data; no timestamps, prompts, file contents, tokens, or credentials enter it. |
| `decisionSha256` | SHA-256 of the immutable pre-effect decision projection. |

The initial policy resides in `config/architecture/sovereign-architecture-truth.v1.json`. Its mandatory same-revision evidence kinds are `architecture_inventory`, `architecture_drift_report`, `backend_assessment`, and `repository_snapshot`.

## Fail-closed decision model

| Condition | Verdict | Effect behavior |
|---|---|---|
| Different effect and contract revision | `REQUIRE_REVALIDATION` | Do not invoke the existing mutation adapter. Collect current evidence again. |
| Required runtime evidence is absent or not bound to the effect revision | `REQUIRE_REVALIDATION` | Do not deploy or claim a runtime effect. |
| Evidence contains a contradiction | `CONTRADICTED` | Block the requested effect. |
| Effect domain is not declared by policy | `DENY` | Block the requested effect. |
| All applicable invariants and evidence bindings hold | `ALLOW` | The existing canonical effect owner may be called; SATC still performs no effect. |

An `ALLOW` result is deliberately only a pre-effect authorization. The existing mutation adapter remains responsible for execution, and an independent target-system readback remains required before any result can become `VERIFIED`.

## Baseline evidence

The initial contract work was based on `origin/main` revision `c5fd0d82874e16937842f38d87b21e24220cdbf2`. The deterministic architecture radar executed on that exact revision recorded 95 backend endpoints, 91 frontend calls, 92 database tables, 49 workflow files, and 19 LLM/tool-boundary candidates. The resulting drift report contains 89 `P1` `CONTRACT_DRIFT` candidates and no `P0` or `P2` candidate. These are static candidates, not runtime truth.

The live backend reported source revision `6f00457ff0c4de1a43a9c5d150d3bca9c9e0e9c4` and a healthy readiness endpoint. That revision is an ancestor of `origin/main` but is not identical to the baseline revision. SATC therefore requires `REQUIRE_REVALIDATION` for a deployment targeting the new revision until an independently collected runtime readback reports exactly that revision.

## Evidence ownership

| Evidence surface | Existing owner | SATC role |
|---|---|---|
| Static architecture inventory | `deterministic_architecture_tools.py` | Bind its revision and digest. |
| Snapshot and drift report | `repository_skill_tools.py` | Bind their revision and digest. |
| Backend assessment | `enterprise_backend_tools.py` | Bind its revision and digest. |
| High-risk mutation evidence | `backend/agent_runtime/mutation_evidence_layer.py` | Remains the effect-path owner; SATC never executes its mutations. |
| Runtime health and deployment readback | Existing backend and deployment operators | Supply independently observed, exact-revision runtime evidence. |

## Testing

`tools/sovereign-chatgpt-mcp/tests/test_architecture_truth_contract.py` uses the actual checked-out Git revision and the versioned policy. It verifies deterministic hashes, missing evidence rejection, cross-revision rejection, runtime-revision revalidation, successful same-revision evaluation, and contradiction blocking.
