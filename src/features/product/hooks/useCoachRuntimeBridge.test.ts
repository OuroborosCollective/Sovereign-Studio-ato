import { beforeEach, describe, expect, it } from 'vitest';
import { createSequentialRuntimeState } from '../runtime/sequentialRuntimeGuard';
import { buildSovereignHealthReport, clearLatestSovereignHealthReportForTests } from '../runtime/sovereignHealth';
import { appendTelemetryEvent, createInitialTelemetryState, createTelemetryEvent } from '../runtime/sovereignTelemetry';
import { deriveCoachStateFromRuntime } from './useCoachRuntimeBridge';

describe('useCoachRuntimeBridge runtime derivation', () => {
  beforeEach(() => {
    clearLatestSovereignHealthReportForTests();
  });

  it('prioritizes repo setup before health readiness', () => {
    const state = deriveCoachStateFromRuntime(
      createSequentialRuntimeState(),
      false,
      false,
      undefined,
      false,
      false,
      false,
      {
        allowed: false,
        status: 'red',
        reason: 'Health red prevents guarded output.',
      },
    );

    expect(state.source).toBe('repo');
    expect(state.title).toBe('Repository laden');
  });

  it('surfaces red runtime readiness as telemetry coach blocker', () => {
    const state = deriveCoachStateFromRuntime(
      createSequentialRuntimeState(),
      true,
      false,
      undefined,
      false,
      false,
      false,
      {
        allowed: false,
        status: 'red',
        reason: 'Health red prevents guarded output: dependency blocked.',
      },
    );

    expect(state).toMatchObject({
      lamp: 'red',
      title: 'Health Gate blockiert',
      message: 'Health red prevents guarded output: dependency blocked.',
      action: 'Telemetry und Health prüfen',
      source: 'telemetry',
      thinking: false,
    });
  });

  it('surfaces latest telemetry health report without an explicit gate argument', () => {
    const telemetry = appendTelemetryEvent(
      createInitialTelemetryState(),
      createTelemetryEvent('github', 'error', 'dependency:github:blocked', 'GitHub dependency unavailable.', undefined, 1_000),
    );

    buildSovereignHealthReport({
      repoFiles: [{ path: 'README.md', type: 'blob' }],
      telemetry,
    });

    const state = deriveCoachStateFromRuntime(
      createSequentialRuntimeState(),
      true,
      false,
      undefined,
      false,
      false,
      false,
    );

    expect(state).toMatchObject({
      lamp: 'red',
      title: 'Health Gate blockiert',
      source: 'telemetry',
    });
  });

  it('does not block coach when runtime readiness is allowed', () => {
    const state = deriveCoachStateFromRuntime(
      createSequentialRuntimeState(),
      true,
      false,
      undefined,
      false,
      false,
      false,
      {
        allowed: true,
        status: 'green',
        reason: 'Health green allows guarded output.',
      },
    );

    expect(state).toMatchObject({
      lamp: 'green',
      title: 'Bereit für Auftrag',
      source: 'runtime-library',
    });
  });
});
