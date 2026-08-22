# Wolfram CAG Partner Analysis Ledger and Handoff Pack v1

**Status:** `IMPLEMENTED_IN_REPOSITORY` + locally `TESTED_AT_REVISION`. Not deployed, not runtime-verified.
**Baseline revision:** `20e357e960c0f1bb7865c3be5b82c122986cd442`
**Parent epic:** #1457 — Wolfram CAG Foundation Tool Integration + Public Evidence Lab
**This slice:** #1626 — Partner analysis ledger and documented handoff pack for Wolfram

## Purpose

Wolfram asked (per owner statement) for documentation of the analyses performed
with the provisioned CAG access. This lane turns that into a reproducible,
secret-free partner report path instead of loose chat prose or manual
screenshots. No chain-of-thought is ever exported: records bind verifiable
inputs, provider/receipt identities, results, derivations, assumptions, limits
and publication references only.

## Canonical analysis record

`build_partner_analysis_record` (schema
`sovereign.wolfram-cag-partner-analysis.v1`, contract
`wolfram-cag-v1-2026-08-21`) binds:

- component, contract version, normalized question and input SHA-256;
- optional repository/runtime revisions (exact 40-char Git SHAs), sovereign
  run id and toolchain step id;
- provider request id, response uuid, response SHA-256 and a credential
  **fingerprint** SHA-256 (never a raw secret);
- verdict `SUPPORTED | CONTRADICTED | INCONCLUSIVE | UNAVAILABLE`, derived
  conclusion, bounded assumptions/limitations/source refs;
- optional failure family, quota and rate-limit metadata (only when actually
  observed), evidence passport hash, HF publication ref and target revision.

`createdAt` is metadata, never causal identity: changing it alone cannot
change `analysisRecordSha256`. `SUPPORTED`/`CONTRADICTED` verdicts hard-require
provider evidence. `HF_PUBLISHED_VERIFIED` hard-requires a publication ref and
a target readback revision, and a record can only reach it through the explicit
`attach_hf_publication` re-derivation — never by self-promotion.

## Documentation classes

`PRIVATE_PROVIDER_EVIDENCE` → `PARTNER_REPORTABLE` → `PUBLIC_DERIVED_RECEIPT`
→ `HF_PUBLISHED_VERIFIED` (last only after #1507 target readback). No record
may promote itself to a more public class.

## Redaction gate

`assert_partner_safe` walks the complete outgoing projection before any
partner/public artifact leaves the system. It hard-rejects:

- Authorization headers, bearer tokens, `api_key`/`token`/`secret`/`password`
  assignments, GitHub token shapes, PEM blocks;
- email addresses (PII);
- raw prompt / chain-of-thought markers;
- forbidden key markers (`credential*`, `*token*`, `raw_prompt`, …).

The same guard runs at record build time, so secret-shaped material can never
enter the ledger in the first place.

## Deterministic partner handoff pack

`build_partner_handoff_pack(records)` produces
`sovereign.wolfram-cag-partner-handoff.v1`:

- summary: verdict counts, exercised components, failure families;
- per-analysis public projections (credential fingerprints removed) sorted by
  record hash;
- quota/rate-limit observations only when actually observed;
- evidence passport hashes (hash-only references via
  `evidence_passport_reference`; the ledger never becomes a second truth
  store) and HF publication refs;
- explicit limits and unresolved questions (limitations of
  `INCONCLUSIVE`/`UNAVAILABLE` records stay visible, contradictions are never
  smoothed away);
- `packSha256` over the canonical body excluding `createdAt`/`generatedAt`
  metadata, so the same record set always yields the same pack identity.

`render_partner_handoff_markdown(pack)` renders a deterministic
human-readable artifact suitable for the #1553 document/report adapter. Render
success is never verification.

## Runtime wiring

- `run_cag_canaries` (#1625 lane) automatically builds and persists one
  analysis record per executed canary, including quota/rate-limit metadata when
  the provider reports it and the failure family when the canary fails.
- `GET /api/internal/wolfram-cag/partner-report` (owner-bridge authorized)
  loads persisted records via `load_partner_analyses`, builds the pack and the
  markdown artifact, and fails closed with an error family on readback or
  redaction problems.
- Persistence is idempotent (`ON CONFLICT (record_sha256) DO NOTHING`) into
  `wolfram_cag_analysis_records` (migrations 058 + 059).

## Truth boundaries

- The ledger references canonical receipts/passports; it is not a second truth
  store.
- A tool result, model answer, UI state or render success can never create
  `RUNTIME_VERIFIED`.
- No record promotes itself; HF publication state requires real target
  readback.
- The pack contains no API keys, tokens, Authorization headers, private
  repository contents, private prompts/chain-of-thought, unrelated user data or
  unrestricted raw provider payloads.

## Components

- `backend/agent_runtime/wolfram_cag_partner_ledger.py` (canonical) with
  byte-equal mirror at
  `scripts/sovereign-backend/agent_runtime/wolfram_cag_partner_ledger.py`.
- `backend/wolfram_cag_runtime.py` (+ byte-equal mirror): canary persistence
  and partner-report endpoint.
- `backend/migrations/058_wolfram_cag_partner_analysis.sql`,
  `backend/migrations/059_wolfram_cag_partner_analysis_observations.sql`
  (+ mirrors).
- Tests: `backend/tests/test_wolfram_cag_partner_ledger.py`,
  `backend/tests/test_wolfram_cag_runtime.py`.
