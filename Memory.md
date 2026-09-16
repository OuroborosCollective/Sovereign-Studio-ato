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

### 2026-09-11 — Refresh LLM boundary bindings after internal toolplane split
Status: VERIFIED static integration; production rerun pending
Task: Refresh the two reopen-on-change LLM boundary bindings changed by #1912 without changing runtime behavior or reviewed classifications.
Decisions: Preserve both candidates as STRUCTURED_POLICY; update only deterministic file-hash bindings with the repository reconciler; no new/removed candidates and no Owner classification decisions.
Touched surfaces: `config/architecture/llm-tool-boundary-review-ledger.json` only.
Evidence: Source `2193e7e85ac21422e75bdce6bfb8df39f0fdf61f`; reconciliation preserved 79 candidates with 2 `fileSha256` drifts, 0 new, 0 removed, 0 Owner decisions, `safeToApply=true`; ledger SHA-256 `01377a9725c6ad28a52cff90d2b9dbf0658db3049e6e2b80a4b3135b36afca0a`; PR #1914 code head `c6f2dac0f91aba30859cf41a40dd34dc03fadb9e` passed all five exact-head workflow families including Release Verification.
Learned: `reopenOnChange` correctly catches static evidence drift after legitimate structured-policy source edits; reviewed classifications should be preserved while bindings are refreshed, not bypassed.
Open: After merge, the new exact main still requires coordinated immutable release, migration-062/runtime readback, PatchMon/Fleet revision equality, and the protected 5/5 Single-Agent Draft-PR proof.
Next safe step: Re-run all exact-head gates with this Memory entry and merge only after a specific Owner approval.

### 2026-09-11 — Consolidate stale open PRs onto current Sovereign main
Status: VERIFIED source/regression integration; production rollout pending
Task: Collapse useful source/test changes from stale open PRs onto current main and remove obsolete/duplicate PR debt without restoring retired frontend paths or stale generated evidence.
Decisions: Port only GitHub-confirmed source/test surfaces; exclude generated/security reports, old boundary/Continuity ledgers, Jules metadata and retired chat/App-shell changes; close duplicates/obsolete PRs instead of regressively merging them; preserve canonical/deployment mirrors for cognitive-swarm JSON hardening.
Touched surfaces: Credential redaction, deterministic sorting, agent/pattern/telemetry/brownfield/tick-window hot paths, URL validation, product accessibility, generated-file review, cognitive-swarm JSON input validation and focused regressions across PR #1916.
Evidence: PR #1916 source head `da203c110a2f6b3a04c07dfba8a56dd6c6658700`; exact changed-path readback contained 23 expected source/test files and no generated/security/ledger/helper-workflow artifacts; Boundary Ledger Drift `34553468467`, Agent Backend `34553468690`, Release Verification `34553468435`, Continuity `34553531243` and Integration Plan `34553531244` all succeeded; useful intent from #1764, #1766, #1767, #1770, #1774, #1780, #1785, #1811, #1819, #1830, #1844, #1845, #1847, #1848, #1909, #1910 and #1915 was consolidated while #1834, #1843, #1854 and #1857 were closed as duplicate/obsolete.
Learned: Old bot PR branches are not safe merge units after long-lived main drift; GitHub PR file identity plus exact-current source reapplication is the reliable boundary, while historical generated evidence must be regenerated rather than imported.
Open: Final code+Memory head still requires exact-head gates before merge; dependency PRs #1903–#1906 remain to be integrated/closed, followed by a zero-open-PR readback and then coordinated production/runtime evidence including migration 062 and Five Real UI Paths.
Next safe step: Re-run all exact-head gates on the Memory-appended #1916 head, merge on success under the standing Owner zero-open-PR authorization, then complete the dependency wave and prove the open PR list is empty.

