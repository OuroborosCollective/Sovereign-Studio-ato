import { describe, expect, it } from 'vitest';
import {
  appendTelemetryEvent,
  createInitialTelemetryState,
  createTelemetryEvent,
  formatTelemetryLine,
  summarizeTelemetry,
} from './sovereignTelemetry';

describe('sovereignTelemetry', () => {
  it('appends events and updates latest stage state', () => {
    const initial = createInitialTelemetryState();
    const event = createTelemetryEvent('repo', 'success', 'repo:loaded', 'Repo loaded', { files: 12 }, 1_000);
    const state = appendTelemetryEvent(initial, event);

    expect(state.events).toHaveLength(1);
    expect(state.latestByStage.repo?.label).toBe('repo:loaded');
    expect(formatTelemetryLine(event)).toContain('repo:loaded');
  });

  it('summarizes warnings and errors', () => {
    let state = createInitialTelemetryState();
    state = appendTelemetryEvent(state, createTelemetryEvent('repo', 'warning', 'repo:empty', 'No repo', undefined, 1));
    state = appendTelemetryEvent(state, createTelemetryEvent('github', 'error', 'github:failed', 'Failed', undefined, 2));

    expect(summarizeTelemetry(state)).toContain('1 warning');
    expect(summarizeTelemetry(state)).toContain('1 error');
  });

  it('keeps the newest event window', () => {
    let state = createInitialTelemetryState();
    for (let i = 0; i < 5; i += 1) {
      state = appendTelemetryEvent(state, createTelemetryEvent('ui', 'info', `event-${i}`, 'tick', undefined, i), 3);
    }

    expect(state.events.map((event) => event.label)).toEqual(['event-2', 'event-3', 'event-4']);
  });
});
