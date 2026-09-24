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

### 2026-09-17 — Ampel accessibility rebase onto exact current main
Status: SOURCE_INTEGRATION_VERIFIED; exact-head CI and merge approval pending.
Task: Preserve the useful Ampel accessibility change after #1988 advanced `main`, without merging the now-stale #1989 head.
Decisions: Re-materialize only the reviewed `Ampel.tsx` and focused accessibility regression from #1989 onto exact `main@f832c29fc38b82126433e55190bfbb78a6a78809`; do not import the stale branch Memory entry or any unrelated files. Keep `role=status` plus a status-specific accessible name on the wrapper and hide duplicate visual dots/text from assistive technology.
Touched surfaces: `src/features/product/components/Ampel.tsx`, `src/features/product/components/PaletteEnhancements.palette.test.tsx`.
Evidence: Memory pre-read completed before integration; #1989 had terminal CI with 27 checks, 0 failures, but its base had advanced from `6ecaba0f...` to `f832c29f...`; exact source paths were materialized from #1989 head `0757b01ee94399a6602cb792b1cce144aced2a71` onto current main without checking out the foreign branch. Repository diff shows only 31 insertions across the two intended files; CODEOWNERS coverage is complete. Node-dependent validation is delegated to GitHub Actions per repository policy.
Learned: A fully green PR can still become non-mergeable by policy once `main` advances. Reapplying the exact reviewed source delta onto the new main preserves the useful change without violating revision-equality rules.
Open: The new exact-current-main Draft PR still needs terminal GitHub Actions before merge; #1989 should remain superseded rather than merged stale.
Next safe step: Publish one replacement Draft PR, close #1989 as superseded, require terminal exact-head CI, then merge only under the standing Owner approval for zero-open-PR cleanup.

### 2026-09-17 — Agent Zero repository-submit HTTP decoupling
Status: SOURCE_REGRESSION_VERIFIED; Draft-PR CI and deployed UI proof pending.
Task: Remove the live 504/60-second Frontend failure caused by Sovereign synchronously waiting for Agent Zero task acceptance inside `/api/user/agent/repository/run`.
Decisions: Persist a deterministic `pending:submit` ref and return from the user request without Agent Zero transport; let only the server-owned reconciler CAS-claim and perform the initial A2A submit; keep unknown submit outcomes fail-closed/no-resubmit and bound the nonblocking A2A acknowledgement to 30 s.
Touched surfaces: Agent Zero A2A/repository-execution canonical+shipping mirrors and focused regressions.
Evidence: Pre-read completed on `main@0fb8045f648dac351fdf4fb5a5bc8c7476257f43`, deployed backend digest `sha256:ed39ef9502d6bba529e0a892f0aa7af364833a79149d78870d6e400d1ad3822e`; live DB showed the latest blocked repository job spanning 09:35:47→09:50:51 with `AGENT_ZERO_A2A_SUBMIT_OUTCOME_UNKNOWN`, matching the old 900-s submit timeout. Dedicated A2A poll completed on the existing known Task-ID without resubmit; diagnostics proved the current backend uses the real Agent Zero URL/key path, and historical live jobs prove shared-workspace mutation/Draft-PR creation. Focused regressions: 23 repository-execution + 6 A2A + 4 single-A2A-contract tests passed; canonical/shipping mirror mismatch=0.
Learned: HTTP 202 existed only after a still-synchronous `requests.post`; `blocking:false` at Agent Zero does not make Sovereign's caller asynchronous. The current root cause is initial-submit ownership, not localhost networking, missing workspace mount or Agent Zero GitHub-token guessing.
Open: Full Flask-backed route suite could not run in the isolated local checker because Flask is absent there; exact-head GitHub Agent Backend/Release lanes and a revision-equal deployed Frontend→pending→A2A→workspace→Draft-PR readback remain required.
Next safe step: Create one Draft PR, require terminal exact-head CI, then merge/deploy only under explicit Owner approval and verify PatchMon/runtime revision equality plus one fresh real UI Draft-PR run.

### 2026-09-18 — Public portfolio positioning
Status: SOURCE_AND_CI_VERIFIED; final Memory-head CI and merge pending.
Task: Improve the public README first view without changing Sovereign product/runtime truth.
Decisions: Keep Sovereign explicitly separate as the agent-infrastructure/operational-assurance line; link Aurion, ProofFleet, ARE Agent Studio, N+1 and WASD only as portfolio context; add no unsupported metrics or deployment claims.
Touched surfaces: `README.md`.
Evidence: Memory pre-read completed; local `git diff --check` passed; PR #1997 pre-Memory head `9762674953c7ee32917498271a9321d72f241ae8` changed only `README.md`; Revision Guardian Evidence, Revision Guardian, Release Gate, Agent Runtime Tests, continuity-ledger and integration-plan-lane-gate all completed successfully on that head.
Learned: Public readability can improve without weakening evidence boundaries when portfolio context is kept distinct from runtime truth.
Open: This append changes the PR head, so exact-head CI must be read again before merge.
Next safe step: Publish this single Memory entry, require terminal checks on the new exact head, then merge under Owner approval and read back `main`.


