# Memory.md — Sovereign Studio ATO

> Project-local, append-only integration memory for `OuroborosCollective/Sovereign-Studio-ato`.
> Historical bootstrap created 2026-09-09 from retrievable conversation and repository evidence.
> This is not a chat transcript and not a substitute for fresh runtime readback.

## Operating contract

1. Read this file before every N+1 integration work session.
2. After each completed work block, append exactly one concise entry before any merge.
3. Every entry records: task, decisions, touched surfaces, tests/evidence, what was learned, open points, and the next safe step.
4. Append-only: do not silently rewrite old entries. If an old statement is later disproved, append a correction entry that identifies the superseded statement and its evidence.
5. Keep projects isolated. Arelorian WASD, Echoes of Aurion, ARE Agent Studio and other repositories have their own `Memory.md`.
6. A green label is not proof. Product/runtime claims require exact-revision evidence, causal readback, and where applicable immutable image/digest identity.
7. No mock, stub, fake snapshot, fake success, or workflow shortcut may stand in for a truth-path runtime source.
8. Continuity is background history only; it is not a merge/release/truth authority. Revision/digest/readback boundaries are authoritative.
9. OpenRouter is the canonical paid provider path. Legacy LiteLLM assumptions are to be removed rather than preserved. Free/keyless routing must remain independently evidenced and fail closed.
10. PatchMon/fleet health, Docker/runtime identity and revision equality are checked after integrations that affect the running product.
11. Release mode remains Draft-PR-first / no automatic merge unless the owner explicitly authorizes a specific merge step.
12. Never place secret values, credentials or private tokens in this file.

## Entry format

```text
### YYYY-MM-DD — short title
Status: VERIFIED | PARTIAL | BLOCKED | HISTORICAL
Task:
Decisions:
Touched surfaces:
Evidence:
Learned:
Open:
Next safe step:
```

---

### 2026-07-28 — N+1 evidence-gated domain foundation
Status: VERIFIED repository merge; PARTIAL runtime rollout
Task: Integrate N+1 as a domain inside the existing Sovereign Flask/PostgreSQL architecture without creating a parallel product/runtime.
Decisions:
- Preserve identity, provenance and personality boundaries.
- Keep N+1 isolated from Arelorian WASD.
- No extra N+1 container and no simulated UI/runtime evidence.
- Learning/provenance remains receipt/evidence gated.
Touched surfaces:
- N+1 domain foundation.
- `docs/SOVEREIGN_LEARNING_LOGBOOK.md` and proven-learning manifest.
- Migration 043 / N+1 persistence surfaces.
Evidence:
- PR #1059 `feat(n+1): add evidence-gated domain foundation` merged.
- PR head `3864023588db7458b28246b0522a40e9e9f6cb4d`.
- Merge commit `fb2f747c75bdf8e3e930e61340d1422b8f6f294c`.
- Historical focused verification reported 57 tests green and migration preview without production write.
- Later runtime readback established migration 043 / 13 N+1 tables live, while API rollout was rolled back because the backend required FreeLLM receipt v2 and the producer still emitted v1.
Learned: A merged schema and live database objects do not prove the API/product path. Receipt producer and consumer versions must agree before activation.
Open: Receipt-version alignment and product-level API proof remained required after the database migration.
Next safe step: Re-read current producer/consumer contracts, bind tests to the exact current revision, then require runtime/API readback before claiming N+1 live.

### 2026-07-30 — Provider-neutral deterministic agent runtime hardening
Status: VERIFIED repository merge; no deployment claim in this block
Task: Harden the real agent execution path around registry contracts, immutable inputs, owner/revision binding and semantic stream validation.
Decisions:
- Validate schema type/required/enum/additionalProperties before effects.
- Reuse one immutable parameter snapshot for authorization, hashing and execution.
- Preserve owner and revision across continued streams.
- Route the existing ToolRunner / agent-job path through the provider-neutral kernel.
- Freeze execution results before evidence binding.
Touched surfaces: Provider-neutral agent runtime kernel, tool policy/routes, execution-result/evidence boundaries.
Evidence:
- PR #1091 merged.
- Head `9c4f74c6ef206c9589408b2ee832a03073bd95f8`.
- Merge commit `77904afea686a3fd61ef80a55aa32cbf752d0161`.
- 34 provider-neutral runtime tests, 32 agent-tool-policy tests, 12 route tests, 1 full runtime E2E, 7 continuity tests.
- Canonical/deployment mirror mismatch count 0; secret-rotation candidates 0; compile and `git diff --check` passed.
Learned: Hashing is insufficient if the authorized object can later mutate or stream transitions are semantically invalid. Evidence must bind the exact executed snapshot and transition sequence.
Open: This PR intentionally contained no deployment or MCP self-update.
Next safe step: Any later runtime activation must be checked against the merged revision and runtime identity, not inferred from the merge.

