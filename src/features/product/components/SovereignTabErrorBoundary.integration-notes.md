# Sovereign Tab Error Boundary Circuit

Small Lego block for tab-level resilience.

## Purpose

- Isolate crashes to one tab.
- Keep Repo, Builder, Files, Diff, Workflow, Repair and Telemetry usable when one tab fails.
- Publish runtime coach events through `sovereign:runtime-coach-state`.
- Publish tab boundary events through `sovereign:tab-boundary-state`.
- Use a small circuit lifecycle: `closed -> open -> half-open -> closed`.

## Intended App wiring

Wrap each visible tab panel in `SovereignTabErrorBoundary`:

```tsx
<SovereignTabErrorBoundary
  tabId="remote"
  tabLabel="Remote Memory"
  onRuntimeEvent={(event) => pushTelemetry('ui', event.phase === 'open' ? 'error' : 'warning', `tab:${event.tabId}:boundary`, event.message, {
    tab: event.tabId,
    phase: event.phase,
    failures: event.failures,
  })}
  onOpenTelemetry={() => setActiveTab('telemetry')}
>
  <RemoteMemoryContainer ... />
</SovereignTabErrorBoundary>
```

## Chaos smoke idea

Use a test-only throwing component inside a wrapped tab. Expected result:

1. The wrapped tab shows the boundary fallback.
2. Telemetry receives a `ui` warning/error.
3. The mobile coach receives a yellow/red runtime event.
4. Other tabs remain usable.

No live chaos injection is enabled by default.