### 2026-09-18 — Agent Zero shared-workspace host mount repair
Status: SOURCE_PATCHED; exact-head CI and target-system runtime proof pending.
Task: Repair the repeated protected Five-Path Draft-PR failure after run `35340120654` attempt 2 reached a real Agent Zero task and closeout claim but still exposed zero changed files.
Decisions: Make `/opt/sovereign-agent-workspaces` the single host truth and bind it read-write into Agent Zero at `/a0/sovereign-workspaces`; the coordinated release reconciler may recreate only the existing Compose-managed Agent Zero service through its observed Compose project/config identity, with `--no-build --pull never`, then require Docker mount readback before release success. Keep Draft-PR publication behind explicit user consent and project the bounded final repository event stage instead of raw blocker text.
Touched surfaces: coordinated release reconciler, Agent Zero diagnostics/canary mount gate, live Five-Path runtime observation, focused regressions.
Evidence: Memory pre-read completed; Five-Path attempt 2 artifact `10550596042` / SHA-256 `ed7a156a61c89ce37d1f78d71585dcdeabf5de3f53e6c6b89120457dd7451e3e` records job `agent-6334c87d50144bfcbcf1d0d869bbf0d8`, Agent Zero task `ffbd456a-b978-4c07-a0b1-8f4b543d987c`, a real closeout claim and final blocked state with `changedFileCount=0`; changing Agent Zero's default working directory alone did not alter this result.
Learned: A matching path string inside Agent Zero is not shared filesystem authority; the Docker bind mount itself must be revision-independent host truth and independently read back.
Open: Exact-head CI, coordinated release host mutation/readback, Agent Zero mount diagnostics and a fresh protected 5/5 Draft-PR run remain required before claiming production-green.
Next safe step: Open one Draft PR, require terminal exact-head gates, merge only under Owner approval, let the coordinated main release install/read back the host mount, then rerun the protected Five-Path lane and require five GitHub-verified Draft PRs.


### 2026-09-18 — Agent Zero mount-release fixture repair
Status: SOURCE_PATCHED; exact-head CI pending.
Task: Repair the post-merge MCP validation failure without weakening the new Agent Zero shared-workspace mount gate, and close the CI gap that let the full MCP suite run only after merge.
Decisions: Keep the production mount preflight unchanged; make the legacy unexpected-runtime-readback fixture satisfy the verified no-op mount boundary so it still reaches the intentionally injected `OSError`; run the read-only MCP validator on pull requests while keeping image publication and VPS effects hard-gated to `push/main` or explicit main-only dispatch.
Touched surfaces: coordinated-release fixture, MCP workflow trigger, MCP CI safety regression.
Evidence: Memory pre-read completed on `main@18cd4baefeb256da0a4ea9b1794738e529d6ff94`; MCP run `35353879350` compiled all changed Python and passed 1053 tests with exactly one fixture failure, `test_unexpected_runtime_readback_failure_stays_redacted_and_retains_mutation`; bounded log artifact `10550429792` SHA-256 `46c7b2e8788068e37cad27340b24cca06a7c2af5267b8c2f1b725ec559a46c41`. Coordinated release `35353879180` stopped before target-system mutation because the exact-revision MCP image was not published.
Learned: Introducing an earlier fail-closed preflight changes the prerequisites of tests that intentionally inject later-stage failures; those fixtures must satisfy the earlier boundary rather than bypass or remove it. A release-critical validator that runs only after merge leaves an avoidable evidence gap, so the same non-mutating suite must execute on the PR head.
Open: Exact-head PR gates including the full MCP validator, a successful main MCP image, coordinated target-system receipt, mount readback, and fresh protected Five-Path proof remain required.
Next safe step: Require terminal exact-head PR and MCP-validator evidence, merge under Owner approval only when green, then let the main MCP/coordinated release rerun the real host-mount path.


### 2026-09-18 — Path-scoped repository closeout regression
Status: SOURCE_PATCHED; exact-head CI and deployed Five-Path proof pending.
Task: Repair the post-mount Five-Path blocker after Agent Zero began reaching real shared-workspace closeout but the README-only mutation was blocked by an unavailable global frontend regression environment.
Decisions: Keep code changes on the existing Janitor-selected project regression path; for documentation-only changes limited to allowlisted root docs, `docs/**` or `.github/**`, run a bounded UTF-8/document-structure regression after the existing full diff, `git diff --check` and Janitor gates. README.md additionally must preserve its first Markdown heading. Do not install dependencies in Agent Zero and do not weaken Draft-PR consent.
Touched surfaces: canonical+shipping `repository_execution.py` and focused repository-execution regressions.
Evidence: Memory pre-read completed on `main@b430384661b596cf79e06c82fac06ed756009865`; protected Five-Path run `35396640026` artifact `10567713173` / SHA-256 `358bcf766a9557ade1a9b20d5858b4dfc10706b89b4f398eb8ba988b9a6374c3` records a real Agent Zero task `4c67b5a7-f849-4d1d-8602-f4b3003fd7ca`, closeout claim, and final `repository_closeout_regression_blocked`, proving the mount/git-status/diff/Janitor boundary was crossed. The backend image carries Node/pnpm but no project node_modules and no pytest dependency, so a global `pnpm run test` is not a valid invariant for a README-only workspace.
Learned: Shared-workspace mutation and regression-environment provisioning are separate truth boundaries; a docs-only change needs a deterministic docs regression, while code changes must continue to require their real project test path.
Open: Exact-head CI, immutable backend deployment, runtime revision/digest readback and a fresh protected 5/5 Draft-PR run remain required.
Next safe step: Publish this Draft PR, require terminal exact-head gates, merge only under Owner approval, deploy the exact merged backend image, then rerun the protected Five-Path and require five GitHub-verified Draft PRs.


### 2026-09-19 — Reload must not adopt pre-A2A zombie repository jobs
Status: SOURCE_PATCHED; exact-head CI pending.
Task: Repair the live frontend reload state that restored an old repository job as executing and locked the mission composer even though the job never reached a valid Agent Zero A2A binding.
Decisions: Auto-restore only non-terminal repository jobs with a real workspace ID and persisted `agent-zero-a2a:*` external binding; skip pre-A2A clones and terminal history instead of treating them as the current execution. Preserve authenticated backend readback and never blind-resubmit on reload.
Touched surfaces: vNext repository-bound production adapter and focused restore regressions.
Evidence: Memory pre-read completed on `main@9e9782f858c53c4bcd2fdd109789a39be1379f72`. The 2026-09-19 mobile live recording shows restored job `agent-1689030d8391402894bf16bfa7087a73` stuck as `RUNNING · repository-single-a2a`, while visible runtime evidence stops at `agent_job_created → workspace_created → repo_clone_completed`; Workspace shows 0 changed files / revision unverified and the composer is disabled with “Mission locked while the persisted run is executing…”.
Learned: A persisted `running` label alone is not resumable execution truth. Reload adoption must require the causal workspace + A2A binding that proves the job crossed repository provisioning into the current execution protocol.
Open: Exact-head frontend/release CI and deployed reload readback remain required before calling the production UI repaired.
Next safe step: Require green exact-head gates, merge under Owner approval, deploy/read back the exact revision, then reload the authenticated production UI and confirm the stale job no longer locks the composer.


