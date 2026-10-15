# PR backlog integration — 2026-10-02

Baseline: `bc51ae5f1d24de3b185cef2456a4f4b9643b05ba`.
Scope: owner-requested review of all 16 open PRs; integrate useful changes and close unsafe, empty or superseded proposals. Frontend and backend remain one architecture. This document describes the containing revision, not a production deployment.

## Decisions

| PR | Decision | Bounded rationale |
| --- | --- | --- |
| #2172 | Integrate with repair | PyJWT 2.15.0; update the installer contract's stale exact-version expectation. The predecessor's sole failed MCP test expected 2.13.0. |
| #2170 | Integrate | Memoize Observatory aggregates and sort normalized day keys; test cross-month/year density order. |
| #2168 | Integrate with repair | Semantic pattern lists, accessible labels and unique React heading IDs. Scope labels describe source provenance, not an unverified execution location. |
| #2167 | Integrate selected source | Chat loading/disabled states and tooltips. Exclude one-off patch scripts and generated reports. |
| #2166 | Close empty | No changed files relative to main. |
| #2161 | Close unsafe | Unconditional Map.set changes duplicate-ID matching from first match to last match without a compatibility regression. Preserve the existing contract. |
| #2159 | Integrate selected source | Question-card focus/decorative-icon accessibility and tests; omit already-applied duplicate-import cleanup. |
| #2158 | Integrate | Tenant, organization and license secret-label redaction with regressions. |
| #2156 | Close disconnected | Legacy BuilderContainer/ChatLine produces fallback metadata, while a separate vNext message surface consumes it without a demonstrated mapping; removing the old notice can lose feedback. Record<string, any> also weakens the message contract. |
| #2154 | Integrate selected source | Header utility accessible names and tooltips; exclude unrelated lint/scanner/report churn. |
| #2150 | Integrate | Bounded processing preserves order, normalization and limits in existing persistence, memory and mobile owners. Add a snapshot cap regression. |
| #2149 | Integrate | Result-card semantic list, hover/focus treatment and accessibility regressions. |
| #2148 | Close unsafe | Identity caching does not establish immutable provenance for every structurally typed public input; mutation can stale hashes/triggers and a rejected promise remains cached. No invalidation/failure contract provided. |
| #2147 | Integrate together with #2158 | Private-key passphrase redaction; resolve overlapping regex and fixture changes without dropping either fix. |
| #2146 | Integrate selected source | Reuse the existing ChatMarkdown renderer in vNext; verify code copy and unsafe-link handling. Exclude generated artifacts. |
| #2144 | Integrate unique portion | Solution-pattern step cap; other changes overlap #2150 and are included once. |

## Unified architecture corrections

The production build exposed three pre-existing main contracts. The repository adapter's interface-only method cannot use an override modifier. The request type must match the existing cloneRepo=false implementation. An accepted abort must not invent a CANCEL reducer event or declare execution cancelled: the job hook invalidates its query, independently reads the backend and projects its phase. A transport-boundary regression keeps EXECUTING visible when the backend still reports running after accepting abort.

No new runtime, queue, memory store or backend owner was introduced. Canonical backend and deployment mirror files are unchanged.

## Evidence and limits

- Focused frontend regression set: 169 passed across 12 files.
- Adapter, execution feedback, agent contract and ChatSurface set: 25 passed across four files.
- MCP authentication and installer contract selection with actual PyJWT 2.15.0 installed: 16 passed.
- Release gate: endpoint assurance and 25 endpoint tests; 3,830 smoke tests passed, two skipped; 90 integration tests passed; LLM/runtime boundary gate passed. Re-executed after the build contract fixes; authoritative exact-head results are the associated GitHub checks.
- Web production build, sharded TypeScript checks, static audit and artifact/Android-handoff smoke passed locally.
- Static architecture inventory, snapshot, drift report and enterprise backend assessment ran against this workspace. The drift report's 104 P1 candidates and zero P0 candidates are bounded static classifications, not independently verified runtime defects; inventories are truncated and do not prove completeness.
- Local Playwright browser installation failed because the downloaded Chromium archive was invalid. Browser E2E must be checked through CI; no local browser-E2E success is claimed.

State before publishing: TESTED_AT_REVISION locally; exact-head CI pending. Integration merge must use the reviewed SHA, terminal applicable green checks and fresh mergeability. Only after merge should the twelve incorporated originals be closed as superseded. Re-read main and the open-PR collection afterward. Neither CI nor this review establishes production RUNTIME_VERIFIED status.
