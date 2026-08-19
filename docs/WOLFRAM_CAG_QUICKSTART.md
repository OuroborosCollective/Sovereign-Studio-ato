# Wolfram CAG Developer Quickstart

**Status:** `IMPLEMENTED_IN_REPOSITORY` + locally `TESTED_AT_REVISION`. Not deployed, not runtime-verified.
**Parent epic:** #1457 — Wolfram CAG Foundation Tool Integration + Public Evidence Lab
**This slice:** #1465 — Developer Quickstart / Example Flow
**Truth boundary:** no live Wolfram CAG transport exists yet (#1458 is owner-provisioning work). Every example receipt therefore honestly reports `UNAVAILABLE` on the transport path while the deterministic comparison verdict shows what the verifier *would* conclude. Nothing in this quickstart fakes a live API call.

## What this is

The Wolfram CAG evidence lane counter-checks a claim (typically produced by an
LLM step) against a Wolfram computation result and emits a versioned,
hash-bound, secret-free receipt with one verdict. This quickstart lets an
external developer reproduce that flow locally with public benchmark cases —
no Sovereign credentials, no private infrastructure, no Wolfram account.

## Flow

```text
LLM claim
  -> CagClaim (bounded, hash-bound)
  -> CAG transport receipt (honest UNAVAILABLE until #1458)
  -> NormalizedCagResult (secret-free projection)
  -> verify_cag_claim -> WolframCagReceiptV1
  -> SUPPORTED | CONTRADICTED | INCONCLUSIVE | UNAVAILABLE
```

Layer separation: the OpenRouter/FreeLLM LLM steps produce the claim text; the
Wolfram CAG components counter-check it; the Sovereign runtime/Judge owns
downstream truth. A CAG receipt never verifies repository, deployment,
PatchMon or runtime state.

## Prerequisites

- Python 3.11+ (stdlib only; no pip install needed)
- A checkout of this repository
- No Wolfram account, no API keys, no Sovereign entitlements

Honest entitlement note: the live CAG transport requires owner-side Wolfram
provisioning (#1458), which is not available to external developers. The
public lane below is fully reproducible without it; it never claims more than
it can prove.

## Run your first claim check

From the repository root:

```bash
python scripts/run-wolfram-cag-benchmark.py --case cag-bench-001
```

Expected outcome: exit code `0` and a summary where

- `transport_verdict` is `UNAVAILABLE` (honest fail-closed: no provisioning),
- `comparison_verdict` is `SUPPORTED` (deterministic reference comparison).

Run all twelve public cases:

```bash
python scripts/run-wolfram-cag-benchmark.py
```

Machine-readable output only:

```bash
python scripts/run-wolfram-cag-benchmark.py --json
```

## Example receipts

Three complete, checked-in example receipts live under
`docs/examples/wolfram-cag/`:

| File | Case | Comparison verdict | Transport verdict |
| --- | --- | --- | --- |
| `quickstart-supported.receipt.json` | cag-bench-001 | `SUPPORTED` | `UNAVAILABLE` |
| `quickstart-contradicted.receipt.json` | cag-bench-002 | `CONTRADICTED` | `UNAVAILABLE` |
| `quickstart-inconclusive.receipt.json` | cag-bench-012 | `INCONCLUSIVE` | `UNAVAILABLE` |

They are regenerated deterministically and verified in CI. To regenerate or
check them:

```bash
python scripts/generate-wolfram-cag-quickstart-receipts.py          # write
python scripts/generate-wolfram-cag-quickstart-receipts.py --check  # verify in sync
```

The checked-in examples use sentinel identities (`quickstart-example` run id,
all-zero revision, empty `recorded_at`) so regeneration is byte-stable. A real
run must bind the actual Git revision:

```bash
SOVEREIGN_CAG_REVISION="$(git rev-parse HEAD)" \
  python scripts/run-wolfram-cag-benchmark.py --json
```

## Reading a receipt

Key fields of a `WolframCagReceiptV1` (see `quickstart-supported.receipt.json`):

- `schema_version` — `sovereign.wolfram-cag-receipt.v1`
- `verdict` — the transport verdict (`UNAVAILABLE` without provisioning)
- `finding_codes` — e.g. `unavailable_no_transport_receipt`
- `claim_hash`, `input_hash`, `result_hash` — SHA-256 over canonicalized,
  secret-guarded values
- `receipt_sha256` — the receipt's own hash identity
- `runtime_revision` — bound Git revision (sentinel in checked-in examples)
- `tolerance` — explicit absolute/relative tolerance for numeric comparisons
- `truth_notice` — the binding reminder that CAG evidence is a supplemental
  counter-check, never a self-asserted `VERIFIED`

## Verdict FAQ

- **SUPPORTED** — the deterministic comparison of claim vs. reference result
  agrees within the case's tolerance rules.
- **CONTRADICTED** — the comparison disagrees (e.g. `17 * 23 = 392`).
- **INCONCLUSIVE** — the claim cannot be parsed into a comparable form or no
  comparable result exists.
- **UNAVAILABLE** — no real transport receipt exists (no provisioning, no
  READY component, or transport failure). This is the honest fail-closed
  answer, not an error to hide.

The comparison verdict describes the deterministic reference comparison only.
The transport verdict is what a live deployment would report, and it stays
`UNAVAILABLE` until #1458 lands. The two are never conflated.

## Security, privacy and terms

- No secrets: the canonicalizer rejects secret-shaped keys and implicit time
  fields; the runner and the generator additionally scan every emitted receipt
  for secret-shaped values and fail non-zero on any hit.
- No private infrastructure: every benchmark case uses elementary public facts
  only (arithmetic, units, statistics, dates).
- Wolfram terms: the public lane performs no Wolfram API calls, so no Wolfram
  account or license terms apply to it. The provisioned path (#1458) will be
  governed by the owner's Wolfram entitlements.
- No wall-clock identity: `recorded_at` is optional provenance and is excluded
  from the receipt hash.

## Contributing a new public case

1. Read `backend/agent_runtime/wolfram_cag_benchmark_cases.py` and add a
   `BenchmarkCase` with a unique `cag-bench-NNN` id, a public, non-sensitive
   claim, the expected result type, a reference value and the expected
   comparison verdict.
2. Run `python scripts/run-wolfram-cag-benchmark.py --json` and confirm
   `verdictMismatches` is empty.
3. Run `python scripts/generate-wolfram-cag-quickstart-receipts.py --check` to
   confirm the checked-in examples are still in sync.
4. Open an issue with the *Wolfram CAG public benchmark case proposal*
   template (`.github/ISSUE_TEMPLATE/wolfram-cag-public-case.md`) describing
   the claim, the expected verdict and why the case is publicly reproducible.

## Reproducing a failure

If a case behaves unexpectedly, open an issue with the same template and
include: the exact command, the full `--json` output, your Python version and
the Git revision (`git rev-parse HEAD`). Do not include secrets, tokens or
private infrastructure details.