### 2026-09-19 — Repository execution is Agent-Zero-only
Status: SOURCE_PATCHED; final exact-head CI/deployed smoke pending.
Task: Remove the mixed executor boundary where Sovereign repository missions could acquire GitHub OAuth/session authority, clone inside Sovereign, or enter cognitive-swarm/controller billing paths instead of the canonical Agent Zero A2A executor.
Decisions: Repository execution is now Frontend → persisted Sovereign job → exactly one Agent Zero A2A task → Agent-Zero-owned repository access/checkout → shared workspace mutation. Sovereign GitHub credentials are rejected on execution and remain separate for readback/publication only. Generic job/toolchain and cognitive-swarm repository mutation paths fail closed; controller repository execution bypasses LLM/billing resolution and delegates directly to the canonical A2A route. Draft-card confirmation, direct-patch fallback, Launcher Executor and write presets no longer require GitHub Write before execution; GitHub Publish remains visible but informational until the separate publication action. Canonical/shipping backend mirrors remain byte-equal.
Evidence: Memory pre-read completed on `main@1ecde15912c732349732e2f823142bbcf6b47fb2`. Wolfram reachability model verified `GitHubOAuthCanReachExecuteRepository=False`, `AgentZeroCanReachExecuteRepository=True`, with the intended path `FrontendMission → BackendJob → AgentZeroA2A → ExecuteRepository`. PR #2011 exact-head backend and MCP full suites reached green during repair; Release Verification reduced from historical OAuth/Swarm contract failures to only obsolete frontend OAuth-gate expectations, which were replaced by execution-without-publication-authority regressions before this final Memory update.
Learned: Authentication/readback/publication authority and execution authority must be structurally separate at every UI and backend entry point. A GitHub credential available to a session must never become an implicit repository executor or prerequisite for starting an Agent Zero mission.
Open: Final exact-head gates after this final Memory update, merge, immutable production release/readback, and deployed Sovereign UI → Agent Zero smoke creating one empty root `testfile` without Draft PR remain required.
Next safe step: Freeze this head, require all exact-head gates green, merge under Owner approval, then verify production revision/digest and run the deployed UI testfile smoke with zero GitHub-OAuth execution dispatch.

### 2026-09-19 — Agent-Zero-only resume fallback closure
Status: SOURCE_PATCHED; exact-head CI and deployed runtime proof pending.
Task: Close the hidden post-#2011 repository-execution fallback that could reconstruct repository Swarm tools when a persisted run with a repository job was resumed.
Decisions: Repository-backed resume now fails closed before billing/model resolution in both Cognitive Swarm and Controller Board; `execute_persisted_swarm` rejects any repository tool factory/summary/toolset or repository job; internal free-agent repository toolsets are rejected; the residual `github_access_token=None` coupling was removed from canonical repository start. Canonical/shipping execution mirrors remain byte-equal.
Evidence: Started from exact `main@89e5303ec81b2e8091b0b5be413c04737b568f4e`. The merged source still contained active `create_repository_swarm_tasks(...)` resume paths in `cognitive_swarm_routes.py` and `controller_board.py`; targeted isolated checks before publication passed 4/4 Agent-Zero-only contract tests and 20/20 controller-board contract tests. The isolated runner lacked Flask for the full cognitive-swarm suite, so exact-head GitHub Agent Backend CI remains authoritative for that regression.
Learned: Start-path exclusivity is insufficient when resume/recovery code can reconstruct mutation authority from a persisted repository job; execution authority must stay exclusive across start, resume, recovery and internal-call boundaries.
Open: Exact-head CI, merge readback, immutable Backend revision/digest, PatchMon/Fleet health and the deployed UI → persisted job → exactly one Agent Zero A2A → empty root `testfile` smoke remain required.
Next safe step: Require terminal exact-head gates, merge only if green, then prove the exact merged Backend image and run the no-OAuth/no-Swarm/no-billing production smoke.

### 2026-09-19 — Agent-Zero-only production smoke lane
Status: SOURCE_AND_CI_VERIFIED; deployed smoke pending.
Task: Add a production-only proof for deployed UI → persisted repository job → exactly one Agent Zero A2A task → shared workspace → empty root `testfile`, with no OAuth/Swarm/billing/Draft-PR execution fallback.
Decisions: Use an opt-in `workflow_dispatch` lane with `contents: read`, no GitHub token or publication step; bind backend `/health` to exact revision/digest; verify `testfile` through the existing job-owned file and git-status readbacks.
Evidence: Memory pre-read on `main@5d23e0f0274e33140cc35e88aca0a7fefeb63109`; production backend `sha256:b6e7cafc8bae27f391a0b9397769cab9283ea9dec68a184bd41378beb0b462df` and Agent Zero healthy with RW shared-workspace mount. PR #2016 pre-Memory head `97c6ae14148c796872028d667d613581a4b10597`: Agent Backend 1305 passed/1 skipped, Revision Guardian, Boundary Ledger, Continuity, Integration Plan, MCP validator and Release Verification all succeeded.
Learned: The existing job-owned FileReadTool plus git-status already proves regular-file identity, zero bytes, empty SHA-256 and uncommitted state; no new runtime readback API or GitHub execution authority is needed.
Open: This Memory append changes the PR head; exact-head gates, merge/deploy revision+digest readback and the real dispatched production smoke are still required.
Next safe step: Require terminal checks on the new exact head, merge only if green, deploy/read back that exact revision and dispatch the smoke.


