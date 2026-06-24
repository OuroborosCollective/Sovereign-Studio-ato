# Launch Readiness

This checklist defines when Sovereign Studio can be treated as a release candidate. CI is required, and real Android smoke testing is still required after an APK is produced.

## Current readiness model

A release candidate needs evidence in four areas:

1. Repository truth: real repo tree loaded, no mock snapshot in the live path.
2. Code truth: TypeScript, unit tests, web build and static audit pass on the relevant commit.
3. Runtime truth: runtime, UX and live-path contracts confirm the app is using runtime sources.
4. Device truth: Android artifact installs and runs on a real device or emulator.

## Automated gates

Required green checks for the release commit or PR head:

- TypeScript type check
- Unit tests
- Web build
- Sovereign static and security audit
- Runtime contract scan
- UX contract scan
- Live-path scan
- Android debug APK build

## Android smoke checklist

Run this after downloading the APK artifact:

- App starts without a blank screen or boot-fatal overlay.
- Repo URL input is usable on phone and tablet layouts.
- Secret input text is not leaked into telemetry, summaries or errors.
- Repo loading reaches a visible ready, degraded or error state.
- Auto Review and Full Auto stay blocked until repo, mission and credential requirements are real.
- Automation waits for runtime busy state and does not rapid-loop through UI tabs.
- More-menu navigation works on narrow Android WebView widths.
- Rotation does not hide primary actions.
- Draft PR flow creates a branch and Draft PR only after review guards pass.
- Workflow watch displays GitHub check state from the produced commit.

## Risk register

| Risk | Severity | Release action |
| :--- | :--- | :--- |
| Generated docs contain prompt transcripts instead of product documentation | High | Block merge and rewrite docs into user-facing content. |
| No fresh workflow run for target commit | High | Trigger CI, release and Android checks before approval. |
| APK built but not device-tested | Medium | Treat as build-ready, not Play-Store-ready. |
| Branch protection not confirmed | Medium | Require PR checks before default-branch merge. |
| License or distribution status unclear | Medium | Keep private status or document distribution policy. |

## Owner checklist

- [ ] Lead Engineer: review README and docs for accuracy.
- [ ] DevOps: verify CI workflow names and required checks.
- [ ] QA: run or review TypeScript, unit, build, runtime contract and Android APK results.
- [ ] Android tester: install artifact and complete smoke checklist.
- [ ] Product Owner: approve release notes and known limitations.

## Release state language

Use these labels honestly:

- Not ready: required checks missing or failing.
- CI green: automated checks passed, but Android device behavior is not proven.
- APK candidate: Android artifact exists and is not expired.
- Play-Store test candidate: CI is green and Android smoke test passed.