### 2026-09-11 — Restore current-main LLM boundary gate and activate Migration 062
Status: VERIFIED source/regression and live DB schema; production rollout pending
Task: Repair the exact-current-main LLM boundary ledger drift and close the live Migration 062 contract gap before production/Five-Path proof.
Decisions: Preserve all 79 reviewed boundary classifications; update only four deterministic SHA/line bindings; apply Migration 062 only after rollback-only preview; do not infer production green from image availability or healthy old containers.
Touched surfaces: `config/architecture/llm-tool-boundary-review-ledger.json`; live `agent_run_receipts` schema/constraints/index.
Evidence: Main `423d57e641adc105971adbb8437af43940a3290b` failed LLM Runtime Boundary run `34577290992`; deterministic reconcile found 4 binding drifts, 0 new/removed candidates, ledger `21371ef8c4621bcf00ecc41d088c9cb949bf347a9d5ca65d4cd1f516d7f3bef6`; PR #1917 pre-Memory head `2267567957d9eb0c98dc2e3cb82c21768b3a43bc` completed all exact-head checks with no pending/failed gates; Migration 062 SHA-256 `2945c62de6dfb8bcbf0bcbe4c9958c0b8b994ca6465bf77e88fcd7182c72b7a2` previewed with rollback, then live readback showed all five `execution_*` columns, nullable legacy MCP fields, dual receipt constraints and `idx_agent_run_receipts_execution_revision`.
Learned: Table-count parity and an `APPLIED` status do not prove a migration; the live column/constraint/index readback is the causal database evidence.
Open: Current main is still not runtime-equal to its immutable backend image; coordinated release, PatchMon equality and 5/5 real vNext Single-Agent Draft-PR paths remain required.
Next safe step: Re-run #1917 on the Memory-appended head; merge only after the exact head is green and Owner authorization is satisfied, then prove immutable deployment/runtime equality before Five Real UI Paths.

### 2026-09-11 — Make Five Real UI Paths causally prove free single-agent Draft PR publication
Status: VERIFIED source/regression; production rollout and 5/5 live proof pending
Task: Close the remaining Five-Path evidence gap so the new vNext frontend proves its actual free single-agent request, internal job/workspace execution and GitHub Draft-PR publication chain.
Decisions: Observe only allowlisted request/runtime fields and never mission/credentials; require `mode=free` + `agentMode=single`, `free_single_agent` foreground=1/background=0, real mutation/diff/tests and exact job/workspace identity; label the EXTERNAL WRITE CONSENT inline group; independently fail closed on the emitted five-path evidence artifact.
Touched surfaces: Five-path Playwright lane, secret-safe runtime/request observer, runtime-evidence verifier, vNext PublicationInspector consent accessibility and focused regressions.
Evidence: PR #1918 code head `3a57f98d0095831276afb8282f706b9447d42517`; Release Verification `34593780545`, Agent Backend `34593780471`, Integration Plan `34593780498` and Continuity `34593780552` all completed successfully on that exact head; seven code/test/workflow files changed before this append and no review threads were open.
Learned: Five successful Draft PR objects are insufficient unless every one is causally bound to the browser request and backend execution topology; the exported evidence also needs an independent fail-closed verifier.
Open: Merge the exact Memory-appended head, deploy the resulting main revision immutably, prove Migration 062/PatchMon/runtime equality, then run and independently inspect the protected five-path workflow.
Next safe step: Re-run all exact-head gates after this Memory append; merge only when terminal green, then perform revision-equal release/deploy before the live 5/5 proof.

### 2026-09-11 — Bind Five Real UI Paths to the deployed backend revision
Status: VERIFIED source/regression; live 5/5 proof pending
Task: Prevent the Five-Path evidence artifact from passing on a valid but non-deployed Git SHA.
Decisions: Read `/health` through the configured production backend origin; require live `sourceRevision` plus immutable `imageDigest`; fail closed unless the evidence SHA equals the running backend revision.
Touched surfaces: `scripts/verify-five-draft-pr-runtime-evidence.mjs` only.
Evidence: PR #1920 code head `dddcd6b9882093c3a6ea08b52e45bf3ca37a2100`; Agent Runtime, Revision Guardian, Integration Plan and Continuity succeeded; Release Gate typecheck, runtime units, Web/Android build, Artifact Smoke, Playwright Smoke, Integration Gate and Release Summary all succeeded on the same head. The preceding main `435339195e8c0fc6d5e43fefc10db9c705d6105f` was independently deployed with exact backend/MCP digests and PatchMon verification after coordinated-release attempt 2.
Learned: A syntactically valid source SHA is not deployment evidence; the browser evidence must be bound to the runtime identity it actually exercised.
Open: Re-run exact-head gates on this Memory-appended head, merge, deploy the resulting new main revisionsame, then execute and independently verify the real 5/5 Draft-PR paths plus cleanup.
Next safe step: Merge only after the Memory head is terminal green; then coordinated release and the protected owner-triggered Five Real UI Paths on the exact deployed main.

