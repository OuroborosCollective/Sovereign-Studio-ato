# Open PR backlog review — 2026-10-04

Scope: all eight open pull requests observed after main `4b27d296fdb5a99c87c5fa527bcac36894cc0f3c`.

The review treats CI/runtime evidence as authoritative and does not preserve changes merely because an older head was green. Useful changes are re-derived on current main; generated evidence files from stale heads are not copied.

| PR | Decision | Reason |
| --- | --- | --- |
| #2185 | salvage | Bounded string-list parsing is behavior-preserving and now has an oversized-evidence regression. |
| #2184 | salvage with repaired tests | Semantic lists, labelled region and focus-visible disclosure are useful. The original Release Verification failed because its new test queried hidden `details` content without opening the disclosure; stale generated security reports are intentionally not carried forward. |
| #2183 | reject | The proposed routing micro-optimization shipped two failing PAL regressions on its own exact head. The performance claim is unbenchmarked and does not justify changing routing code. |
| #2182 | salvage | Provider-specific AI/cloud credential labels improve masking coverage; the consolidated change adds quoted-label and plain-prose false-positive tests. |
| #2181 | reject | WeakMap token caching adds persistent cache semantics and a claimed ~5x speedup without benchmark evidence. The current planner has no demonstrated bottleneck requiring this complexity. |
| #2179 | salvage with repaired tests | Semantic landmarks/lists and keyboard-visible disclosure are useful. The original Release Verification failed because the new test queried hidden launch-markdown content before opening `details`. |
| #2178 | reject | The patch moves a runtime fallback notice into presentation metadata, but BuilderContainer's canonical `ChatLine` contract does not own that metadata and the Control Surface `ChatMessage` type is a separate surface. This weakens the explicit runtime-notice truth boundary rather than safely styling it. |
| #2175 | reject | Native `title` on disabled decision buttons is not a reliable accessibility path: disabled HTML controls are removed from keyboard focus and commonly suppress pointer interaction. Existing visible labels already communicate the submitting state. |

## Consolidated changes

- `githubOpenPrReviewRuntime`: cap string evidence during parsing rather than after allocating oversized intermediate arrays.
- `crypto.maskSecrets`: cover DeepSeek, Perplexity, Replicate and Cloudflare credential labels while retaining assignment syntax and false-positive regressions.
- `ScanFindingRegistryPanel`: labelled region, semantic finding/history lists and focus-visible native disclosure controls.
- `RepoReadinessPanel`: labelled region, semantic progress/risk/checklist structures and keyboard-focusable launch markdown after explicit disclosure.
- Regression tests are colocated with each rescued behavior.

## Evidence handling

Older PR heads are historical evidence only. Three original Release Verification runs were red:

- #2184: `PaletteEnhancements.palette.test.tsx` failed in the Scan Finding accessibility case.
- #2183: two `builderPALRuntime.test.ts` cases failed.
- #2179: `PaletteEnhancements.palette.test.tsx` failed in the Repo Readiness accessibility case.

The consolidated PR must establish fresh exact-head CI. No production runtime claim is made by these UI/parser/security changes.
