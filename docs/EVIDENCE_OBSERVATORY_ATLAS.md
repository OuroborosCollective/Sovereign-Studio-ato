# Sovereign Evidence Observatory Atlas

## Purpose

The Observatory Atlas turns research material into inspectable, versioned evidence states. It is not a consensus engine, political position, identity classifier, or popularity-weighted truth system.

Core invariant:

`claim -> provenance -> evidence class -> proof receipt -> gate -> evidence passport -> public projection`

`SUPPORTED`, `REFUTED`, `UNPROVEN`, and `NOT_APPLICABLE` are evidence states. Publication means the state is reproducible and its boundaries are explicit; it does not mean every published claim is true.

## Truth boundaries

- Community engagement never changes truth state.
- Notion is a research workbench and candidate source, never canonical truth.
- Community submissions are always private `QUARANTINED` candidates.
- A candidate becomes `PUBLISHABLE` only after deterministic gate replay succeeds.
- `SUPPORTED` and `REFUTED` require a decisive proof receipt bound to the verdict basis.
- `UNPROVEN` can be publishable only when the unresolved evidence need is explicit and the uncertainty state is reproducible.
- Agreement between models never proves a claim.
- Geographic, stylistic, temporal, social, or linguistic correlation never proves a human identity.
- Map pins are emitted only for `geo.evidenceRole=material`. Context-only geography is not projected as proof geography.
- Source counts and media density are not independent-origin counts. Source lineage groups records by provenance origin family.
- The source-dependency tool is a simulation. Removing a source does not recompute a verdict.
- No raw provider credential is accepted through Observatory routes.

## State machine

1. `QUARANTINED/private`
   - Notion normalized import.
   - Community hint submission.
   - Failed or incomplete gate replay.
2. `PUBLISHABLE/public`
   - Claim fingerprint matches the candidate.
   - Evidence class, sources, provenance, timeline bindings, contradiction review, sensitivity review, proof receipts, verdict basis and Evidence Passport gates pass.
   - Case, gate and passport are hash-bound.
3. `PUBLISHED/public`
   - All gates are replayed immediately before export.
   - Exact data and manifest bytes are committed to the configured Hugging Face staging revision.
   - Exact files are read back at the returned commit OID and SHA-256 compared.
   - Only then is a publication receipt persisted and the case state changed to `PUBLISHED`.

## Evidence Time Machine / Atlas UI

Public route: `/observatory` or `/evidence-observatory`.

The Atlas provides:

- historical `asOf` filtering so future evidence is hidden from historical views;
- Evidence Density and contradiction density over time;
- Source Lineage grouped by independent origin family;
- world-map projection only for material geographic evidence;
- case hashes and Evidence Passport hash;
- case timeline and explicit `evidenceNeeded` list;
- pinboard for locally comparing public cases without changing server truth;
- Claim Genealogy / Information DNA when the case contains `claimGenealogy` edges;
- information-flow edges when the case contains `informationFlow` records;
- source-dependency simulation showing whether a source/receipt/origin/timeline dependency would break if one source were removed.

## Community intake

`POST /api/evidence-observatory/v1/submissions`

Requires an authenticated session. The request may contain project, title, claim, HTTPS source URL and a bounded note. The server always writes a private `QUARANTINED` candidate. The endpoint cannot publish, verify or promote truth.

## Notion intake

`POST /api/admin/evidence-observatory/v1/notion/import`

The endpoint accepts a bounded normalized Notion API export from an authenticated admin workflow. It does not accept raw Notion credentials. A candidate identity includes the Notion page identity and claim fingerprint. A changed claim therefore creates a new candidate identity rather than silently rewriting an already evaluated claim.

Direct Notion credential handling is intentionally not implemented in this module. A future direct sync must use a protected connector/credential lane and still terminate at the same `QUARANTINED` boundary.

## Verification gate

`POST /api/admin/evidence-observatory/v1/cases/<caseId>/verify`

Required evidence includes:

- exact normalized claim fingerprint;
- supported evidence class;
- `asOf` timestamp;
- explicit neutral/evidence-only method declaration;
- HTTPS source locators with content SHA-256 and observed timestamps;
- source provenance with origin family;
- bounded optional geography with material/context role;
- proof receipts with integrity, authentication declaration, claim binding and replay state;
- timeline events bound to known sources;
- contradiction review;
- sensitivity review including secret exclusion and redaction verification;
- verdict-basis source and proof-receipt bindings;
- decisive receipt for `SUPPORTED` / `REFUTED`;
- explicit missing evidence for `UNPROVEN`.

The gate emits `gateSha256`. The Evidence Passport emits `passportSha256`. The complete case emits `caseSha256` over payload, gate and passport.

## Hugging Face publication

`POST /api/admin/evidence-observatory/v1/publish/huggingface`

Default repository: `Thorsu/sovereign-evidence-observatory`.

Default revision: `staging-atlas`.

Direct `main` / `master` publication is forbidden by the integration helper. Authentication is delegated to the protected runtime identity resolved by `huggingface_hub`; no credential value crosses the Observatory function boundary.

Each batch writes:

- `staging/atlas-batches/<date>-<batchId>.jsonl`
- `staging/atlas-batches/<date>-<batchId>.manifest.json`

A successful API result is not accepted as sufficient evidence. Both files are downloaded at the returned commit OID and their exact SHA-256 values must match the pre-commit values before database state changes to `PUBLISHED`.

## Evidence Arena

The Arena reuses Sovereign's existing LLM execution path rather than creating a second provider/key system.

1. `GET /api/evidence-observatory/v1/arena/cases/<caseId>/request`
   - emits an evidence-discipline prompt and versioned public case data;
   - execution endpoint is the existing `/api/llm/chat`.
2. The client executes the selected existing Sovereign route/model at temperature 0.
3. `POST /api/evidence-observatory/v1/arena/score`
   - requires the exact `llmRequestId` to exist in `llm_usage_settlements` for the same authenticated user;
   - refuses non-final settlement states;
   - verifies supplied route/model identities when present;
   - hashes the model response and metrics;
   - stores a replay-safe run keyed by user + LLM request identity.
4. `GET /api/evidence-observatory/v1/arena/leaderboard`
   - ranks evidence discipline on versioned Observatory cases;
   - never claims to rank general model truthfulness.

Metrics include verdict agreement with the evidence case, correct abstention, citation precision, decisive-basis coverage, a deterministic evidence-bound unsupported-claim proxy, contradiction recall, and aggregate evidence score.

## Source dependency simulation

`GET /api/evidence-observatory/v1/cases/<caseId>/source-dependency?sourceId=<id>`

Returns:

- whether the removed source is part of the verdict basis;
- whether verdict-basis proof receipts depend on that source;
- remaining source and independent-origin counts;
- whether the removed origin still has another source representation;
- number of affected timeline events;
- deterministic analysis SHA-256;
- `simulationOnly=true` and `verdictRecomputed=false`.

## Database ownership

Migration `053_evidence_observatory_atlas.sql` owns:

- `evidence_observatory_cases`
- `evidence_observatory_publish_receipts`
- `evidence_observatory_arena_runs`

The migration is byte-equal in the canonical/deployment migration mirrors.

## Deployment / readback gates

Do not call the integration live until all of the following are evidence-backed on one exact revision:

1. Python contract tests pass.
2. Frontend Vitest/type/build checks pass in GitHub Actions.
3. Migration 053 applies successfully and schema reconciliation reports the three tables live.
4. Backend readiness reports migration 053 plus all three Observatory tables.
5. Container image digest and deployed source revision match the approved revision.
6. PatchMon fleet/health lanes are healthy for the exact deployment.
7. A real community submission proves `QUARANTINED/private` behavior.
8. A real verified case proves gate/passport/case hash replay.
9. A real Hugging Face staging batch proves commit + exact-byte readback before `PUBLISHED`.
10. A real Arena run proves LLM settlement identity and replay-safe score persistence.

Until these gates are read back, the repository implementation is not production runtime truth.