### 2026-07-31 — Compile-time contract-generation pilot planned
Status: HISTORICAL planning block
Task: Define a compile-time TypeScript contract-generation pilot for MCP/receipt boundaries.
Decisions:
- Generate/align runtime validators, JSON Schema and MCP input/output schemas.
- Bind contract/toolchain hashes.
- Keep schema-valid output `SUCCEEDED_UNVERIFIED` until external readbacks establish verification.
- Fail closed when the transformer/toolchain is absent.
Touched surfaces: Issue #1115 planning around MCP contracts, runtime validation and Python/Pydantic alignment.
Evidence: Historical issue-planning record; no live runtime success is claimed by this entry.
Learned: Type compatibility and schema conformance are boundary prerequisites, not runtime verification.
Open: Implementation and current relevance must be re-read from the present repository before reuse.
Next safe step: Treat this as design ancestry only; inspect current typed boundary ownership before integrating anything derived from it.

### 2026-08-01 — Deterministic Durable Memory Forest
Status: VERIFIED repository merge; production mutation not part of this block
Task: Replace the earlier Durable Memory draft with a deterministic, append-only, provenance-bound implementation.
Decisions:
- Content-addressed/reproducible leaf and retrieval-pack identities.
- Deterministic candidate ordering.
- Fail-closed trust graph `REPORTED -> OBSERVED -> VERIFIED`.
- Receipts required for observed, verified, contradicted and invalidated evidence.
- SQL append-only enforcement with `ON DELETE RESTRICT`, UPDATE/DELETE blockers and RLS without permissive policy until runtime identity is proven.
Touched surfaces: Durable Memory Forest logic, migration/persistence contracts, canonical/deployment mirrors.
Evidence:
- PR #1143 merged.
- Head `d83029af4c5b666a552e0a46efb3a18b7ae8f27a`.
- Merge commit `1456794b178d38b835d47132e7575a25e850363b`.
- 62 targeted tests.
- Real isolated PostgreSQL migration preview succeeded and fully rolled back; no production mutation.
- CODEOWNERS pass; mirror mismatch 0; secret triage had no rotation candidates.
Learned: Random UUID identity and policy-only append semantics contradict deterministic memory. Identity and immutability must be structurally enforced.
Open: The new tables still required a separately authorized production migration/apply and runtime readback.
Next safe step: Before relying on Durable Memory, resolve current schema/runtime identity and verify the relevant tables/constraints live.

### 2026-08-01 — Environment-bound MCP execution
Status: VERIFIED repository merge; runtime persist-before-effect still required separate proof
Task: Replace the earlier MCP-execution draft with deterministic, environment-/principal-/egress-bound receipts.
Decisions:
- Content-address Principal, Credential, Egress, Installation and Execution receipts.
- Require environment/revision/principal binding.
- Hostname allow only with canonical public DNS-IP evidence; bind resolved IP into receipt.
- Anonymous credentials cannot authorize mutation.
- Enforce cross-receipt constraints, append-only SQL, `ON DELETE RESTRICT` and RLS without permissive policy.
Touched surfaces: MCP execution boundary, egress decision/receipts, migration 049, canonical/deployment mirrors.
Evidence:
- PR #1144 merged.
- Head `cce3308908b454ed0c096f2ddc8487916ea40184`.
- Merge commit `ade005a68e3521f0a601af8e807f65c5b2ba86c9`.
- 60 targeted tests.
- Isolated PostgreSQL migration preview + complete rollback; no production mutation.
- Mirror mismatch 0; no secret findings in changed domain paths; no UUID remainder in Python core and no `NOW()` in migration 049.
Learned: An egress decision receipt does not prove the runtime persisted it before performing the effect.
Open: Persist-before-effect ordering and live runtime integration remained separately provable obligations.
Next safe step: For any MCP mutation claim, require actual environment principal, receipt chain and effect/readback from the same run.