### 2026-09-19 — Production smoke canonical UI route correction
Status: SOURCE_PATCHED; exact-head CI and redispatch pending.
Task: Repair the first real Agent-Zero-only production smoke after it failed before repository execution because the workflow targeted the callback/rescue host instead of the canonical deployed user app.
Decisions: Bind the smoke UI to `https://sovereign-backend.arelorian.de/app/`; keep `chat.arelorian.de` out of the workflow execution surface; preserve the existing read-only workflow permissions and all OAuth/Swarm/billing/Draft-PR negative assertions.
Evidence: Memory pre-read completed on `main@01ddd09863e958c4b4bc8d55c6adee376059e0c9`. Production release is verified at Backend `sha256:2f7079f691e15262dc133b42e95d9e98eb6225ee6e4a2c50cd1863205a9b036b`, MCP `sha256:f77aef81dcd16c6d41894da7a2cdd1f83122565d7aeeaf47dcd4fe4933a6c0a5`, runtime receipt `217fccd5352997b523c35fe5a953abdb4c6f74bcd3931af923d580730be709c2`. Smoke run `35471558556` failed causally with `DEPLOYED_UI_HTTP_404` before any repository/A2A action. The live backend source owns `/app/` as the canonical user-app route and `docs/GITHUB_OAUTH_SETUP.md` names that URL as the productive frontend. Focused contract 3/3, `git diff --check`, backend compile and workflow schema diagnostics pass after the correction.
Learned: OAuth callback/rescue origins are not interchangeable with the product UI truth boundary; production smoke must bind to the route actually serving the revision-stamped user artifact.
Open: Exact-head GitHub gates, merge/deploy readback for the correction and a fresh production smoke still remain before final E2E verification.
Next safe step: Publish one Draft PR, require exact-head terminal green, merge under Owner approval, verify the resulting production revision/digest, then redispatch the same smoke and read its artifact to terminal.


### 2026-09-20 — Agent Zero observation, CAG order and abort feedback
Status: IMPLEMENTED_IN_REPOSITORY; CI and production verification pending.
Task: Investigate the owner's stalled-video job and restore the compact route control and centered white eye while retaining Agent Zero as the sole GitHub executor.
Evidence: Exact base/runtime `ddecf91c8bffb9a72db71917c404f26e17faa505`, backend image `sha256:fb29f55f2731c73214131cab970449658d0e4ce12152c6165d80c9fa84a968f4`. Job `agent-6adc254dd9e54e85baa660ef2011c18c` reached `repository_closeout_regression_blocked` at 15:39:19Z because the workspace lacked node_modules. The observed access-delegation/contract-binding order contradicted the CAG invariant, creating a verified-but-false state-transition incident outside the active readback-only repair grant. Frontend Abort threw before HTTP; backend correctly refused to claim an unproven A2A stop.
Changes: Persist throttled task observations without resetting the stall clock; preserve observed files/diff before regression; correct the CAG order and exclude polling noise; surface readback/abort failures; remove phase-derived percentages; restore the white eye and compact single-agent selector. Three canonical/shipping mirrors remain byte-equal. Added a bounded, pinned Paramiko routing probe with interactive password input and no secret output.
Validation: 102 focused backend tests passed; two filesystem ownership tests also fail on the unchanged base in this local environment and require CI. Python compile and git diff check passed. Frontend behavior tests await GitHub Actions.
Open: Production workspace dependency provisioning, verified Agent Zero task cancellation and per-task Low/Free–Medium/Paid–High/Paid binding remain unresolved. Existing backend Free/Paid providers are configured, but the installed Agent Zero model configuration/source is not yet observed. Owner-authorized SSH was unreachable before authentication. Paid options stay explicitly unavailable; no authority, billing, runtime, merge or deployment mutation was performed.

### 2026-09-21 — Deadline frontend/closeout hardening
Change: Replaced the vNEXT header eye with a deterministic 3D white-eye/black-pupil design and made repository closeout bootstrap missing Node dependencies only from an exact lockfile; the canonical Sovereign origin may use its checked-in pnpm build policy, while other repositories keep lifecycle scripts disabled.
Learned: The proven completion blocker was not READY_TO_PUBLISH polling but the clean Agent-Zero workspace reaching Sovereign closeout without node_modules; provider timeouts remain a separate runtime risk and are not disguised by this patch.
Evidence: Pre-memory head `f2b3de5ca55e436da9c4db96a7bad2350ec42edd` passed Release Verification 35614791421, Sovereign Agent Backend 35614791861, Sovereign ChatGPT MCP 35614791402, Integration Plan 35614791399, Continuity 35614791409 and Boundary Drift 35614791537; canonical/shipping TestTool copies are byte-identical. This append changes the head, so exact-head gates remain required before merge.


### 2026-09-21 — Agent Zero live-control truth repair
Change: Added exact A2A `tasks/cancel` confirmation, immutable-created-at stall enforcement, suppressed duplicate unchanged `tasks/get` heartbeats, hardened Agent Zero against reusing timed-out terminal sessions, clarified changed-file UI semantics, and replaced the header eye with a visibly distinct deterministic cyber-ocular HUD.
Learned: Live job `agent-33db1102b0c34588a980ea248d7a3a58` was genuinely handed to Agent Zero, but `tasks/get` stayed `submitted` while Agent Zero logs showed the workspace task executing and a terminal `ls` returning no output for 30s; repeated submitted events were noise, not progress.
Evidence: targeted A2A tests 7/7 and repository-execution tests 31/31 pass locally after integrating the monotonic stall fix; PR #2039 Agent Runtime Tests passed on pre-memory head `ce9e2b796a5e80bc368c44a11f24353234b48088`; live DB readback preserved the single task id `5c42f9f0-25c6-4a2a-bff1-54f2eeae5a14` without duplicate submit.


### 2026-09-21 — Release Verification stale UI contract repair
Change: Updated the vNext truth-contract tests to match the merged cyber-ocular geometry and to verify the truthful unavailable-completion message without case-sensitive wording drift.
Learned: Release Verification run 35623545113 failed because two assertions lagged behind intentional UI copy/geometry changes; production behavior was already correct.
Evidence: Pre-memory head `d3e88083a0b913a9134939486e0a589e0100640f` passed Release Verification 35626122857 with frontend-smoke 3791 total / 3789 passed / 0 failed / 2 skipped, plus Runtime Unit Tests, Playwright Smoke Gate and Integration Gate success; Agent Backend 35626122841, MCP 35626122862, Continuity 35626122859 and Integration Plan 35626122855 also passed.

