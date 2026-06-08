# Ghost Pilot PR Summary

## Summary

This branch hardens the Android Ghost Pilot workflow so a failed model call can no longer collapse into a false-green one-command test.

## Changes

- Replaced the hard-coded deprecated Gemini model with configurable modern fallback order.
- Added deterministic ADB fallback script.
- Added quality validation for generated ADB scripts.
- Added real package launch default: `com.arestudio.nocode.aab`.
- Added Sovereign green gate before emulator execution.
- Added Android debug APK build and install before ADB execution.
- Added docs and a fallback selfcheck helper.

## Validation intent

The workflow now runs:

```bash
node scripts/check-guard-config.mjs
pnpm run audit:sovereign
pnpm run type-check
pnpm run test:run
pnpm run build
npx cap sync android
cd android && ./gradlew assembleDebug --stacktrace
```

Then it generates or falls back to a validated ADB sequence, installs the debug APK, and scans emulator logs for app fatal runtime errors.
