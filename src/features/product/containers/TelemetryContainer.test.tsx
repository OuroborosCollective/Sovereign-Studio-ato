import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TelemetryContainer } from './TelemetryContainer';
import { appendTelemetryEvent, createInitialTelemetryState, createTelemetryEvent } from '../runtime/sovereignTelemetry';

describe('TelemetryContainer', () => {
  it('renders empty telemetry and keeps it collapsed', () => {
    const onExpandedChange = vi.fn();
    render(<TelemetryContainer state={createInitialTelemetryState()} expanded={false} onExpandedChange={onExpandedChange} />);

    expect(screen.getByTestId('telemetry-container')).toBeDefined();
    expect(screen.getByText(/No telemetry events yet/i)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /Sovereign Telemetry Terminal/i }));
    expect(onExpandedChange).toHaveBeenCalledWith(false);
  });

  it('toggles telemetry when events exist', () => {
    const onExpandedChange = vi.fn();
    const telemetry = appendTelemetryEvent(
      createInitialTelemetryState(),
      createTelemetryEvent('ui', 'success', 'ui:ready', 'UI ready.', undefined, 1000),
    );

    const { rerender } = render(<TelemetryContainer state={telemetry} expanded={false} onExpandedChange={onExpandedChange} />);
    fireEvent.click(screen.getByRole('button', { name: /Sovereign Telemetry Terminal/i }));
    expect(onExpandedChange).toHaveBeenCalledWith(true);

    rerender(<TelemetryContainer state={telemetry} expanded={true} onExpandedChange={onExpandedChange} />);
    expect(screen.getAllByText(/ui:ready/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Sovereign Telemetry Terminal/i }));
    expect(onExpandedChange).toHaveBeenLastCalledWith(false);
  });
});
