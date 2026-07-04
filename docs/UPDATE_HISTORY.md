# Update History

This file records user-facing Sovereign Studio changes in plain language. It is intentionally separate from generated package previews so release notes stay readable and reviewable.

## 2026-07-04 — Chat-first runtime truth and capability routing baseline

### Changed

- Updated the public README from the older V3 repository-architect framing to the current Sovereign Studio ATO product truth: chat-first, Android-first, runtime-first, Draft-PR-only.
- Added `docs/SOVEREIGN_CAPABILITY_ROUTING.md` to explain the route split between worker/model chat, Direct GitHub Patch, workspace executors, OpenHands and Draft PR runtime.
- Updated `docs/SOVEREIGN_RUNTIME.md` with the current truth path: intent detection, repo gate, GitHub API write validation, capability routing, action stream, active blockers and workflow watch.
- Expanded `docs/SOVEREIGN_PRODUCT_TRUTH.md` with the current no-drift rules: no fake truth, no hard percent progress, no live mocks, no Plan-only PR, no OpenHands lock-in, no secret leakage.
- Updated `docs/GITHUB_AUTH_SESSION.md` to reflect real GitHub API validation and Android clipboard guidance.
- Rewrote `docs/SOVEREIGN_READER.md` as the current handoff for future agents.
- Updated `.agents/skills/sovereign-studio-agent/SKILL.md` to guide future agents toward branch/Draft PR work, runtime modules and capability routing instead of direct main-push assumptions.

### Why it matters

The product had moved beyond the old linear “repo → readiness → package → Draft PR” documentation. Current behavior now includes chat-first repo operation, GitHub API access validation, inline action tracing, local runtime answers and emerging capability routing. Without updated docs, future agents are likely to drift back into dashboard UI, OpenHands-only write routing or fake success states.

### Current architecture issues

These issues describe the next implementation path:

- `#500` Route write intents after GitHub ready without OpenHands lock-in.
- `#501` Direct GitHub Patch route for README/docs changes.
- `#502` Sovereign Capability Router.
- `#503` Agent-neutral Workspace Runtime.
- `#504` Active blocker dedupe and honest status.
- `#505` Credential handling and Android clipboard guidance.

### Validation target

This is a documentation-only baseline update. It should still pass the usual docs-safe gates:

```bash
pnpm run type-check
pnpm run test:unit
pnpm run build:web
```

No CI green should be claimed unless GitHub workflow runs or local logs prove it.

## 2026-06-24 — Release-readiness documentation hardening

### Changed

- Restored the README as a real user entry point instead of a generated prompt transcript.
- Added a clearer runtime-truth explanation for repo loading, package generation, Draft PR publishing and workflow watching.
- Added a launch-readiness checklist that separates automated GitHub checks from required real Android smoke testing.
- Documented the current provider and brain-gate rule: provider output is input, not truth, until runtime contracts and generated-file guards accept it.

### Why it matters

A green workflow is useful, but it is not enough by itself. Release readiness must stay tied to real repository state, real TypeScript/tests/build output, real GitHub Actions results and real Android behavior.

### Validation target

Before this PR can be merged, the relevant commit should show green results for:

- `pnpm run type-check`
- `pnpm run test:unit`
- `pnpm run build:web`
- `pnpm run audit:sovereign`
- Runtime/UX/live-path contract scan
- Android debug APK build

## Current product baseline

Sovereign Studio ATO is a guarded chat-first repository workbench:

1. Load a GitHub repo snapshot through chat or setup.
2. Detect intent and route the request through runtime capabilities.
3. Validate GitHub write access through the GitHub API before writes.
4. Use the smallest safe route: worker/model chat, Direct GitHub Patch, workspace/OpenHands or Draft PR runtime.
5. Review generated changes and diffs.
6. Publish only as a Draft PR.
7. Watch workflows and route failures into repair guidance.

## Open release note

Play-Store readiness still requires a real Android device or emulator smoke test after the APK artifact is produced. Automated APK build success does not prove WebView startup, layout, rotation, secure access handling or touch navigation on real devices.
