# Runtime Dependency Surface

This note documents the runtime dependency surface added for the Sovereign operator coach.

## Scope

The dependency surface keeps the latest runtime dependency signals visible in the browser session.

Covered dependency signals:

- GitHub
- Workflow
- Remote Memory
- Pattern Memory
- Runtime
- Telemetry

## Persistence

Dependency signals are stored in memory and mirrored into session storage.

Storage keys:

- `sovereign-dependency-signals`
- `sovereign-dependency-telemetry`

The data is intentionally session-scoped because dependency health is runtime status, not durable user memory.

## Limits

- Dependency signals: latest 8
- Dependency telemetry events: latest 25

## Safety

The surface is browser-only and guarded by DOM checks. It must not block the main app if storage or monitor rendering is unavailable.
