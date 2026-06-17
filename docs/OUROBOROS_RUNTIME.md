# Ouroboros Runtime

Ouroboros is the app's typed runtime control layer for root initialization, auth sequence state, ARE payload state, consent-aware pattern references, resonance signals, telemetry, and invariant reports.

It is not a background AI loop and it does not directly read or write the Remote Memory database. Remote Memory stays behind the configured gateway and bridge layers.

## What the runtime owns

The Redux slice at `src/features/ouroboros/ouroborosSlice.ts` owns:

- root initialization state
- auth sequence state
- active ARE payload state
- current error state
- typed telemetry event
- typed resonance signal
- consent-aware active pattern reference
- latest guard report

The runtime validator at `src/features/ouroboros/ouroborosRuntime.ts` owns:

- state invariant checks
- structured violation messages
- assertion helper for hard runtime checks
- serializable guard report generation
- stable state hash generation that excludes the previous guard report

## Guarded invariants

`validateOuroborosState` rejects:

- auth sequence active before root initialization
- active ARE payload without active auth sequence
- resonance strength outside 0..1
- negative resonance reinforcement count
- invalid resonance timestamp
- resonance consent mismatch
- consent state with invalid grant/revoke timestamps
- invalid telemetry timestamp

## Determinism rules

Reducers do not call `Date.now()`.

Time values must be provided through explicit action payloads or runtime report options. This keeps reducers reproducible and testable.

`buildOuroborosRuntimeReport` may use the current time only when no `checkedAt` option is passed. Tests pass fixed timestamps.

## Consent boundary

Ouroboros may store a consent-aware pattern reference, but it does not grant global memory access by itself.

Remote pull/update flows must still use the Remote Memory Gateway and bridge/intake validation before any pattern becomes locally usable.

## Tests

Covered by:

- `src/features/ouroboros/ouroborosSlice.test.ts`
- `src/features/ouroboros/ouroborosRuntime.test.ts`
- `src/store/hooks.test.tsx`

These tests verify typed reducer behavior, runtime invariant failures, guard report generation, and selector compatibility with the store state shape.