### 2026-09-11 — Restore JSON-native parameters at the repository-tool effect boundary
Status: VERIFIED source/regression; production rerun pending
Task: Repair the provider-neutral repository-tool bridge after the live Five-Path run opened its circuit with seven tool calls, three consecutive failures and zero confirmed mutations.
Decisions: Keep canonical parameter snapshots immutable for policy/hash/evidence, but recursively thaw mappings/arrays to JSON-native `dict`/`list` only immediately before the authorized ToolRegistry effect; preserve canonical/shipping mirror parity.
Touched surfaces: `backend/agent_runtime/tools/base.py`, shipping mirror, and provider-neutral real-Janitor regressions.
Evidence: Live Five-Path run `34597592175`, artifact SHA-256 `cc0d64e05080e490318c17333f40bae6810c02c2156869c1352bd5a041c3b695`; PR #1924 pre-Memory head `5488a63ffa25f003902f3d697e79168e705d7f74`; Agent Backend `34599803085` executed the new real `DynamicJanitorTool` bridge regression within `1270 passed, 1 skipped`; Release Verification `34599803118`, Code Quality, Security, Android and CodeQL all succeeded; canonical/shipping `base.py` blobs matched.
Learned: Immutable evidence containers cannot be passed shallowly into JSON-contract tools; a frozen array becoming a tuple is enough to turn an authorized valid tool call into a policy failure and contribute to the circuit breaker.
Open: This source fix does not prove that all three original live tool failures shared the same cause; exact-main deployment plus a fresh real Free-Single-Agent repository mutation readback must decide that.
Next safe step: Re-run every exact-head gate on this Memory-appended head, merge only when terminal green, deploy the resulting main immutably, then rerun one bounded real repository mission before continuing to deterministic backend closeout and simplified Draft-PR consent.

### 2026-09-11 — Bind vNext missions to product repository context
Status: VERIFIED source/regression; production rollout pending
Task: Prevent normal vNext repository mutations from degrading to conversation merely because the user did not repeat a GitHub URL in the mission text.
Decisions: Bind the control-surface repository context to `mode=free`, `agentMode=single`, `intentMode=repository_execution`; allow only an explicit GitHub URL as a bounded target override; keep swarm/worker/queue expansion out of this Draft-PR-first fix.
Touched surfaces: vNext repository-bound production adapter, adapter context, focused repository-binding regression.
Evidence: PR #1925 pre-Memory head `9b4f2d2166306279d3bed88ba7739b35f60bdd5b`; Sovereign Agent Backend, Continuity and Integration Plan workflows succeeded; Release Verification passed revision integrity, runtime canary contracts, typecheck, Runtime Unit Tests and Artifact Smoke on the same head.
Learned: Prompt text must not decide repository capability when the product already owns a repository context; otherwise a valid mutation request deterministically collapses to conversation.
Open: Agent Zero A2A/shared-workspace execution, deterministic backend closeout and the real UI-to-GitHub Draft-PR proof remain separate runtime obligations.
Next safe step: Re-run relevant gates on the Memory-appended head, merge #1925, then integrate Agent Zero A2A against the shared Sovereign workspace and prove one real Draft PR before scaling to 5/5.

### 2026-09-13 — Bounded Agent Zero operator diagnostics (#1935)
Status: CI_VERIFIED; production diagnostics and product E2E pending.
Änderung: Zwei feste Broker-/Host-Tools für Backend-Prozess-/Key-Readback und A2A-Submit/Poll mit dauerhaftem Claim vor Submit und ohne Resubmit bei unbekanntem Ausgang; Installer-/Registry-Verträge aktualisiert und Browser-Smoke an den bereits gemergten #1925-Request gebunden.
Erkenntnis: Default- und optionale private Registry sind getrennte Verträge (253/256 Tools); Paketmetadaten und gesunde Container beweisen weder geladene Servermodule noch einen erfolgreichen A2A-Task.
Evidence: Code-Head `db01156a9f863c5bbb8c358954e81bdf61fafcef`; MCP `34728550936` mit 1041 passed/12 skipped, Launcher-Import und Container-Build erfolgreich; Release Verification `34728529691` einschließlich Playwright und Integration Gate sowie Agent Runtime `34728529729` erfolgreich. PatchMon-Readback: 4/4 gesund, HTTP 200, bestehendes Backend-Image `sha256:1642ac13ebf26580a6211c91e9faf39b007a322d2e42033b48b44e7223660524`.
Offen: Exakte Checks nach diesem Eintrag, explizite Operator-Release-Freigabe, immutable Deployment und Registry-/Prozess-/HTTP-Readback; #1930 bleibt auf `06bc26fdb2ff62be4cadb73a94dc358210dfa511` ohne finalen Memory-Eintrag oder Merge bis zur vollständigen Live-/Five-Path-Evidence.

