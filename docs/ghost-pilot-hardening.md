# Ghost Pilot Android Test Hardening

This workflow intentionally treats AI-generated test scripts as untrusted input.

## What changed

- Removed the hard-coded `gemini-1.5-flash` single point of failure.
- Added model fallback order:
  1. `vars.GEMINI_MODEL`, when configured
  2. `gemini-2.5-flash`
  3. `gemini-2.5-flash-lite`
  4. `gemini-flash-latest`
- Added deterministic fallback ADB sequence when Gemini is unavailable, returns HTTP errors, or emits a weak script.
- Added a quality gate so scripts with only `HOME` / `BACK` or too few commands are rejected.
- Whitelisted generated commands to `adb shell input ...` only.
- Changed crash scan to fail on app runtime fatal errors while avoiding false positives from unrelated `SystemUI` ANRs.
- Runs the repository green gate before the emulator phase.
- Builds and installs the debug APK before running the ADB sequence.

## Configuration

Optional repository variable:

```text
GEMINI_MODEL=gemini-2.5-flash
```

Workflow env defaults:

```text
GHOST_PILOT_APP_PACKAGE=com.arestudio.nocode.aab
GHOST_PILOT_MIN_COMMANDS=8
GHOST_PILOT_MIN_MEANINGFUL_COMMANDS=4
```

The Android package follows `android/app/build.gradle` and must stay aligned with the app `applicationId`.

## Sovereign guard alignment

The workflow runs the repository green gate before the emulator test:

```bash
node scripts/check-guard-config.mjs
pnpm run audit:sovereign
pnpm run type-check
pnpm run test:run
pnpm run build
```

This keeps the workflow aligned with `AGENTS.md` and `sovereign.guard.json`.

## Artifact interpretation

`ghost_pilot_status.txt` can contain:

- `AI_GENERATED_AND_VALIDATED: <model>` — Gemini generated a usable sequence.
- `DEGRADED_BUT_TESTED: missing GEMINI_API_KEY` — no secret was available, fallback ran.
- `DEGRADED_BUT_TESTED: Gemini unavailable or returned weak sequence` — Gemini failed or returned a sequence that did not pass the quality gate.

A degraded run is still a real emulator interaction path. It must not silently collapse to a single `adb shell input keyevent 3` command.

## Safety rule

The workflow does not execute arbitrary shell commands returned by the model. It only accepts lines matching:

```bash
adb shell input tap ...
adb shell input text ...
adb shell input keyevent ...
adb shell input swipe ...
```
