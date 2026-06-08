# Ghost Pilot Selfcheck

The branch includes `.github/scripts/ghost-pilot-selfcheck.sh` as a local CI helper for the fallback path.

It verifies that fallback generation:

- writes `ghost_pilot_status.txt`,
- uses `DEGRADED_BUT_TESTED`,
- launches the configured Android package,
- creates at least the configured number of ADB input commands,
- creates at least the configured number of meaningful tap/text/swipe commands.

Run it from the repository root:

```bash
bash .github/scripts/ghost-pilot-selfcheck.sh
```

The main workflow still runs the full Sovereign green gate and the real emulator path. This helper exists so agents can validate fallback quality without waiting for an emulator.