### 2026-09-14 — OpenRouter-Katalogidentität und kanonischer Restore-Vergleich (#1949)
Status: TESTED_AT_REVISION; endgültige CI-/Release-/Runtime-Abnahme nach diesem Eintrag offen.
Änderung: Neue Paid-Routen erhalten modellstabile IDs; Upsert nach `model_id` erhält bestehende Primär-/Fremdschlüssel. Paid-Abgleich und Paid-Lesemodelle bleiben im eigenen Namensraum und verändern die separate Free-Route nicht. PostgreSQL-Metadatenclients verwenden für Quell- und Restore-Rolle denselben `search_path=pg_catalog`; sämtliche Struktur-, Zeilen- und Vault-Vergleiche bleiben aktiv.
Erkenntnis: Die August-Fehler in Migration 021 und im Free-Typvergleich waren bereits behoben. Der aktuelle Paid-Fehler entsteht durch wechselnde Default-/Root-Zuordnung bei zwei Unique-Constraints. Die tatsächlich gescheiterte Restore-Probe zeigte außerdem rollenabhängig unterschiedlich qualifizierte Fremdschlüsseldefinitionen; ein Fehlerlabel ersetzt keinen Ursachenbeweis.
Evidence: Memory vor Integration gelesen; Basis `24c52e6eb0712f8510d1791a1ef3ed60ec278ff6`, Code-Head `0fbf44ee4bcc18c19f2168bb8677a735da159044`. 8 Identitäts-/Namensraumregressionen und 26 Fleet-Regressions bestanden; Required Agent Runtime Tests auf diesem Head erfolgreich. Echter PostgreSQL-15.1-Preview reproduzierte die alte UniqueViolation und prüfte Wiederholung, ID-/FK-Erhalt und Free-Isolation mit Rollback/Cleanup, SQL-SHA `d1398d79e8974675aa025934f9afd6ed203a99f766c67f8d2c31aaa4bfe39b65`. Read-only Suchpfadexperiment am selben Live-Schema: SQL-SHA `0f309745fdf3d46b9b04c1d8e4b23cefa89f488f78d9b9da345f26a18084ea9a`.
Offen/Nächster Schritt: Finale Exact-Head-Checks einschließlich Guardian, freigegebener Merge, immutable Backend-/MCP-Rollout und frischer Provider-/Docker-/PatchMon-Readback. Host-Wartung erst nach erfolgreicher wiederholter echter Restore-Probe mit aufbewahrtem Backup. Aktuell 6 Paketupdates, keine Security-Updates; kein Patch/Reboot ausgeführt. Test-Fixtures sind keine Produktions- oder Provider-Evidence.


### 2026-09-14 — Server-owned Agent Zero repository reconciliation (#1951)
Status: CI_VERIFIED; production rollout and live 5/5 proof pending.
Task: Remove client polling as the lifecycle owner for nonblocking Agent Zero repository jobs after live Five-Path evidence showed the shared workspace mutating after the browser runner had already stopped polling.
Decisions: Reconcile persisted `agent-zero-a2a:*` jobs from the production backend, keep claim refs quarantined, reuse the existing persisted `external_ref` CAS for idempotent closeout, fail closed on bounded stalls without resubmit, and give the protected Five-Path lane a bounded 10-minute repository window.
Touched surfaces: Agent job store/repository execution canonical+shipping mirrors, production Gunicorn bootstrap, repository-execution regressions, required Agent Backend gate, Five-Path E2E timeout.
Evidence: Base `8ce58dbeac5ab9b5d98ea7e51d31946b5592c710`; reviewed code head `ada5ca88085c0050dcac7e0a94c1e01d1a0ecdd0`; Agent Backend run `34865744937` passed 1294 tests + 1 skipped including `test_repository_execution.py`; Release Verification `34865744954`, Boundary Ledger `34865744980`, Integration Plan `34865744942` and Continuity `34865744993` all succeeded; PR #1951 reported `mergeable=true`, `mergeable_state=clean` before this append.
Learned: A2A submission plus eventual workspace mutation is not completion if lifecycle reconciliation is owned by a browser poller; asynchronous repository work needs a durable server-owned reconciler while effect ownership remains CAS-bound.
Open: This entry does not claim production fixed; the Memory-appended head must pass exact-head gates, then the merged revision needs immutable backend deployment/readback and a fresh real 5/5 Frontend → Agent Zero → Draft-PR causal proof.
Next safe step: Re-run exact-head required gates on this Memory head, merge #1951 only if terminal green, deploy/read back the immutable backend revision, then rerun and independently verify Five Real UI Paths.

