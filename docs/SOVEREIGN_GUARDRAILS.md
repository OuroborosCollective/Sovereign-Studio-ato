# Sovereign Studio Guardrails

These rules define the non-negotiable truth path for Sovereign Studio. A feature is not ready when it only looks green. It is ready when the live GitHub-first path, runtime checks, validations and tests agree.

## Product Direction

Sovereign Studio is a GitHub-first no-code tool. The app should help a user connect a repository, inspect it, generate or repair changes, publish guarded Draft PRs, watch GitHub results and learn from accepted solution patterns.

The Android app is the primary user-facing build artifact. The web UI that Capacitor packages into Android must be the current live app, not a legacy shell, stale preview path or test-only screen.

## Truth Path Rules

- GitHub is the source of truth for generated changes, PR state, workflow results and release readiness.
- No fake green state is allowed. A screen may show pending, unknown, blocked or failed, but it must not show green unless the real validation path supports it.
- No mock, stub or facade may be treated as the live truth path.
- Demo/local fallback behavior must be visibly labeled as demo, local or diagnostic and must not unlock release/merge success states.
- PR generation must publish the actual generated package files, not only preview/audit artifacts.
- Runtime checks must block unsafe or incomplete packages before PR creation.

## Remote Memory Rules

- Remote Memory Gateway is optional and consent/opt-in gated.
- Frontend code must not depend directly on a memory database implementation.
- Contributor submissions must stay separated from shared-derived patterns.
- User erasure may delete contributor identity and user-submitted summaries while preserving shared-derived patterns when policy allows.
- Pull updates may enrich the local Aha/Solution Pattern Store only through validated gateway/intake logic.
- Remote memory failures must degrade gracefully and visibly; they must not fake successful sync, learning or validation results.

## App Bridge Rules

- App Bridge integration must keep clean runtime checks, validations and tests.
- Every route, action chain and analysis-to-result-to-action loop should have explicit guards when it affects user trust or release output.
- Live Android/Web entry points must render the current Sovereign container app.
- Legacy UI or old hook paths must be removed, hard-deprecated or blocked from publishing live PRs.

## Runtime, Validation and Test Rules

Required for any meaningful logic change:

1. Runtime check for invalid state or unsafe input.
2. Validation/reporting that explains what happened.
3. Unit or integration test that proves the intended behavior.
4. UI state that distinguishes pending, blocked, failed and green.
5. GitHub workflow coverage where the behavior can break release output.

For generated PR workflows, tests must verify that README/docs requests produce the expected file set and cannot degrade to a single preview file such as `generated/sovereign-product/workflow.ts`.

## Release Rules

- Android release workflows must build the current web app, sync Capacitor, sign the release AAB/APK with the configured signing key and upload artifacts.
- Release readiness checks must inspect the real Gradle build type and manifest values, not unrelated blocks or stale assumptions.
- AAB/APK artifacts must include checksums and clear names.
- Play readiness must use current Google Play requirements, including target SDK policy.

## Review Checklist

A PR should not be merged when any of these are true:

- It only creates a preview artifact instead of real generated files.
- It bypasses GitHub-first validation.
- It marks fake/diagnostic/local results as green.
- It adds direct frontend coupling to a memory database.
- It mixes contributor-submitted memory with shared-derived patterns without gateway validation.
- It changes live app entry points without tests.
- It changes Android release output without checking signing, artifacts and readiness.
- It introduces mock/stub/facade truth paths into the live product flow.