### 2026-08-01 — Free/paid routing evidence separation
Status: PARTIAL
Task: Diagnose FreeLLM/Revolver/OpenRouter availability without conflating provider funds, user credits and route readiness.
Decisions:
- Keep provider account funding separate from product-user `provider_funded_credits`.
- Do not mark a paid route unavailable merely because a test user receives internal-credit HTTP 402.
- Keyless/free readiness requires real canaries; no fake key or SQL readiness patch.
Touched surfaces: FreeLLMAPI/Revolver routing, OpenRouter paid path, internal credit gate.
Evidence:
- Historical readback: nine FreeLLMAPI/Revolver routes double-canary approved; FreeLLMPool reported 0 ready.
- The observed `paid_credits_required`/402 was traced to internal user credit state, not proof that the Sovereign OpenRouter account lacked funds.
- No real paid completion canary was completed in that block.
Learned: Provider transport health, provider account funding and application-user spending authorization are three different truth boundaries.
Open: Paid OpenRouter completion and current free/keyless route inventory require current canaries.
Next safe step: Resolve current routing implementation first; use OpenRouter as canonical paid path and prove each free/keyless route independently.

### 2026-08-19 — HERO-1 MCP smoke attribution correction
Status: PARTIAL / corrected evidence attribution
Task: Smoke-test GitHub MCP connectivity and PR workflow behavior.
Decisions:
- Separate read/auth evidence from write evidence by actual tool used.
- Do not credit GitHub-MCP with a write that was performed through runtime-tools.
Touched surfaces: MCP smoke evidence and Draft PR #1575.
Evidence:
- Historical main `a688ffd74147cb806530665b4ddd3db790ce91b4`.
- Draft PR #1575 head `12c90b57fa3f832e70a3929b5fcc6d7c0d66c57a`.
- GitHub-MCP auth/read was verified; the actual write/PR creation used runtime-tools and therefore did not verify GitHub-MCP write capability.
Learned: Tool attribution is part of provenance. The same final GitHub object cannot prove which transport/tool created it.
Open: GitHub-MCP write capability remained unproven by that test.
Next safe step: When testing a connector, bind evidence to the exact invoked tool/transport and independently read back the resulting object.

### 2026-08-19 — OmniRoute managed runtime startup repair
Status: VERIFIED repository merge; historical runtime lane, not current routing authority
Task: Repair the managed OmniRoute container restart loop without weakening its sandbox/security contract.
Decisions:
- Remove only the `/tmp` tmpfs that hid the image-owned startup helper.
- Keep read-only root FS, non-root, no-new-privileges, cap-drop and private network.
- Put temp data under `/app/data`.
- Generate OmniRoute runtime secrets only during confirmed managed deployment; never store/return secret values.
- Do not set the route ready in SQL; require models + two real keyless chat canaries first.
Touched surfaces: Managed Compose template, secret-env provisioning, OmniRoute runtime.
Evidence:
- PR #1579 merged 2026-08-19.
- Head `a28142e4f2cc004718ff9ec6d4ed658f83bff481`.
- Merge commit `ae273c23e81f1d64435a4f92228be7661c4eeb88`.
- Original live failure: pinned OmniRoute image restarted with exit 127 because `/tmp/check-permissions.sh` was hidden.
- Local evidence: 7/7 OmniRoute compose tests, 31/31 managed-compose tests, 15/15 installer-contract tests, 8/8 continuity tests, clean diff/schema diagnostics/secret triage.
Learned: Container hardening can accidentally mask files required by the immutable image. Security controls need runtime evidence, not only static intent.
Open: The PR itself explicitly did not claim runtime green. Later architecture retired OmniRoute execution; this block remains historical only.
Next safe step: Do not resurrect historical OmniRoute assumptions. Re-read current OpenRouter/free routing ownership before touching transport code.