### 2026-09-21 — Open-PR runtime consolidation
Change: Consolidated the live Agent Zero stale-submitted cancellation/workspace-progress repair with the non-contradictory publication-intent prompt and a hard 30-minute repository stall cap; obsolete competing PRs were retired.
Learned: FastA2A `submitted` is not proof of progress, so stale queue state must be bounded while independently observed workspace mutations are preserved; publication wording belongs to Sovereign, not Agent Zero execution.
Evidence: Pre-memory head `c8aba8bc7004238685e3b7de056d5fea94acc6a2` passed Release Verification #5924 (frontend smoke 3789 passed / 0 failed / 2 skipped, Runtime Unit, Playwright and Integration success), Agent Backend #3244, MCP #2392, Continuity #2804, Boundary Drift #1646 and Integration Plan #2297.

### 2026-09-21 — Agent Zero IT-Tools private sidecar
Change: Added digest-pinned IT-Tools as a private managed Compose sidecar and exposed it to Agent Zero only as an optional deterministic developer utility, with no public port or evidence authority.
Learned: IT-Tools is a static browser UI, so a running container alone proves little; verified deployment must additionally prove the real Agent Zero container can reach the internal UI.
Evidence: Pre-memory head `9d78549df383ad63c3bf754d7db6d9b8da4a7306` passed 66/66 focused local regressions plus Release Verification 35636412544, MCP 35636412289, Agent Backend 35636412286, Continuity 35636412253, Boundary Drift 35636412305 and Integration Plan 35636412343; PatchMon runtime was 4/4 healthy. Live sidecar deployment remains unclaimed until the merged exact revision passes the Agent-Zero HTTP canary.

### 2026-09-21 — IT-Tools installer copy repair
Change: Added the missing `IT_TOOLS_TEMPLATE_DIR` bootstrap directory before managed control-plane copy.
Learned: Registering a managed stack is insufficient if its template target directory is not created before the fail-closed atomic installer copy.
Evidence: Self-update of main `8739e61eff8988aa3996da87124f570e33af02d7` failed exactly at `copy_control_plane_file:templates/sovereign-it-tools/docker-compose.yml` and rolled back; after the repair 20 installer + 35 managed-compose tests, backend compile and `git diff --check` pass.

### 2026-09-21 — Wolfram source intelligence lane
Change: Added consent-gated Wolfram CodeParser/CodeInspector/CodeFormatter parse, inspect and format-preview tooling over the existing CAG transport, with source-as-data encoding, 32-KiB input bound, per-call egress approval, structural formatter equivalence, Sovottt MCP exposure and a lane-only 128-KiB normalized-result window while normal CAG remains 4 KiB.
Learned: Static CodeTools evidence is useful only when source egress, parser structure and result-size boundaries are explicit; provider success remains SUCCEEDED_UNVERIFIED and cannot replace repository/runtime truth.
Evidence: Pre-memory head `bf6d2b94b71ea2ff03c68b5610267fc7c942dbf5`; Agent Backend #3261 SUCCESS; MCP #2414 SUCCESS with 1058 passed/12 skipped and live registry contract including `wolfram_source_intelligence`; Release Verification #5942 SUCCESS with frontend smoke 3789 passed/0 failed/2 skipped, 11 Playwright smoke and 90 integration tests; Boundary Ledger #1661, Integration Plan #2313 and Continuity #2820 SUCCESS.

### 2026-09-21 — MCP runner immutable-image recovery
Change: Added an explicit main-only `publish_immutable_mcp` workflow-dispatch recovery mode that publishes/verifies the exact MCP image without implying VPS deployment.
Learned: Manual VPS bootstrap cannot recover a missing MCP publisher if workflow-dispatch can only validate; image publication and deployment need separate bounded recovery stages.
Evidence: Coordinated Release 35640973123 on `6325abbb90288c38197f07d6427d1eb6fd0f545f` failed at exact-revision image-workflow evidence while backend digest `sha256:80771f6ba2d08f4c328a3cb83a34c2b247765b024aabdb0dc8e002cdab67d34b` was verified; 13 bootstrap/deploy + 20 installer tests and `git diff --check` pass after the recovery-path change.


### 2026-09-21 — Agent Zero Causal Progress Lease
Status: SOURCE_REGRESSION_VERIFIED; production runtime proof pending
Änderung: SCPL trennt A2A-Liveness von materieller Git-Progression, persistiert predecessor-/workspace-/taskgebundene Progress-Receipts im bestehenden Event-Store, dedupliziert bereits kreditierte Workspace-Fingerprints und begrenzt Weiterlauf zusätzlich durch eine absolute Deadline; #1525 bleibt alleiniger Worker-Heartbeat-/Fleet-Lease-Owner.
Erkenntnis: Polling/working ist keine Fortschrittsevidence; selbst ein gültiger Progress-Receipt braucht eine atomar serialisierte predecessor chain, und fehlendes Job-Start-Binding muss fail-closed statt durch eine neu startende Deadline behandelt werden.
Evidence: Pre-Memory PR #2055 head `4a77b8c392b60bdee27894940505fc63f7ce3f58`; Agent Backend run 35645339576: 1317 passed, 1 skipped plus N+1 malformed-JSON pass; Boundary Ledger 35645339491, Integration Plan 35645339592 und Continuity 35645339613 success; canonical/shipping blobs für cag_self_healing, causal_progress_lease, job_store und repository_execution identisch. Production bleibt UNVERIFIED, da der verfügbare Runtime/MCP-Readback keinen revisions-/digestverifizierten laufenden Stand lieferte.
Next safe step: Finalen Memory-Head exakt neu prüfen; Draft PR nicht mergen/deployen, bevor Required Checks terminal grün, main weiterhin basegleich und ein späterer revisionsgleicher Agent-Zero/Workspace/PatchMon-Runtime-Readback verfügbar ist.