### 2026-09-14 — Five-Path timeout hierarchy aligned (#1952)
Status: CI_VERIFIED; live 5/5 proof still pending.
Task: Correct the protected Five-Path harness after the post-deploy run on `656e029...` was killed by Playwright at ~300 s even though repository readiness was allowed 600 s.
Decisions: Keep product/A2A runtime unchanged; set each live path budget to repository-ready timeout plus 300 s and extend the serial workflow budget to 90 minutes.
Touched surfaces: `tests/e2e/five-draft-pr-paths.spec.ts`, `.github/workflows/e2e-testing.yml`.
Evidence: Base `656e02911322004736ad0f16b2c49272fe2b7e76`; code head `133aa5047c12fbcf02f97812288bea8acd927cb8`; failed live run `34869905753` timed out at 300324 ms; Agent Backend `34871533422`, Release Verification `34871533338`, Integration Plan `34871533345`, Continuity `34871533398` all succeeded; Wolfram budget check confirmed 600 s inner wait < 900 s per-test bound and 90 min workflow leaves 15 min slack across five maximum paths.
Learned: A bounded inner wait is ineffective when the enclosing test has a shorter timeout; timeout hierarchy must be monotonic from operation to test to workflow.
Open: This does not prove the Agent Zero corridor green; the protected 5/5 live run must be repeated after merge on exact deployed revision.
Next safe step: Re-run exact-head gates on this Memory-appended head, merge only if green, then perform exact-revision rollout/readback and the protected 5/5 Draft-PR proof.

### 2026-09-15 — A2A task-loss workspace-first recovery (#1971)
Status: CI_VERIFIED; production 5/5 proof pending.
Task: Repair the live lost-A2A-task closeout failure without re-solving Draft-PR creation, and remove two false-red CI paths.
Decisions: Treat the owned shared workspace—not transient A2A task retention—as repository-work truth: changed workspace closes out without resubmit; verified-empty workspace permits one CAS-bound recovery submit; unverifiable workspace blocks without resubmit. Missing ATO is a clean no-op; delayed supplemental dispatch after an exact PR closes is a clean no-op while unknown provenance still fails closed.
Touched surfaces: Repository execution canonical/shipping mirrors, repository/workflow regressions, ATO workflow, supplemental coordinator.
Evidence: Live `main@5a682f8407536d6f7ccbc0b6908a9d04e8fdd434` Five-Path run `34938782265` / artifact `10384124194` (`sha256:c9dd856c6dbebcdd25b29d3b2d1707e933cb8a2850c64d2edee4f4584296b737`) exposed TaskLost→retry-claim blocking after ~112s; guarded patch run `34977042660` passed 19 repository-execution tests; reviewed head `75b13f04ee84b6b44fa122eca35c04432e56cfa8` passed Agent Backend `34977685372`, Release Verification `34977685253`, Boundary Ledger `34977685300`, Integration Plan `34977685238`, Revision Guardian, and immutable PR-image validation `34977807411` with local OCI digest `sha256:f22e38f94abfae330856a9a34fffc2b51c20205eed8582ad5c219a95eb64e2c7`.
Learned: `tasks/get` loss proves only loss of transient executor identity, not loss of repository work; Draft-PR machinery already exists, while workspace mutation/evidence must remain the durable causal boundary.
Open: Production is not yet proven on this change; final Memory head must pass exact-head gates, then merged main requires coordinated immutable rollout/readback and a fresh protected Five-Path 5/5 run.
Next safe step: Rerun exact-head gates on this Memory head, merge #1971 only if terminal green, deploy/read back exact merged revision, then require fresh 5/5 and return to 0 open PRs.

### 2026-09-16 — vNext reload, ocular geometry and backend pnpm recovery (#1978)
Status: VERIFIED code/runtime candidate; final Memory-head revalidation and merge pending.
Task: Repair mobile vNext session loss on reload, the shrunken ocular header and repository closeout failing when `pnpm` was absent from the production backend image.
Decisions: Restore persisted repository runs only from authenticated backend job readback (skip non-repository jobs, never blind-resubmit); restore original eye geometry while keeping mobile visibility; carry Node 22 + pnpm 9.12.2 in the immutable backend image with canonical package shims.
Touched surfaces: vNext App/adapter/ocular contracts, browser reload E2E, backend Dockerfile and deployment contract test.
Evidence: Pre-read completed before integration; PR #1978 code head `c015c394c0e9e3ef37ec25545ddd8ce14fd184c9`; Release Verification `35084387703` and Agent Backend `35084387565` passed; immutable publish `35095516916` produced `sha256:ce7d6b789f3a93402ff4313dd2adb25b310f70557a42f56d2daccc6364bf047c`; production container readback shows that exact digest healthy, PatchMon 4/4 ready, FreeLLM 7 ready, OpenRouter ready, PostgreSQL canary=1 and A2A correlation canary verified.
Learned: Browser-local run identity cannot survive reload; copying Node package launchers across image stages can dereference relative shims and break them; visual mobile fixes must preserve the approved ocular geometry contract.
Open: The dedicated Agent-Zero canary control-plane still reports an unresolved prior-submit/receipt gap even though the separate live A2A correlation canary succeeds; final Memory-appended head must be exact-head CI/runtime revalidated before merge.
Next safe step: Re-run all exact-head gates, publish/deploy this final Memory head immutably, repeat PatchMon/runtime readback, then request the explicit merge step without automatic merge.

