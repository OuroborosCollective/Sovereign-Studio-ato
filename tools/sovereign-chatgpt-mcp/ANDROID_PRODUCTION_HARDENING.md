# Private ChatGPT MCP — Android Production Hardening

This contract applies to Android/Capacitor/React-Native production work performed through the private ChatGPT MCP operator.

## Goal

Produce runtime-backed Android fixes and release evidence without treating UI state, generated output or a successful command exit as proof by itself.

The operator must distinguish:

- source truth;
- generated Android truth;
- Gradle/build truth;
- packaged APK/AAB truth;
- device/runtime truth;
- GitHub CI/release truth.

## Required lifecycle

1. Create an isolated workspace from the current target branch.
2. Run `android_project_inventory`.
3. Run `android_failure_family_scan`.
4. Add real Gradle/logcat/WebView/crash evidence with `android_runtime_evidence_analyze` when available.
5. Build an ordered causal plan with `android_repair_plan`.
6. Fix the first causal family with the smallest exact patch.
7. Add or update a regression test for changed production logic.
8. Rerun the exact failed check from the same family.
9. Scan adjacent families that can be exposed by the fix.
10. Run `android_run_validation_suite`:
    - `fast` while iterating;
    - `standard` before PR/main write;
    - `release` before a release claim.
11. Inspect produced APK/AAB files with `android_artifact_inspect`.
12. Verify GitHub checks with `repository_pr_status`.
13. Rerun failed workflows only through `repository_rerun_failed_workflows`.
14. Merge only with an exact confirmed PR head and green evidence.
15. If private MCP code changed, reload the exact merge revision and retry the original operation.

## Failure-family coverage

The hardening runtime covers at least:

- Android project/platform structure;
- compileSdk, targetSdk and minSdk policy;
- Gradle wrapper, Android Gradle Plugin and Java toolchain drift;
- dependency resolution and duplicate classes;
- manifest merge and exported-component contracts;
- dangerous Android permissions;
- release signing;
- R8/ProGuard and reflection/plugin preservation;
- Capacitor package and native bridge drift;
- WebView navigation, cleartext and TLS failures;
- missing/stale packaged web assets;
- resource linking and AAPT2 failures;
- Kotlin/Java compilation;
- DEX limits;
- crash, ANR and memory failures;
- CI dependency reproducibility and accidental environment output;
- APK/AAB structure, checksum, ABI, signing and alignment evidence;
- multiple Android-surface drift between Capacitor and React Native.

## Evidence rules

A fix is not complete merely because:

- a file was edited;
- Gradle returned zero once;
- a PR exists;
- a container is running;
- an APK/AAB file exists;
- the UI reports success.

Completion requires the relevant combination of:

- exact source diff;
- regression test;
- same-family rerun;
- generated/synced Android state;
- Gradle lint/unit/build evidence;
- package checksum and archive structure;
- signature/alignment evidence when tools are present;
- device/logcat evidence when a device or emulator is available;
- green GitHub checks for the exact commit.

## Repair boundaries

- Never rewrite large existing files blindly.
- Never suppress a compiler, lint, R8 or manifest error without proving why it is safe.
- Never disable TLS verification, release signing or Android security checks as a repair.
- Never fake signing variables to make a readiness check pass.
- Never treat missing Android SDK, emulator or device access as a successful test.
- Never expose keystores, passwords, tokens or environment files.
- Unknown failure families remain explicit blockers until the repair engine is extended and regression-tested.

## Release-ready definition

A release is ready only when:

- zero critical/high release blockers remain;
- relevant type checks and tests pass;
- Capacitor sync/generated assets match source truth;
- Gradle release tasks pass in an environment with the required SDK and signing material;
- APK/AAB artifacts are non-empty and structurally valid;
- checksums are recorded;
- APK signing/alignment is verified when applicable;
- the exact release commit and CI run are identified;
- no new causal runtime error appears in post-fix evidence.
