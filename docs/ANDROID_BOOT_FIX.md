# Android Boot Fix

## Symptom

The Android app can show only `Loading Refactor` forever.

## Root cause

The committed Android WebView HTML referenced hashed bundle files under `android/app/src/main/assets/public/assets/`, but the referenced files were not present in the repository snapshot. When the WebView cannot load the bundle, React never mounts and the static loader stays visible.

## Applied mitigation

`android/app/src/main/assets/public/index.html` now contains a small defensive boot fallback. If the bundle does not mount after startup or the bundle load throws, the user gets a visible recovery surface instead of a black endless loader.

## Permanent release path

Run the normal build and sync flow so Capacitor copies the current bundle into Android assets:

```bash
npm ci
npm run build
```

The app should follow this AI provider order by default:

1. mlvoca without key
2. Pollinations without key
3. optional user-owned keys

GitHub PAT and AI keys must stay separated. The GitHub PAT is only for repository fetch/update. AI providers must not be hard-required at app boot.