### 2026-09-16 — Bounded Agent Zero diagnostic failure staging (#1980)
Status: CI_VERIFIED; exact merged-revision runtime retry pending.
Task: Make the remaining dedicated Agent Zero diagnostic gap causally inspectable after #1978 reached revision-equal production.
Decisions: Preserve only strict uppercase internal failure-family identifiers plus fixed diagnostic stages; keep arbitrary exception text, subprocess stderr, URLs, response bodies, headers and secrets suppressed; do not change A2A execution or mutation behavior.
Touched surfaces: `tools/sovereign-chatgpt-mcp/agent_zero_diagnostics.py` and its focused regressions.
Evidence: Pre-read completed before integration; #1978 merged to `2e4681f9b1043b4f9329544d5bdbe581ce47c438`; backend runs exact digest `sha256:9eed65ee2a1da33cabdfcd1b348c3e318c37dac196000313f646be332e79d05d`; MCP self-update aligned the control plane to the same revision with digest `sha256:c3f876b84e6396df54217dbb55230f15c09da6eea72d72cd0b9c598a82dc6c5e`; the generic diagnostic failure reproduced after alignment while the separate A2A correlation canary remained verified. PR #1980 pre-Memory head `39a6e6cf4158199007ab2463bcf9d5c351054fa0` passed all exact-head checks; focused local evidence: 26 diagnostic tests, 22 broker tests and 3 backend-release/A2A tests passed, plus `git diff --check` and CODEOWNERS coverage.
Learned: A secret-safe diagnostic that collapses every bounded internal exception into one generic family destroys causal value; stage plus allowlisted-shaped family retains observability without exposing protected details.
Open: This patch improves diagnosis only; it does not claim the underlying dedicated Agent Zero diagnostic path fixed.
Next safe step: Re-run exact-head gates on this Memory-appended head, then merge only with explicit Owner approval; after exact merged-revision MCP rollout, repeat `agent_zero_backend_diagnostics` and repair only the newly proven failure family if one remains.

### 2026-09-16 — Agent Zero framework-interpreter diagnostic repair
Status: SOURCE_REGRESSION_VERIFIED; Draft-PR CI and live runtime proof pending.
Task: Repair the exact `DIAGNOSTIC_PROCESS_FAILED` reproduced at `probe-agent-zero-runtime` after #1980 made the failure stage observable.
Decisions: Execute the read-only Agent Zero inventory with the fixed framework interpreter `/opt/venv-a0/bin/python` rather than ambient `python`; require at least one observed `run_ui.py` process to resolve to that same executable before treating package metadata as diagnostic evidence; leave backend/A2A mutation paths unchanged.
Touched surfaces: `tools/sovereign-chatgpt-mcp/agent_zero_diagnostics.py` and focused diagnostic regressions.
Evidence: Memory pre-read occurred before this block; exact live baseline is `main@37a126eeca07b1698505efe087e10cd5028fdd51`, MCP `sha256:8e4d16787865dfda36909fdc4eab20e1e258826ad65c221c5d2df680b7a12cc0`, backend `sha256:67740c2081f7e02aaf83837741bef1ea76867fe15645ec201664e3bb6b34de8d`; dedicated diagnostic reproduced `DIAGNOSTIC_PROCESS_FAILED` at `probe-agent-zero-runtime` while Agent Zero and general A2A remained healthy. Focused checks passed: 27 diagnostic, 22 broker, 19 install-contract and 3 backend-release/A2A tests plus `git diff --check`; CODEOWNERS covers both changed paths.
Learned: Agent Zero activates a dedicated framework venv for `run_ui.py`; a fresh `docker exec` does not inherit shell activation, so an ambient interpreter is not valid evidence about the running framework. Matching the probe executable to the observed server process closes that attribution gap.
Open: Source tests cannot prove the live Agent Zero container accepts this interpreter path; exact-head CI, immutable MCP rollout and a fresh `agent_zero_backend_diagnostics` readback are still required.
Next safe step: Create one Draft PR, require terminal exact-head gates, and request explicit Owner merge approval only if green; after merge/self-update rerun the dedicated live diagnostic and stop on any new failure family.

