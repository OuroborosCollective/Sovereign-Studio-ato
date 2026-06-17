import { describe, expect, it } from 'vitest';
import { createInitialTelemetryState, createTelemetryEvent, appendTelemetryEvent } from './sovereignTelemetry';
import { deriveTelemetryContainerState, nextTelemetryExpandedState } from './telemetryContainerRuntime';

describe('telemetryContainerRuntime', () => {
  it('summarizes empty telemetry state', () => {
    const state = deriveTelemetryContainerState({ state: createInitialTelemetryState(), expanded: false });

    expect(state.valid).toBe(true);
    expect(state.canExpand).toBe(false);
    expect(state.eventCount).toBe(0);
    expect(state.summary).toContain('No telemetry events');
  });

  it('allows expand when events exist', () => {
    const telemetry = appendTelemetryEvent(
      createInitialTelemetryState(),
      createTelemetryEvent('ui', 'success', 'ui:ready', 'UI ready.', undefined, 1000),
    );
    const state = deriveTelemetryContainerState({ state: telemetry, expanded: false });

    expect(state.valid).toBe(true);
    expect(state.canExpand).toBe(true);
    expect(state.eventCount).toBe(1);
    expect(state.summary).toContain('1 events');
  });

  it('keeps empty telemetry collapsed', () => {
    expect(nextTelemetryExpandedState(false, 0)).toBe(false);
    expect(nextTelemetryExpandedState(true, 0)).toBe(false);
  });

  it('toggles telemetry when events exist', () => {
    expect(nextTelemetryExpandedState(false, 1)).toBe(true);
    expect(nextTelemetryExpandedState(true, 1)).toBe(false);
  });
});
