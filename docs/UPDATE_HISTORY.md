# Update History

This file records user-facing Sovereign Studio changes in plain language. It is intentionally separate from generated package previews so release notes stay readable and reviewable.

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

Sovereign Studio V3 is a guarded repository workbench:

1. Load a GitHub repo snapshot.
2. Analyze readiness and risk.
3. Build a brain-gated implementation package.
4. Review generated files and diffs.
5. Publish only as a Draft PR.
6. Watch workflows and route failures into repair guidance.

## Open release note

Play-Store readiness still requires a real Android device or emulator smoke test after the APK artifact is produced. Automated APK build success does not prove WebView startup, layout, rotation, token masking or touch navigation on real devices.