### 2026-08-19 — Continuity removed from authoritative gating
Status: VERIFIED design directive
Task: Remove Continuity from merge/release/truth authority while keeping passive historical logging.
Decisions:
- Continuity may observe and record but must not block/authorize workflow, merge, release, visibility or truth.
- Replace Continuity dependencies with hard revision, digest, ancestry and readback checks.
Touched surfaces: Revision Guardian/CI gating philosophy and continuity ownership.
Evidence: Historical implementation/readback recorded Revision Guardian/CI decoupling and current-main ancestry remaining a hard check.
Learned: Historical consistency is useful context, but it must not become a circular truth source.
Open: Any remaining code path that still treats Continuity as authoritative is architectural drift.
Next safe step: Architecture scans must flag blocking/authoritative Continuity references and move authority to revision/digest/readback boundaries.

### 2026-08-20 — Fortified fleet hardening branch
Status: HISTORICAL, not merged by this block
Task: Harden fleet application semantics and verifier behavior.
Decisions:
- Investigate and fix double-apply race and shallow-copy behavior before integration.
- Keep the branch out of main until the actual issues and runtime effects are closed.
Touched surfaces: Fleet hardening branch `hardening/fortified-fleet`.
Evidence:
- Historical head `abb931ad...`.
- 36/36 tests and 12/12 verifier checks reported green.
- Two real defects were still identified: Double-Apply-Race and Shallow-Copy.
Learned: A passing verifier suite does not erase defects discovered by causal review.
Open: Branch history is not current product truth; current code must be inspected before reusing any fix.
Next safe step: Treat the branch only as ancestry; re-derive any needed change against current main and runtime.

### 2026-08-25 — Live Monitor made the primary repository-scoped runtime surface
Status: VERIFIED repository merge
Task: Make the permanent Live Monitor the primary runtime surface and bind projections/previews to repository/job/workspace authority.
Decisions:
- Keep monitor projections bound to active repository/job/workspace.
- Preserve Runtime Unit Tests rather than hiding/removing the gate.
- Attribute CI coverage only to commands workflows actually execute.
- Scope immutable repository previews to signed user/repository/revision authority and fail closed on content handling.
Touched surfaces: Frontend primary monitor, repository preview scope, coverage attribution, smoke behavior.
Evidence:
- PR #1689 merged.
- Head `a2cf0907d1ce29a1fe4126b8a895a972e76644f0`.
- Merge commit `17470370fc2559afce5205f597e7ee2f5189b61e`.
- PR verification: 29 GitHub-access-helper tests, 27 internal-file-tool tests, GitHub scope authority contract, Continuity/ledger contracts, canonical/deployment mirrors mismatch 0, clean git diff.
Learned: The user-facing primary surface must reflect durable backend/repository truth, not a transient local chat choreography.
Open: Later work showed the Draft-PR end-to-end path was still not product-proven despite real components existing.
Next safe step: Judge monitor capability only by a real UI -> backend job -> workspace/tests -> GitHub object -> independent readback chain.

### 2026-09-09 — Runtime/repository identity mismatch and Secret-Egress proof requirement
Status: BLOCKED for revisionsame production-green claim
Task: Re-check current main, deployed MCP/PatchMon identity and the meaning of `secretValuesReturned=false`.
Decisions:
- Introduce the SSEP principle: `secretValuesReturned=false` is trustworthy only when derived from an executed egress scan/guard over the actual outgoing payload and resolved credential context, not a missing/default boolean.
- Continue requiring revision equality and immutable runtime evidence before product green.
Touched surfaces: Current repository/runtime identity, secret-egress truth boundary, PatchMon/fleet readback.
Evidence:
- Current main at this backfill workspace: `4d95c4525cfd43021e961cdfa4f0e7c3bda110be`.
- Workspace is clean and exactly based on that main.
- Deployed MCP revision readback: `4cff0bcfd579cfe37280999a8c69069aa0485dd6`.
- Runtime identity says container healthy / MCP protocol ready / broker RPC ready, but deployed immutable image digest is unavailable and deployed MCP revision is not current main.
- Therefore current repository/runtime resolver reports evidence gaps and does not establish revision-equal production green.
Learned: Healthy runtime and correct source are independent dimensions. `healthy=true` cannot substitute for exact source/runtime identity.
Open: Current deployed-MCP digest and revisionsame deployment remain unproven.
Next safe step: Before any production-green claim, obtain exact runtime image/digest plus revision binding and PatchMon/fleet readback from the same deployed candidate.

