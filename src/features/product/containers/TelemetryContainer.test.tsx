import React from 'react';
import { fireEvent, render, screen, waitFor, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TelemetryContainer } from './TelemetryContainer';
import { appendTelemetryEvent, createInitialTelemetryState, createTelemetryEvent } from '../runtime/sovereignTelemetry';

const TELEMETRY_TOGGLE = /NoCode Live Monitor.*Telemetry Log/i;

describe('TelemetryContainer', () => {
  it('renders empty telemetry and keeps it collapsed when no events exist', () => {
    const onExpandedChange = vi.fn();
    render(<TelemetryContainer state={createInitialTelemetryState()} expanded={false} onExpandedChange={onExpandedChange} />);

    expect(screen.getByTestId('telemetry-container')).toBeDefined();
    expect(screen.getByText(/Noch keine Live-Events/i)).toBeDefined();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: TELEMETRY_TOGGLE }));
    });
    expect(onExpandedChange).toHaveBeenCalledWith(false);
  });

  it('toggles telemetry when events exist', () => {
    const onExpandedChange = vi.fn();
    const telemetry = appendTelemetryEvent(
      createInitialTelemetryState(),
      createTelemetryEvent('ui', 'success', 'ui:ready', 'UI ready.', undefined, 1000),
    );

    const { rerender } = render(<TelemetryContainer state={telemetry} expanded={false} onExpandedChange={onExpandedChange} />);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: TELEMETRY_TOGGLE }));
    });
    expect(onExpandedChange).toHaveBeenCalledWith(true);

    rerender(<TelemetryContainer state={telemetry} expanded={true} onExpandedChange={onExpandedChange} />);
    expect(screen.getAllByText(/ui:ready/i).length).toBeGreaterThan(0);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: TELEMETRY_TOGGLE }));
    });
    expect(onExpandedChange).toHaveBeenLastCalledWith(false);
  });

  it('ingests dependency telemetry events into the visible panel state', async () => {
    render(<TelemetryContainer state={createInitialTelemetryState()} expanded={true} onExpandedChange={vi.fn()} />);

    await act(async () => {
      window.dispatchEvent(new CustomEvent('sovereign:dependency-telemetry-event', {
        detail: {
          stage: 'runtime',
          level: 'warning',
          label: 'dependency:workflow:degraded',
          message: 'Workflow dependency degraded.',
          details: { dependencySource: 'workflow', dependencyKey: 'github-workflow-watch' },
        },
      }));
    });

    await waitFor(() => expect(screen.getAllByText(/dependency:workflow:degraded/i).length).toBeGreaterThan(0));
    expect(screen.getByText(/Workflow: warning/i)).toBeDefined();
  });
});