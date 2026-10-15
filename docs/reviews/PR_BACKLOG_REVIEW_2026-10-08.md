# PR backlog review — 2026-10-08

Baseline main: `b2e301ed164189ec42011229b559038a202982f6`. Owner authorized processing all open PRs by selective integration, merge or close, ending with zero open PRs. Agent Zero must remain excluded. This document records repository review, not deployment or live provider success.

| PR | Reviewed head | Disposition |
|---|---|---|
| #2198 | `38784da1d36b4043858e200742bebc6f692eb1e6` | Close: localeCompare was replaced with lexical ordering, changing equal-time parent lineage; no semantic regression evidence supplied. |
| #2200 | `27d7655deb0e82e13f11f0ab0de4bf9f24bc807c` | Select only bounded log filtering. Exclude unrelated workflows/generated reports and weakened liveSessionContract assertion. |
| #2201 | `c13afe89cc638ec1ca3ba6d193958e9f31e345cf` | Close: disabled-control title patch is duplicated by #2207 and does not establish keyboard-accessible disabled reasons; retain current controls. |
| #2203 | `ed6a25f197e9d0a8cefb31a749471dabfee2aa8d` | Select accessibility changes; replace fixed heading ID with React useId for multiple instances. |
| #2204 | `b2e1c9d10a867fbe753a9f3d736ba74ce2442841` | Close: deleting map entries changes duplicate tick-range semantics and mismatch ordering without contract evidence. |
| #2206 | `ebc9e2a8b5fcad0d6f15c4570ba1d91f46f7c190` | Select bounded directory iteration; verify first-20 input window and first-three unique order. |
| #2207 | `17406c7eb95b8964174b15f119e2905b4c445ed6` | Close: duplicates #2201 and includes patch.js/generated noise; retain current controls. |
| #2208 | `2d29d393be62f2b2a9a9495d052a558a40301435` | Close: Agent Zero is excluded by explicit owner direction; route strings and visible root are not functional runtime proof. |
| #2209 | `e278936cdc32d81f0ade853bbe1e233651c4ede6` | Select semantic error lists/headings; replace fixed heading ID with React useId. |
| #2210 | `f149daca8c80de29e33a59b9c2d48db28b6b963e` | Select ElevenLabs/Stability/Fal labels while preserving existing provider labels, whitespace and token boundaries. |
| #2211 | `c7f711a06eb99e61781fbe1ca40809f4ee94a4ca` | Close: duplicate lineage sorting proposal with changed collation semantics. |
| #2212 | `1cf4daa292751fbb2796c447a3c7140ea54fb4a9` | Select last-200 slice before sanitization; verify retained order, sanitization and unchanged input. Exclude generated reports. |
| #2216 | `6149a0515318cd9bed58da26721318bc7578ddd3` | Select @capacitor/ios 6.2.2 with exact lock integrity; resolved against existing core 6.2.1. |
| #2218 | `de6ea41653ebf1c4b4dbecce65cf553182bb51d5` | Select @capacitor/android 6.2.2 with exact lock integrity; resolved against existing core 6.2.1. |
| #2219 | `95268d6ab4cc687fb4ea0664efa117cc5a7996ff` | Select four-layer Observatory and live runner. Add validation of Wolfram source/tool/time after adversarial rehash, and bind Notion index to same run digest and hexadecimal commit. |
| #2220 | `7b5bc78ab6587c6b7e742c0118e09b5c717e7b36` | Select native SDK handoff, shared real Git diff including empty untracked files, bootstrap causal error and terminal readback. EXCLUDE _empty_file_addition_regression and all exemption-specific behavior; full regression gate remains. No new STRUCTURED_POLICY classification granted. |

## Validation before final-head CI

- Frozen install: pnpm 9.12.2 `install --frozen-lockfile --ignore-scripts` succeeded (573 packages); no lock changes from install. Native iOS/Android package source contains the internal HTTP interceptor navigation guard. No device runtime or native build is claimed locally.
- Targeted Vitest: five files, 132 passed (terminal readback, workspace events, directory ordering, accessibility, credential redaction).
- Observatory Python: 85 passed across new four-layer/live-runner and neighboring gate, publisher and staging tests. Adversarial rehash and cross-run publication counterexamples failed before the repairs and pass after them.
- Backend Python: 30 passed across native SDK handoff, actual Git empty-file diff, execution authorization and repository tools. The installed OpenAI Agents SDK is real; the model and database adapter boundaries are test fixtures. Test-only source/image identity is explicitly synthetic, not deployed attestation.
- Canonical backend and deployment mirrors remain byte-equivalent. Boundary ledger reconciliation preserves all 81 existing classifications, adds none and refreshes three stale bindings; no owner classification is invented.
- Final immutable PR head must pass required GitHub checks before merge. The review deliberately retains existing regression, permission and publication gates.

## Limits and deferred work

The empty-file regression exemption in #2220 is not integrated. Empty-file missions still face the normal independent regression/bootstrap path; neither recovery of a historical run nor deployed runtime success is claimed. Original PR head remains named above for future explicit review. No HF dataset publication, Wolfram request, Notion mutation, deployment, Agent Zero invocation or self-update is part of this backlog operation. Source-map-js #2217 was independently merged before this baseline; its security review is recorded in Memory.md.

After the consolidation passes exact-head CI and merges, originals are to be closed with their selective-integration or exclusion reasons, and GitHub open PR state must be freshly read back.