### 2026-09-09 — Frontend-to-GitHub Draft-PR product path repair
Status: BLOCKED acceptance; repair PR open/draft
Task: Make a real user mission in the product frontend reliably reach workspace execution and create an independently verifiable GitHub Draft PR.
Decisions:
- A repair PR is not acceptance evidence that the product created a Draft PR.
- Keep current-session repository job identity across reload/long-running readback instead of duplicating jobs.
- Preserve explicit publication confirmation.
- Accept opaque GitHub installation credentials at input boundaries while redacting them before event/log truncation; input acceptance does not grant write authority.
- Required regressions stay inside existing required gates rather than creating side-channel PR runners.
Touched surfaces: Frontend repository mission, backend agent/job/token handling, CI placement, Draft-PR publication/recovery flow.
Evidence:
- PR #1893 `fix(frontend): make Draft PR flow survive real repository runs` is open and Draft.
- Current PR head at historical backfill: `2ebf7aa8ef76585b372901ba40974aef8dc260e6`; base `4d95c4525cfd43021e961cdfa4f0e7c3bda110be`.
- Mandatory backend run cited in PR: 1315 passed, 1 skipped on an exact source checkout; independent pytest artifact hash recorded in the PR.
- Historical browser/live-backend run reached real POST `/api/user/agent/swarm/run` but failed on GitHub credential format; later production-canary attempts also failed to establish the terminal Draft-PR chain.
- Current acceptance statement remains: deployed frontend -> corrected backend -> real workspace/test evidence -> independently verified GitHub Draft PR is not yet proven.
Learned: Real code for prepare/create plus green unit tests still does not prove the product corridor. The proof must traverse the actual frontend and independently verify the GitHub artifact/head/content/state.
Open: Exact live authenticated execution, workspace/test evidence, Draft PR creation, independent GitHub readback, and final production revision/PatchMon readback.
Next safe step: Continue on #1893 without merge until the exact-head required gates and a real authenticated frontend mission produce the independent GitHub Draft-PR proof. Then append a new Memory entry with the successful or failed evidence before any merge.

### 2026-09-09 — Historical Memory.md bootstrap
Status: PARTIAL until Draft-PR checks complete
Task: Create the first project-root append-only integration memory from retrievable Sovereign engineering history.
Decisions: Keep project histories separated and future entries concise, append-only and evidence-bound.
Touched surfaces: Root `Memory.md` only.
Evidence: Draft PR #1896 was created from base `4d95c4525cfd43021e961cdfa4f0e7c3bda110be`; architecture inventory/snapshot/drift/assessment were executed; PatchMon readback showed 4/4 expected components running and HTTP 200; the fleet rollout gate remained closed because exact revision/workflow binding was not established.
Learned: A useful learning memory is a curated provenance ledger rather than a raw transcript.
Open: Draft-PR checks are still running; no merge is claimed.
Next safe step: Re-read the final diff and exact-head checks before any merge.

---

## Backfill boundary

This file captures the retrievable Sovereign integration history that materially affects current architecture and future N+1 work. It intentionally does not pretend to contain every chat sentence. If an older work block is recovered later, append it as a new `Historical recovery` entry with its original date/evidence; do not rewrite the existing chronology.

### 2026-09-09 — vNext authentication, safe evidence and run-blocker projection
Status: PARTIAL; Draft-PR acceptance remains BLOCKED
Task: Continue frontend replacement on #1894 without simulated success or automatic merge.
Decisions: Share an HTTPS auth/agent origin; verify browser-cookie identity; replace credential-bearing HTML step reports with metadata-only evidence; let persisted run blockers override stale job activity. Preserve concurrent cleanup/diagnostic changes.
Touched surfaces: vNext adapter/phase projection, live E2E TLS/session/reporting helpers and regressions.
Evidence: `2c30e65ddb0149c2ad71ba208534fe19f7b1cbdf`, Release Verification `34413236398/102672270269` passed. Live `34412996576` on `5beadf98...` proved authenticated HTTPS identity but returned `CHANGED_FILES_MISSING`, zero changed files/diff/tests, tool calls without mutation, and zero Draft PRs; artifact `10128088804`, ZIP SHA256 `9e4f1cb6248996cb32220ef7ea05ef218ae58a09b276bf34c93fb4c8dc0367bf`. Local phase regression replayed 71 genuine run observations within 131 assertions. Detailed receipts: #1894 comment `5609776468`.
Learned: HTTP-200 login is not a session proof; traces-off does not prevent HTML Fill-step credential leakage; a running linked job must not hide a blocked parent run.
Open: Real workspace mutation/test evidence, five independently verified Draft PRs and production/PatchMon proof. Issued test keys were revoked; old credential-bearing HTML artifacts and test-account rows were not deleted.
Next safe step: Read exact-head live run `34413640219`, inspect actual failed repository tool calls, and repair their cause. No merge/deploy until the full corridor is proven.