### 2026-09-21 — SCPL final truth-boundary hardening
Status: SOURCE_REGRESSION_VERIFIED; production runtime proof pending
Änderung: SCPL wurde nach dem ersten grünen Stand fail-closed nachgeschärft: fehlende Git-Evidence bleibt `UNVERIFIED` statt als beobachteter Stillstand zu gelten; terminale/gewechselte Job-Bindings können keine späten Progress-Receipts mehr erzeugen; konkurrierende Reconciler übernehmen nur einen real persistierten neuen Receipt-Head; die vollständige append-only Receipt-Chain wird bounded oldest-first validiert; ein Retry-/Task-ID-Wechsel verlängert die Lease nicht ohne einen neuen autoritativen Git-Workspace-Fingerprint.
Erkenntnis: Fehlende Beobachtbarkeit ist nicht dasselbe wie No-Progress, und neue Executor-Identität ist nicht materieller Fortschritt. Für einen belastbaren Progress-Lease müssen sowohl der aktuelle Workspace-Zustand als auch die gesamte Predecessor-Chain und die noch aktuelle Job-/A2A-Bindung übereinstimmen.
Evidence: Pre-Memory head `f0778ef1378c226a6bd7ba0dd9c4e049205e8836` auf unverändertem `main@e3875a43f530333aad5670bd450b299aa2216a54`; Agent Backend 35649838961, MCP 35649838965, Release Verification 35649838956, Boundary Ledger 35649838951, Integration Plan 35649838945 und Continuity 35649838981 jeweils SUCCESS; Runtime Unit Tests, Web+Android Build, Artifact Smoke, Playwright Smoke und Integration Gate SUCCESS; canonical/shipping Mirrors für causal_progress_lease, job_store, repository_execution und cag_self_healing 4/4 blob-identisch. Amplitude-Projekt 850948 enthält aktuell keine Events, daher wurde keine erfundene SCPL-Telemetrie ergänzt. Production bleibt UNVERIFIED, weil kein revisions-/digestgleicher PatchMon/Docker-Runtime-Readback verfügbar ist.
Next safe step: Memory-Head exact erneut durch alle Required Checks prüfen; Draft PR weder mergen noch deployen, solange Runtime-Parität nicht separat real belegt ist.



### 2026-09-22 — N+1 malformed JSON hardening rebased onto current main
Status: PARTIAL
Task: Carry the reviewed N+1 malformed-JSON hardening from stale PR #2057 onto current main after PR sweep.
Decisions:
- Preserve `request.get_json(force=True, silent=True)` on all three N+1 POST endpoints so non-dictionary JSON reaches the existing typed 400 response instead of an unhandled parser exception.
- Update both canonical backend and mirrored Sovereign backend files; do not weaken the existing payload contract.
Touched surfaces: `backend/n_plus_one/routes.py`, `scripts/sovereign-backend/n_plus_one/routes.py`, existing `backend/tests/test_n1_json_validation.py`.
Evidence: Original PR #2057 had all available CI lanes successful and failed only the mergeability freshness check because its base was stale; current main still contained the vulnerable `force=True` calls, so the narrow patch was reapplied on a fresh current-main branch.
Learned: A stale but clean security fix should be re-derived against current ownership rather than merged through a divergent branch.
Open: Current-main branch needs exact-head CI/runtime readback before merge.
Next safe step: Create a Draft PR, require all checks, then merge only after green exact-head evidence.
### 2026-09-23 — Evidence Flywheel + consent boundary integration
Status: PARTIAL — source patch and Draft PR created; exact-head CI/runtime verification pending
Task: Integrate vendor-neutral evaluation patterns from the supplied skills archive into Sovereign without creating a second runtime, registry, approval system or evidence truth layer.
Decisions: Add the revision-bound Evidence Flywheel skill to agent/runtime surfaces; bind engineering work to real baseline → bounded execution → causal failure analysis → minimal repair → regression/benchmark → independent readback; extend the existing consent pattern with Action Preview, authority/scope binding, causal Action Receipt and asynchronous revocation checks; preserve Agent Zero as the repository executor and do not reintroduce Swarm, awareness-monitor execution or LiteLLM.
Touched surfaces: AGENTS.md; .agents/skills/evidence-flywheel/; tools/sovereign-chatgpt-mcp/skills/sovereign-evidence-flywheel/; existing consent/operational-assurance skills; evidence-flywheel architecture doc; installer contract; regression contract test.
Evidence: Current main baseline 7e1aa5e354807ade245486ae9f4c3bb6ee495e53; Draft PR #2071 head before this Memory append 88f550ea29ab38b77d404a35405b231607e0dd6b; exact-head GitHub Actions were observed running/queued, not green. Supplied archive SHA-256 dbfb60b5e0fbd84c2fbf16c1ae3d527cfb3782e7455d896a9e6749781e5c8787.
Learned: The useful archive contribution is the evaluation discipline itself; Sovereign already owns the necessary architecture, consent, registry, benchmark, CI and readback primitives, so duplicating them would increase drift rather than reduce it.
Open: New Memory append changes the PR head; exact-head CI, runtime identity, PatchMon readback and any merge remain pending.
Next safe step: Re-read this exact branch head, require terminal checks and only then consider the normal Owner/merge gate.


### 2026-09-23 — Evidence Flywheel contract regression repair
Status: PARTIAL — source regression repaired; exact-head revalidation pending
Task: Repair the exact-head MCP gate failure introduced by the Evidence Flywheel integration.
Decisions: Keep the regression test strict and align the canonical/packaged skill wording instead of weakening the assertion.
Touched surfaces: `.agents/skills/evidence-flywheel/SKILL.md`, `tools/sovereign-chatgpt-mcp/skills/sovereign-evidence-flywheel/SKILL.md`.
Evidence: Exact-head `9e9866252e786e2846037c98e52c25b97e28617a` had 1066 passed / 12 skipped / 1 failed; the sole failure was `test_evidence_flywheel_contract_contains_required_boundaries` because `causal failure-family analysis` was absent while the semantically equivalent `failure-family analysis` was present. The failing MCP workflow was `Sovereign ChatGPT MCP` run `35805757831`, job `107006753984`; all other terminal PR #2071 runs were successful, and all five PR #483 runs were successful.
Learned: Contract tests must remain exact enough to protect the intended method, while canonical text should expose the required invariant unambiguously; mirror parity is preserved.
Open: The repair changes the PR head, so no green claim or merge is valid until the new exact head is re-run through all required gates.
Next safe step: Re-read the new PR head, require terminal exact-head CI, then perform the required independent/runtime readbacks before any merge decision.


