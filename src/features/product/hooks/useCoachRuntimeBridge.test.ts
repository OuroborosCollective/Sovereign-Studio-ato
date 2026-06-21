import { beforeEach, describe, expect, it } from 'vitest';
import { createSequentialRuntimeState, startSequentialStep } from '../runtime/sequentialRuntimeGuard';
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

  describe('sequential runtime step states', () => {
    it('shows running state for repo-load step', () => {
      const runtime = startSequentialStep(
        createSequentialRuntimeState(),
        'repo-load',
        { repoReady: false },
      );

      const state = deriveCoachStateFromRuntime(
        runtime,
        false,
        false,
      );

      expect(state).toMatchObject({
        lamp: 'green',
        thinking: true,
        source: 'runtime-library',
      });
    });

    it('shows running state for package-build step', () => {
      const runtime = startSequentialStep(
        createSequentialRuntimeState(),
        'package-build',
        { repoReady: true },
      );

      const state = deriveCoachStateFromRuntime(
        runtime,
        true,
        false,
      );

      expect(state).toMatchObject({
        lamp: 'green',
        thinking: true,
        source: 'runtime-library',
      });
    });

    it('shows failed state when a step has failed', () => {
      const runtime = startSequentialStep(
        createSequentialRuntimeState(),
        'package-build',
        { repoReady: true },
      );

      // Simulate failure - need to include the 'step' field
      const failed = {
        ...runtime,
        steps: {
          ...runtime.steps,
          'package-build': { step: 'package-build' as const, status: 'failed' as const, message: 'Build error' },
        },
        activeStep: 'package-build' as const,
      };

      const state = deriveCoachStateFromRuntime(
        failed,
        true,
        false,
      );

      expect(state).toMatchObject({
        lamp: 'red',
        thinking: false,
        source: 'runtime-library',
      });
    });
  });

  describe('workflow states', () => {
    it('shows publishing state when isPublishing is true', () => {
      const state = deriveCoachStateFromRuntime(
        createSequentialRuntimeState(),
        true,
        false,
        undefined,
        true, // isPublishing
        false,
      );

      expect(state).toMatchObject({
        lamp: 'green',
        thinking: true,
        source: 'workflow',
      });
    });

    it('shows watching workflow state', () => {
      const state = deriveCoachStateFromRuntime(
        createSequentialRuntimeState(),
        true,
        false,
        undefined,
        false,
        true, // isWatchingWorkflow
      );

      expect(state).toMatchObject({
        lamp: 'green',
        thinking: true,
        source: 'workflow',
      });
    });

    it('shows red when workflow status is red', () => {
      const state = deriveCoachStateFromRuntime(
        createSequentialRuntimeState(),
        true,
        false,
        'red',
      );

      expect(state).toMatchObject({
        lamp: 'red',
        thinking: false,
        source: 'workflow',
        action: 'Repair prüfen',
      });
    });
  });

  describe('package states', () => {
    it('shows green when package is ready and workflow is green', () => {
      const state = deriveCoachStateFromRuntime(
        createSequentialRuntimeState(),
        true,
        true, // hasPackage
        'green',
      );

      expect(state).toMatchObject({
        lamp: 'green',
        thinking: false,
        source: 'runtime-library',
      });
    });

    it('shows ready for review when package is ready', () => {
      const state = deriveCoachStateFromRuntime(
        createSequentialRuntimeState(),
        true,
        true, // hasPackage
        'idle',
      );

      expect(state).toMatchObject({
        lamp: 'green',
        thinking: false,
        source: 'runtime-library',
        title: 'Package bereit',
      });
    });
  });

  describe('pattern memory states', () => {
    it('includes pattern memory status in state derivation', () => {
      const state = deriveCoachStateFromRuntime(
        createSequentialRuntimeState(),
        true,
        false,
        undefined,
        false,
        false,
        true, // hasActivePatterns
      );

      // State should be derived successfully even with active patterns
      expect(state.source).toBeTruthy();
    });
  });
});