### 2026-09-10 — FreeLLM single-agent default with opt-in swarm
Status: PARTIAL; source/regression verified, production live proof pending
Task: Make normal vNext write/repository jobs run as one FreeLLM foreground agent while keeping the multi-agent swarm as an explicit feature.
Decisions: vNext defaults to `mode=free` + `agentMode=single`; single-agent preserves FreeLLM revolver candidates with zero background agents; swarm is opt-in and fails closed with `SWARM_CAPACITY_NOT_READY`; no automatic Free-to-Paid fallback.
Touched surfaces: vNext execution selector/request adapter; cognitive swarm start contract and shipping mirror; backend/frontend/Playwright regression contracts.
Evidence: Draft PR #1908 exact head before this append `a182bdbee024b3f404f170fe1a8a1d14fadcc9ed`; Agent Runtime and full Release Verification passed including typecheck, runtime units, Web/Android build, Artifact Smoke, Playwright Smoke and Integration Gate. Earlier production Five-Path runs `34535312135` and `34536426012` both reproduced `FREELLM_RATE_LIMITED` before repository mutation, motivating a normal single-agent path independent of swarm readiness.
Learned: Swarm capacity is an optional acceleration capability, not a prerequisite for an ordinary repository-writing product path; free transport and agent topology must be separately selectable and evidenced.
Open: Merge/deploy exact revision, then prove deployed vNext single-agent workspace mutation/tests and five independently read-back GitHub Draft PRs; provider backoff may still require an explicit new-run retry UX.
Next safe step: Re-run exact-head gates with this Memory entry, merge only if green, deploy exact merge revision, then execute the protected Five Real UI Paths as single-agent.

### 2026-09-11 — Internal Agent Job toolplane decoupled from external MCP broker
Status: VERIFIED source/regression; production live proof pending
Task: Remove the external ChatGPT MCP/broker as a prerequisite for normal backend Agent Job repository reads, writes, diffs and tests.
Decisions: Internal repository tools bind evidence to the executing backend revision/image plus the target workspace Git base as separate identities; ChatGPT MCP identity remains only for true external MCP/operator effects; historical v1 MCP receipts remain append-only while new internal calls use `sovereign.agent-execution-receipt.v1`.
Touched surfaces: Agent run receipts, repository tool execution, run-store receipt persistence, live-workspace receipt projection, migration 062 and the Required Agent Backend test lane; canonical/deployment mirrors remain paired.
Evidence: Deployed baseline `64bbf428c5646b922cad0e9499c5de3b5457fd0a`; Five Real UI Paths run `34542861497` reached FreeLLM single-agent repository execution but failed three pre-tool attempts with zero persisted tool rows; PR #1912 head before this append `c1da1ae313a23e7bc921e2887f8b9524aa82d23c`; Agent Backend run `34548069921` passed with 1269 tests + 1 skipped including five new internal-toolplane identity regressions; Release Verification `34548069971` passed Runtime Units, Typecheck, Web/Android, Artifact Smoke, Playwright and Integration Gate.
Learned: A backend Agent Job already owns an isolated workspace and must not call the hardened external ChatGPT MCP merely to prove its own file/Git/test execution; repository provenance, backend runtime provenance and external MCP provenance are distinct trust boundaries.
Open: Merge/deploy the exact reviewed revision, apply/read back migration 062, prove backend runtime/image equality, then rerun Five Real UI Paths and require 5/5 independently verified Draft PRs.
Next safe step: Re-run exact-head gates after this append; merge only with explicit Owner authorization, then immutable deploy + PatchMon/runtime readback + protected Five-Path proof.