### 2026-09-16 — Agent Zero unknown-submit quarantine recovery
Status: SOURCE_REGRESSION_VERIFIED; exact-head CI and live recovery pending.
Task: Remove the permanent global Canary blockade caused by an old `AGENT_ZERO_CANARY_UNRESOLVED_PRIOR_SUBMIT` without deleting evidence or blindly repeating the unknown submit.
Decisions: Keep the original fsync receipt unchanged; the same operation can never call `message/send` again. A new owner-approved Canary may quarantine an older unknown receipt only when it has no Task-ID and its bound Backend revision/image differs from the current exact release. Quarantine is a separate root-only `0600` receipt that explicitly preserves the unknown outcome. Any receipt with a Task-ID remains poll-only and continues to block new submits until terminal readback.
Touched surfaces: Agent Zero diagnostic/canary runtime, focused MCP regressions, MCP operator documentation.
Evidence: Pre-read completed before integration on `main@5eee8e9bcd6e039732651722909eb114c1fdcf03`; live dedicated Canary reproduced `AGENT_ZERO_CANARY_UNRESOLVED_PRIOR_SUBMIT` while `agent_zero_backend_diagnostics` completed and generic A2A correlation remained verified. Focused checks passed: 29 diagnostic tests, 22 broker tests, 19 install-contract tests, 3 backend-release/A2A tests and `git diff --check`; CODEOWNERS covers all touched MCP paths. Requested Wolfram and SciSpace plugin calls were attempted but the current conversation boundary returned `FORBIDDEN`, so no external research result is counted as evidence.
Learned: An unknown external-operation outcome and permission to run a later release-health Canary are distinct truths. Preserving the first as permanently unknown does not require letting it hold every future release hostage, provided the old operation is never replayed and known Task-IDs remain reconcilable instead of quarantined.
Open: Source tests cannot identify the live stale receipt until this MCP revision is installed. Exact-head CI, immutable MCP rollout, then one fresh dedicated Canary must prove whether the live receipt is safely quarantined or exposes a Task-ID that must be polled.
Next safe step: Create one Draft PR, require terminal exact-head gates, request explicit Owner merge approval only if green, self-update exact merged main, then rerun the dedicated Canary without deleting any historical receipt.

### 2026-09-16 — MCP Neuro import gate de-duplication after #1982 rollout
Status: SOURCE_REGRESSION_VERIFIED; exact-head CI and merged-runtime retry pending.
Task: Repair the #1982 MCP self-update blocker that rolled back at `verify_runtime_import_contracts` / `phase=neuro_imports` before the stronger isolated Neuro deployment canary could run.
Decisions: Keep the import-only probe advisory/non-terminal; retain the isolated Neuro runtime canary as the hard runtime authority because it exercises all five registered Neuro/Teaching tools with isolated state and bounded phase/error diagnostics. Add a built-image import gate to the MCP validator so source-level Python success cannot stand in for the immutable image runtime.
Touched surfaces: MCP main workflow, VPS installer runtime import sequence, installer contract regressions.
Evidence: Pre-read completed on `main@365e94ca1338f70d86b3efdc98d02d1cfd02768a`; exact backend rollout is healthy at `sha256:ea118c7f23b80d10ce67d65c7a8e5b2e1e8375628aaa6a87e4581aa6049a5cd3`, while the MCP self-update rolled back to healthy predecessor digest `sha256:b1d589c15632af8d0b8604b3759a9ed0820e18331f185154356d0e6690aa3477` after the redundant import-only Neuro gate failed. Focused checks: 20 install-contract tests and 9 Neuro deployment-install tests passed; workflow schema diagnostics clear; `git diff --check` and CODEOWNERS coverage passed.
Learned: A weak duplicate gate can suppress the evidence from a stronger downstream canary. Immutable-image imports must be exercised inside the built image, and production runtime failures should be decided by the richer canary that preserves bounded causal diagnostics.
Open: Source evidence does not prove the new exact-head image installs; exact-head CI, merge approval, immutable MCP self-update and the isolated live Neuro canary must pass before returning to the dedicated Agent Zero quarantine canary.
Next safe step: Create one Draft PR, require terminal exact-head gates, merge only with explicit Owner approval, self-update exact merged main, and then rerun the dedicated Agent Zero canary without altering historical receipts.