### 2026-09-23 — Evidence Flywheel mirror-contract regression repair
Status: PARTIAL — source repair committed; exact-head revalidation pending
Task: Repair the second MCP contract regression on PR #2071 without weakening the regression suite.
Decisions: Keep the exact contract assertions; align the canonical and packaged flywheel skills byte-for-byte, expose the required Action Preview wording in both, and use the contract’s required `fake snapshot` invariant rather than removing the guard.
Touched surfaces: `.agents/skills/evidence-flywheel/SKILL.md`; `tools/sovereign-chatgpt-mcp/skills/sovereign-evidence-flywheel/SKILL.md`.
Evidence: Exact-head `58e291a3c56aa2a30f9d2461390ef373b7ca9b09` MCP run `35809701860` failed 2/1067 tests: canonical/runtime mirror parity and the required `fake snapshot` wording. The repair commits are `60acd77522d024af792e38e7937e282fe4dd4441` and `8e2cbfdc3cf8fd1d027f1d6dd13ed9ad1e89a695`; the packaged mirror now uses the canonical content.
Learned: Contract tests are correctly detecting both semantic wording drift and mirror divergence; the right fix is canonical contract alignment, not test relaxation.
Open: The new head still needs terminal exact-head CI and independent runtime/readback evidence before merge.
Next safe step: Re-read the final branch head, require all required gates to finish green, then perform the normal runtime/PatchMon evidence checks before any merge.


### 2026-09-23 — Evidence Flywheel installer boundary readback repair
Status: PARTIAL — post-merge source defect repaired; final main/runtime readback pending
Task: Repair the Evidence Flywheel installer command boundary found by independent post-merge readback.
Decisions: Replace the literal \\n between the Neuro Teaching and Evidence Flywheel installer checks with a real shell command boundary; keep the fail-closed checks intact and do not weaken contracts or tests.
Touched surfaces: `tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh`; `Memory.md`.
Evidence: Evidence Flywheel integration merged as main commit `9eb27019aeea7b8589814a5cce436f64aba76a8e`. Independent file readback found a literal \\n in the installer. Repair head is `d391adfcfae96483d682ed42603fff08f9aa6765`, PR #2073. Exact-head Required Checks: Continuity 2933, Integration Plan 2426, Agent Backend 3367, Release Verification 6057, Boundary Ledger 1759 and MCP 2540 all SUCCESS.
Learned: Post-merge source readback can expose shell-boundary defects that static integration contracts did not catch; the smallest causal repair is preferable to test relaxation or a second implementation path.
Open: PR #2073 still needs the normal merge gate and post-merge main/runtime readback; no live PatchMon/host runtime claim is made because no remote device was available.
Next safe step: Merge the exact verified head, resolve the new main revision, then repeat installer, CI and applicable runtime identity/readback checks.

### 2026-09-23 — Hostinger sovereign-toolchain dotenv boundary repair
Status: PARTIAL — repository fix prepared; Hostinger update revalidation pending
Task: Remove an unnecessary .env dependency from tools/sovereign-toolchain/docker-compose.yml that can cause Hostinger to reject the project before runtime values are resolved.
Decisions: Keep BROKER_GID and SOVEREIGN_MCP_IMAGE dynamic and immutable in the MCP deployment path; do not commit host-specific values or secrets. The toolchain Compose file contains no references requiring those variables, so the redundant env_file: .env declaration is removed.
Touched surfaces: tools/sovereign-toolchain/docker-compose.yml; tools/sovereign-toolchain/tests/test_compose_contract.py.
Evidence: exact main baseline 5511c638e8ba0384420979692dd63ed7ec1d4b9d; Compose before SHA-256 54e090ca6695ba62c42005d5db174b5e6896e399f5399724fb35eb5cdff6f347; after SHA-256 57ce56a785e40f08c4c3ec5f0648b936b899ee8161c20378cdd9c4f96a30c09a; repository schema diagnostics CLEAR; diff is exactly two deleted env_file lines plus one new regression test.
Learned: Hostinger should not inherit MCP-only environment requirements merely because the toolchain Compose file declares a blanket .env file; host-specific broker/image identity remains owned by the MCP installer and runtime.
Open: New draft PR and exact-head GitHub regression are pending; actual Hostinger revalidation still requires the Hostinger project endpoint/configuration to be reachable.
Next safe step: publish the Draft PR, require terminal CI, then retry the Hostinger update and read back the project state.

