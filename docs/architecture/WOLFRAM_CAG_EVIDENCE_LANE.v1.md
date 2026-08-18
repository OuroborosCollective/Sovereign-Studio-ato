# Wolfram CAG Evidence Lane v1

**Status:** `IMPLEMENTED_IN_REPOSITORY` + locally `TESTED_AT_REVISION`. Not deployed, not runtime-verified.
**Baseline revision:** `5dbe8a750b0d40f11cc3800ea091db945c9d2a49`
**Parent epic:** #1457 — Wolfram CAG Foundation Tool Integration + Public Evidence Lab
**This slice:** #1460 — Deterministic claim verification + CAG evidence receipts (+ public benchmark fixtures for #1464)

## Purpose

This lane turns a bounded, secret-free CAG transport result (produced by the
#1459 adapter) into a versioned, hash-/revision-bound `WolframCagReceiptV1`
that answers one question for an agent claim:

> Is this claim **SUPPORTED**, **CONTRADICTED**, **INCONCLUSIVE** or **UNAVAILABLE**?

It is the deterministic evidence/judge slice of the CAG epic. It deliberately
does **not** create a second tool registry, a second permission runtime, or a
new truth authority, and it can never self-assert `VERIFIED`.

## Flow

```text
mission / LLM claim
  -> CagClaim (bounded, verifiable, hash-bound)
  -> CAG component transport receipt (#1459)
  -> NormalizedCagResult (secret-free projection)
  -> verify_cag_claim -> WolframCagReceiptV1
  -> SUPPORTED | CONTRADICTED | INCONCLUSIVE | UNAVAILABLE
  -> Sovereign Judge / downstream step
```

## Truth boundaries

- No `VERIFIED` verdict exists in `CagEvidenceVerdict`. `VERIFIED` stays
  reserved for the Sovereign proof-verdict / evidence lane.
- No mocks or stubs in the truth path. Without a real transport receipt
  (READY component, 2xx, non-`UNAVAILABLE` transport verdict) the honest
  verdict is `UNAVAILABLE`.
- No secret value is ever returned, logged, hashed or persisted. Inputs and
  results are canonicalized through a secret-guarded, allowlist-filtered
  canonicalizer that rejects floats, secret-shaped keys and implicit time
  fields.
- No wall-clock time is causal identity. `recorded_at` is optional,
  non-canonical provenance and excluded from the receipt hash.
- Float/precision differences are never claimed as byte equality; they are
  evaluated against explicit, per-result-type `ToleranceRule`s
  (`absolute` + `relative` + `significant_digits`).
- A contradiction stays a contradiction; the judge never smooths it away.
- CAG evidence can never replace PatchMon, GitHub, DB, container or runtime
  readback evidence.

## Components

- `backend/agent_runtime/wolfram_cag_evidence.py` (canonical) with byte-equal
  mirror at `scripts/sovereign-backend/agent_runtime/wolfram_cag_evidence.py`.
  Pure stdlib, no network/filesystem/clock/random access. Exposes
  `CagClaim`, `NormalizedCagResult`, `ToleranceRule`, `VerificationInput`,
  `WolframCagReceiptV1`, `verify_cag_claim`, `unavailable_receipt`,
  `compare_numeric_claim`, `compare_exact_claim`.
- `backend/agent_runtime/wolfram_cag_benchmark_cases.py` (+ mirror): 12 public,
  reproducible, non-sensitive `LLM claim -> CAG check -> evidence verdict`
  benchmark cases covering all four CAG components and the result types
  required by #1460.

## Receipt contract (`WolframCagReceiptV1`)

Schema `sovereign.wolfram-cag-receipt.v1`, contract `wolfram-cag-transport.v1`.
Binds: Sovereign run id, claim hash, runtime revision, component + contract
version, input text + input hash, domain/units/assumptions, timeout + output
limits, provider request/response ids, response status, component readiness,
result type + result hash, tolerance rule, latency + quota/cost class, verdict,
finding codes, bounded summary. `receipt_sha256` is the canonical, tamper-evident
hash (`recorded_at` excluded).

## Developer quickstart (#1465 slice)

```python
from backend.agent_runtime.wolfram_cag_evidence import (
    CagClaim, NormalizedCagResult, ToleranceRule, VerificationInput,
    DEFAULT_TOLERANCE_RULES, verify_cag_claim,
)

claim = CagClaim(
    claim_text="17 * 23 equals 391",
    claim_value="391",
    expected_result_type="exact_number",
    domain="arithmetic",
    sovereign_run_id="demo-run",
    runtime_revision="",  # or a full 40-char Git SHA
)
result = NormalizedCagResult(
    component_id="wolfram.cag.compute",
    result_type="exact_number",
    domain="arithmetic",
    assumptions=("decimal integers",),
    units="",
    reference_value="391",
    claim_value="391",
    provider_request_id="",
    provider_response_uuid="",
    response_status=200,
    component_ready=True,
    raw_payload={"expression": "17*23", "result": 391},
)
inputs = VerificationInput(
    claim=claim,
    input_text="evaluate 17*23",
    result=result,
    tolerance=DEFAULT_TOLERANCE_RULES["exact_number"],
    transport_receipt={"component_status": "READY", "verdict": "SUPPORTED", "response_status": 200},
)
receipt = verify_cag_claim(inputs)
print(receipt.verdict.value, receipt.receipt_sha256)
```

Without real CAG provisioning (#1458), omit `transport_receipt` (or pass
`None`); `verify_cag_claim` honestly returns `UNAVAILABLE`. No live HTTP is
executed.

## Verdict FAQ

| Verdict | Meaning |
| --- | --- |
| `SUPPORTED` | A real CAG result counter-checks the claim within the tolerance rule. |
| `CONTRADICTED` | A real CAG result contradicts the claim. Never smoothed away. |
| `INCONCLUSIVE` | Values missing/unparseable, or domain/result-type mismatch. |
| `UNAVAILABLE` | No real provisioning/transport evidence; component not entitled/ready. |

`VERIFIED` is intentionally absent and reserved for the Sovereign proof-verdict lane.

## Open items

- #1458 must supply real, secret-free entitlement evidence before live
  transport feeds real receipts into this lane.
- #1461 (agent/ToolChain/teaching routing) and #1462 (runtime health/PatchMon)
  build on the transport + this evidence lane and remain `PLANNED`.
- Public demo (#1464) needs real provisioning for `RUNTIME_VERIFIED` demos; the
  bundled benchmark cases are deterministic `IMPLEMENTED_IN_REPOSITORY`
  contract fixtures, not runtime proof.
