# Ghost Pilot Agent Compliance

This change follows the repository agent rules by keeping the product surface untouched and moving CI logic into versioned helper scripts.

## Protected product rules

No UI layout or product behavior files are changed. The left repository tree, center chat/editor/status surface, right history/analysis surface, free-first routing, visible fix loop, and confirmation rules are not modified.

## Guard rules

The workflow calls the required green gate before Android emulator execution:

- `audit:sovereign`
- `type-check`
- `test:run`
- `build`

It also runs `scripts/check-guard-config.mjs` before those commands.

## Android package

The Ghost Pilot app package is set to `com.arestudio.nocode.aab`, matching `android/app/build.gradle`.