### 2026-09-24 — Real Aurion Admin MCP tool-lane integration
Status: PARTIAL — contract/runtime surfaces integrated; authenticated Admin-MCP canary and production activation remain pending
Task: Integrate the existing Aurion Admin MCP as a Sovereign/Sovottt private tool-lane without inventing an API, authority or authentication layer.
Decisions: Reuse the existing HTTPS `/admin-mcp` resource, Aurion's OIDC/JWKS + audience + persisted `role=admin` authority and the three existing scopes; expose the 53 registered Aurion tools through the Sovereign private broker with separate read and write dispatch actions; keep Aurion as final schema/authorization authority; no Keycloak/OAuth/FusionAuth changes and no new public `/admin-*` route.
Touched surfaces: `tools/sovereign-chatgpt-mcp/aurion_admin_mcp_lane.py`, `server.py`, `broker.py`, `command_contract.py`, Docker/install contracts, and regression tests.
Evidence: Uploaded Aurion snapshot fingerprints matched `AURION_ADMIN_MCP_CONTRACT.md`, `server/adminMcp.ts`, `server/adminMcpProtocol.ts`, and `shared/aurionAuthoringContract.ts`; 53-tool registration order and handler mappings captured; Admin-MCP lane tests 11/11 and install contract 21/21; Aurion and MariaDB containers healthy; PatchMon fleet runtime verified; no feature deployment performed.
Learned: Aurion already provides the complete admin authority boundary; Sovereign should remain an adapter/broker lane and must not reproduce Aurion authorization or write logic.
Open: No valid admin OAuth bearer was available for a live privileged `tools/call`; deployed Sovereign MCP still runs revision `5511c638e8ba0384420979692dd63ed7ec1d4b9d` and its immutable digest is not exposed by current readback. Two unrelated baseline suites remain red on fresh main: `test_tool_success_ranking.py` (7 failures) and `test_coordinated_release_reconciler.py` (13 failures).
Next safe step: Review the Draft PR at exact head, obtain authenticated Admin-MCP read/plan canary evidence, then consider deployment/merge only after the normal owner gate.

### 2026-09-24 — Aurion Admin MCP live-count gate final main repair
Status: PARTIAL — exact current-main repair prepared; CI/runtime activation pending
Task: Re-derive the post-merge Aurion Admin MCP live tool-count repair directly from current `main` after the prior PR branch conflicted during synchronization.
Decisions: Preserve the merged 288-tool Private Owner Mode expectation, but make the live FastMCP registry assertion consume `EXPECTED_MCP_TOOL_COUNT` instead of a second hardcoded 258 value; keep 255 for non-owner mode and retain existing Aurion scope/authority boundaries.
Touched surfaces: `tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh`; `tools/sovereign-chatgpt-mcp/tests/test_neuro_deployment_install_contract.py`; `Memory.md`.
Evidence: Fresh workspace based on `main@1f85621741107e7242841f7a87a91a4da2acd04d`; installer patch SHA `497bd98e7f2a92a28e1d5ddc54d8e39f79e472a10d12800908befeaf151b12db`; focused Aurion lane/install tests remain green on the available runtime; local installer-contract execution is CI-owned because PyYAML installation is disabled in the MCP container.
Learned: The merged installer has two independent live tool-count assertions; both must bind to the same computed expectation or revisionsame activation fails closed.
Open: Publish this clean current-main branch, require terminal exact-head CI, then rerun immutable MCP publish/self-update and verify live revision plus digest.
Next safe step: Create the Draft PR and use GitHub Actions as the authoritative dependency/test environment before any merge.

### 2026-09-24 — Aurion Admin MCP post-merge installer count repair
Status: PARTIAL — source repair verified; post-merge runtime retry pending
Task: Repair the private MCP installer count after the merged Aurion Admin MCP lane caused the revisionsame Self-Update to fail at live tool-surface verification.
Decisions: Keep Aurion disabled by default, but in Private Owner Mode count the existing 258-tool surface plus the 30 default read-only Aurion Admin tools, yielding 288; do not broaden scopes or change Aurion authority.
Touched surfaces: `tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh`; `tools/sovereign-chatgpt-mcp/tests/test_neuro_deployment_install_contract.py`.
Evidence: Main merge `ad4df69377eecbc5ba46a4a0bb4c0afdaea87e34`; immutable MCP publish and digest verification run `35957957386` SUCCESS; failed Self-Update stage `verify_live_tool_surface_and_widget_domain`; focused regressions 9/9 installer-contract, 11/11 Aurion lane, 21/21 install-contract plus `git diff --check` green after repair.
Learned: Enabling a gated dynamic MCP surface in the installer requires the live expected tool count to follow the actual scope-gated registration, not the pre-integration baseline.
Open: Repair needs a Draft PR and exact-head CI before another merge; Self-Update had rolled back cleanly and the running MCP remained on the prior verified digest.
Next safe step: Publish the narrow repair, require terminal exact-head CI, then rerun the immutable MCP publish/self-update path and read back revision plus digest.

### 2026-09-24 — Bitcoin full-chain graph × ScaNN × Wolfram evidence lane
Status: PARTIAL; focused repository verification green, full PR suite/live chain ingest pending
Task: Build the internal Bitcoin research pipeline that keeps canonical UTXO/transaction truth separate from approximate retrieval and mathematical counter-checking.
Decisions: Bitcoin Core is the live source boundary; a persistent transactional UTXO/graph store is canonical; ScaNN is candidate retrieval only; exact rescore remains deterministic; Wolfram CAG is supplemental and cannot self-assert VERIFIED; no blockchain attribution is encoded in similarity.
Touched surfaces: `backend/agent_runtime/retrieval/bitcoin_rpc.py`, `bitcoin_graph.py`, `bitcoin_canonical_store.py`, `bitcoin_chain_indexer.py`, `bitcoin_scann.py`, `bitcoin_scann_runtime.py`, `bitcoin_wolfram_contract.py`; shipping mirrors; retrieval regressions; backend CI; architecture documentation; Notion research architecture page.
Evidence: PR #2088 head `f110bae5d2c8032d031b92c6872a17332b1ea87a`; focused Bitcoin Contract job passed compile +  tests on run `35966626003`; GitHub Integration Plan Lane and Continuity runs on the earlier synchronized head passed; live Wolfram kernel counter-checks returned `True`, `True`, and `Sqrt[2]`; Notion architecture page was created and re-fetched successfully.
Learned: A full-chain graph needs same-transaction prevout resolution for intra-block spends and exact integer satoshi accounting; a separate storage boundary prevents ANN similarity from becoming truth.
Open: Current PR's live ScaNN build/readback and full Agent Backend/Release runs are still pending; no real full-chain Bitcoin Core ingestion or production runtime evidence is claimed.
Next safe step: Require terminal exact-head CI, then run the real Bitcoin Core → canonical-store ingest on an authorized node, build/read back the revision-bound ScaNN index, bind real Wolfram CAG receipts, and independently record the resulting evidence before any merge.
