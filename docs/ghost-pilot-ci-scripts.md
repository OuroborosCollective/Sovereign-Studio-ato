# Ghost Pilot CI Scripts

The Ghost Pilot workflow uses helper scripts under `.github/scripts`.

- `ghost-pilot-generate-sequence.sh` builds a Gemini-generated ADB test sequence or falls back to a deterministic local path.
- `ghost-pilot-fallback-adb.sh` is the deterministic fallback interaction path.
- `ghost-pilot-selfcheck.sh` validates fallback quality without starting an emulator.

These scripts exist outside YAML so agents can review and maintain the logic without editing a long inline workflow block.