### 2026-09-17 — Stale Draft-PR consolidation and external URL hardening (#1986)
Status: SOURCE_INTEGRATION_VERIFIED; final Memory-head CI and merge approval pending.
Task: Work through the remaining open Sovereign Draft PRs without regressively merging stale branches, while preserving useful current-main security changes.
Decisions: Close empty, generated-evidence-only, obsolete-UI, superseded backend/Agent-Zero and unbenchmarked performance-only drafts rather than merging them. Port the useful #1975 credential-label redaction onto current main. Re-derive #1985's HTTPS-only external-navigation intent on current main because exact PR materialization was unavailable, using the existing `safeHttpsUrl` contract before checkout/docs/Draft-PR `window.open` calls. Keep generated security reports and old runtime code out of the consolidation.
Touched surfaces: `src/shared/utils/crypto.ts`, `src/shared/utils/crypto.test.ts`, `src/features/billing/PaywallModal.tsx`, `src/features/product/components/UserKeyManager.tsx`, `src/features/product/containers/BuilderContainer.tsx`; GitHub lifecycle for #1965, #1972-#1977, #1979, #1984 and #1985.
Evidence: Memory pre-read completed on `main@bdfc492e57cbe66cef8a7543629b5a288d1f4ca0`; #1975 exact source delta was materialized and reviewed before porting; #1985 changed-path/readback and all exact-head checks were green before closure, while direct materialization failed closed and therefore no unverified file bytes were imported. PR #1986 pre-Memory head `f27e9e6d792fed6692297147ecff99cbc6dfbbbc`; local `git diff --check` passed; CODEOWNERS covers the ported crypto paths; the latest Draft-PR update reported zero parallel drafts after the stale set was closed. Completed #1986 checks observed so far are green; Release Gate remained in progress at this entry.
Learned: Zero-open-PR cleanup is safer when useful intent is reapplied onto exact current main and stale generated/performance branches are closed instead of merged wholesale. Security intent can be re-derived from current contracts when a foreign branch cannot be materialized, but that must be stated explicitly rather than pretending the original patch bytes were reviewed.
Open: Final exact-head checks on the Memory-appended #1986 head remain required. The separate Agent Zero known-task poll gap (`AGENT_ZERO_CANARY_RUNTIME_CHANGED` for an old receipt with a real Task-ID) is not part of this consolidation and remains a distinct runtime repair.
Next safe step: Re-run all exact-head gates on #1986 after this entry, merge only with explicit Owner approval, then continue the known-task cross-release poll repair without resubmitting the old Agent Zero operation.

### 2026-09-17 — Agent Zero known-task cross-release poll repair
Status: SOURCE_REGRESSION_VERIFIED; exact-head CI and merged-runtime proof pending.
Task: Resolve the dedicated Canary deadlock where a historical receipt has a real Agent Zero Task-ID but its submit binding belongs to an older Backend release.
Decisions: Keep the original submit `binding` immutable and keep same-operation submit replay fail-closed across release changes. Permit only `action=poll` across Backend revisions when a Task-ID exists and the exact Agent Zero container identity still matches the original submit binding; record the current readback runtime separately as `pollBinding`. If Agent Zero itself changed, fail closed with `AGENT_ZERO_CANARY_AGENT_ZERO_RUNTIME_CHANGED`. Never resubmit the historical operation.
Touched surfaces: `tools/sovereign-chatgpt-mcp/agent_zero_diagnostics.py` and focused diagnostic regressions.
Evidence: Memory pre-read completed on `main@6ecaba0fd33f2903182dc150c6f7ebea5c38ab83`. The preceding exact runtime at `bdfc492e57cbe66cef8a7543629b5a288d1f4ca0` had MCP digest `sha256:b27a0519f3541b5496b33c43248624117c4f223204deeb23a5848e827f3b4527`, Backend digest `sha256:950dd37a8e8cd4ee34055bd2d8027585fb7aed66688fc98351c352a67a5d8399`, completed Agent Zero diagnostics, and one persisted operation `0c9821b2b2364097bccd54c8407c474e` with a verified Task-ID/state `submitted`; polling it reproduced `AGENT_ZERO_CANARY_RUNTIME_CHANGED` without resubmit. Focused source checks after the repair: 30 Agent Zero diagnostic tests and 22 broker tests passed; `git diff --check` passed; CODEOWNERS covers both changed MCP paths.
Learned: Backend release provenance and executor task identity are distinct. A known Task-ID may be read back through a newer exact Backend without rewriting submit provenance, but only while the Agent Zero execution identity remains the same.
Open: Source regressions do not prove the historical live task can still be read from Agent Zero. Exact-head CI, explicit merge approval, immutable MCP rollout, then a poll of the original operation must decide terminal state before any fresh dedicated Canary submit.
Next safe step: Create one Draft PR, require terminal exact-head gates, and request explicit Owner merge approval only if green; after merge/self-update poll `0c9821b2b2364097bccd54c8407c474e` first and never resubmit it.
