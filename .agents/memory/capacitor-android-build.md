---
name: Capacitor Android build env requirement
description: Why local Android (cap sync / build:aab) fails on Node 20 and what this container can and cannot validate.
---
# Capacitor Android build in this repo

- The Capacitor CLI (`@capacitor/cli` v8) requires **Node >= 22**. Under Node 20 the
  web build (`tsc && vite build`) succeeds but the final `cap sync android` step of
  `npm run build` / `build:aab` fails with "The Capacitor CLI requires NodeJS >=22.0.0".
  **Fix:** keep the `nodejs-22` module installed (CI already pins Node 22).

- This isolated container has **no Android SDK, no ANDROID_HOME, no emulator/device,
  and no signing keystore/secrets**. A real signed `gradlew bundleRelease`/`assembleRelease`
  and on-device "keys persist across cold starts" test **cannot run here** — that path
  is the GitHub Actions workflow `.github/workflows/android-release.yml`, which provisions
  JDK 21 + SDK and injects `ANDROID_KEYSTORE_*` secrets.

- What IS locally verifiable: full web build + `cap sync` (copies the React bundle into
  `android/app/src/main/assets/public`, registers @capacitor/preferences for Android),
  correctness of the synced index.html (React shell, not the old canvas artifact),
  signing config wiring in `android/app/build.gradle`, and clean app launch (no JS errors).

- Key persistence: `src/features/ai/keyStorage.ts` uses `@capacitor/preferences` with a
  localStorage migration/fallback; all keys (Gemini, GitHub, repo, Groq, HF, Together,
  OpenRouter) are written through it from `src/ProductMagicApp.tsx`.
