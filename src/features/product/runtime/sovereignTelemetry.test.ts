import { describe, expect, it } from 'vitest';
import {
  appendTelemetryEvent,
  assertTelemetryEventValid,
  createInitialTelemetryState,
  createTelemetryEvent,
  formatTelemetryLine,
  summarizeTelemetry,
  validateTelemetryEvent,
  validateTelemetryState,
  type SovereignTelemetryEvent,
} from './sovereignTelemetry';

describe('sovereignTelemetry', () => {
  it('appends events and updates latest stage state', () => {
    const initial = createInitialTelemetryState();
    const event = createTelemetryEvent('repo', 'success', 'repo:loaded', 'Repo loaded', { files: 12 }, 1_000);
    const state = appendTelemetryEvent(initial, event);

    expect(state.events).toHaveLength(1);
    expect(state.latestByStage.repo?.label).toBe('repo:loaded');
    expect(formatTelemetryLine(event)).toContain('repo:loaded');
    expect(validateTelemetryState(state).valid).toBe(true);
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
      state = appendTelemetryEvent(state, createTelemetryEvent('ui', 'info', `event-${i}`, 'tick', undefined, i + 1), 3);
    }

    expect(state.events.map((event) => event.label)).toEqual(['event-2', 'event-3', 'event-4']);
    expect(validateTelemetryState(state).valid).toBe(true);
  });

  it('rejects malformed telemetry events', () => {
    const broken = {
      id: '',
      stage: 'repo',
      level: 'success',
      label: '',
      message: 'Repo loaded',
      timestamp: 1,
    } as SovereignTelemetryEvent;

    const report = validateTelemetryEvent(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('id is required');
    expect(() => assertTelemetryEventValid(broken)).toThrow('Telemetry event is invalid');
  });

  it('rejects secret-like telemetry content', () => {
    expect(() => createTelemetryEvent('github', 'error', 'github:failed', 'token=supersecret123456789', undefined, 1)).toThrow('secret-like');
    const report = validateTelemetryEvent({
      id: 'event',
      stage: 'github',
      level: 'error',
      label: 'github:failed',
      message: 'Failed safely',
      timestamp: 1,
      details: { error: 'Bearer abcdefghijklmnop' },
    });
    expect(report.valid).toBe(false);
  });

  it('warns when latestByStage does not match newest event for the stage', () => {
    const first = createTelemetryEvent('repo', 'info', 'repo:first', 'first', undefined, 1);
    const second = createTelemetryEvent('repo', 'success', 'repo:second', 'second', undefined, 2);
    const state = {
      events: [first, second],
      latestByStage: { repo: first },
    };

    const report = validateTelemetryState(state);
    expect(report.valid).toBe(true);
    expect(report.warnings.join(' ')).toContain('latestByStage mismatch');
  });
});
