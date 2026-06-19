import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SovereignTabErrorBoundary, type SovereignTabBoundaryEvent } from './SovereignTabErrorBoundary';

function ThrowingPanel({ message = 'boom' }: { message?: string }): React.ReactElement {
  throw new Error(message);
}

function RetryHarness({ onRuntimeEvent }: { onRuntimeEvent: (event: SovereignTabBoundaryEvent) => void }): React.ReactElement {
  const [broken, setBroken] = useState(true);

  return (
    <SovereignTabErrorBoundary
      tabId="remote"
      tabLabel="Remote Memory"
      onRuntimeEvent={onRuntimeEvent}
      policy={{ failureThreshold: 3, cooldownMs: 1000, halfOpenMaxAttempts: 1 }}
    >
      {broken ? <ThrowingPanel /> : <button type="button" onClick={() => setBroken(true)}>healthy</button>}
      <button type="button" onClick={() => setBroken(false)}>repair child</button>
    </SovereignTabErrorBoundary>
  );
}

describe('SovereignTabErrorBoundary', () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it('renders children while the tab is healthy', () => {
    render(
      <SovereignTabErrorBoundary tabId="repo" tabLabel="Repo">
        <div>Repo content ready</div>
      </SovereignTabErrorBoundary>,
    );

    expect(screen.getByText('Repo content ready')).toBeDefined();
  });

  it('isolates a crashing tab and reports a masked runtime event', () => {
    const events: SovereignTabBoundaryEvent[] = [];

    render(
      <SovereignTabErrorBoundary tabId="builder" tabLabel="Builder" onRuntimeEvent={(event) => events.push(event)}>
        <ThrowingPanel message="token=super-secret-value exploded" />
      </SovereignTabErrorBoundary>,
    );

    const fallback = screen.getByTestId('sovereign-tab-error-boundary');
    expect(fallback.getAttribute('data-tab-id')).toBe('builder');
    expect(fallback.textContent).toContain('Builder');
    expect(fallback.textContent).not.toContain('super-secret-value');
    expect(events.length).toBeGreaterThan(0);
    expect(events[0].message).not.toContain('super-secret-value');
  });

  it('opens the circuit after repeated tab failures', () => {
    const events: SovereignTabBoundaryEvent[] = [];
    let now = 1000;
    const { rerender } = render(
      <SovereignTabErrorBoundary
        tabId="workflow"
        tabLabel="Workflow"
        nowMs={() => now}
        onRuntimeEvent={(event) => events.push(event)}
        policy={{ failureThreshold: 1, cooldownMs: 10_000, halfOpenMaxAttempts: 1 }}
      >
        <ThrowingPanel />
      </SovereignTabErrorBoundary>,
    );

    rerender(
      <SovereignTabErrorBoundary
        tabId="workflow"
        tabLabel="Workflow"
        nowMs={() => now}
        onRuntimeEvent={(event) => events.push(event)}
        policy={{ failureThreshold: 1, cooldownMs: 10_000, halfOpenMaxAttempts: 1 }}
      >
        <ThrowingPanel />
      </SovereignTabErrorBoundary>,
    );

    expect(screen.getByTestId('sovereign-tab-error-boundary').getAttribute('data-circuit-phase')).toBe('open');
    expect(events.some((event) => event.phase === 'open')).toBe(true);
  });

  it('allows telemetry navigation from fallback', () => {
    const onOpenTelemetry = vi.fn();

    render(
      <SovereignTabErrorBoundary tabId="remote" tabLabel="Remote Memory" onOpenTelemetry={onOpenTelemetry}>
        <ThrowingPanel />
      </SovereignTabErrorBoundary>,
    );

    fireEvent.click(screen.getByText('Telemetry oeffnen'));
    expect(onOpenTelemetry).toHaveBeenCalledTimes(1);
  });
});
