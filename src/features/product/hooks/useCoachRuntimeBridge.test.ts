import { describe, expect, it } from 'vitest';
import { createSequentialRuntimeState } from '../runtime/sequentialRuntimeGuard';
import { deriveCoachStateFromRuntime } from './useCoachRuntimeBridge';

describe('useCoachRuntimeBridge runtime derivation', () => {
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
