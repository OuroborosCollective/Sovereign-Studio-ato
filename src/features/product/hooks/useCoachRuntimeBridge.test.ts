import { beforeEach, describe, expect, it } from 'vitest';
import { createSequentialRuntimeState, startSequentialStep } from '../runtime/sequentialRuntimeGuard';
import { clearLatestSovereignHealthReportForTests } from '../runtime/sovereignHealth';
import { deriveCoachStateFromRuntime } from './useCoachRuntimeBridge';

describe('useCoachRuntimeBridge runtime derivation', () => {
  beforeEach(() => {
    clearLatestSovereignHealthReportForTests();
  });

  it('prioritizes repo setup before other states', () => {
    const state = deriveCoachStateFromRuntime(createSequentialRuntimeState(), false, false);
    expect(state.source).toBe('repo');
    expect(state.title).toBe('Repository laden');
  });

  it('shows running state for package-build step', () => {
    const runtime = startSequentialStep(createSequentialRuntimeState(), 'package-build', { repoReady: true });
    const state = deriveCoachStateFromRuntime(runtime, true, false);

    expect(state).toMatchObject({
      lamp: 'green',
      thinking: true,
      source: 'runtime-library',
      title: 'Package wird erstellt',
    });
  });

  it('routes pending workflow to workflow instead of stale package diff guidance', () => {
    const state = deriveCoachStateFromRuntime(
      createSequentialRuntimeState(),
      true,
      true,
      'pending',
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
      lamp: 'yellow',
      title: 'Workflow wartet',
      action: 'Workflow prüfen',
      source: 'workflow',
      thinking: false,
    });
    expect(state.message).not.toContain('Diff und Files prüfen');
  });

  it('shows green workflow complete when package is ready and workflow is green', () => {
    const state = deriveCoachStateFromRuntime(createSequentialRuntimeState(), true, true, 'green');

    expect(state).toMatchObject({
      lamp: 'green',
      thinking: false,
      source: 'workflow',
      title: 'Workflow grün',
      action: 'Fertig prüfen',
    });
  });

  it('shows package ready as workflow handoff when workflow has no active status', () => {
    const state = deriveCoachStateFromRuntime(createSequentialRuntimeState(), true, true, 'idle');

    expect(state).toMatchObject({
      lamp: 'green',
      thinking: false,
      source: 'workflow',
      title: 'Package bereit',
      action: 'Workflow prüfen',
    });
    expect(state.message).toContain('Diff-Ansicht ist nur noch intern');
    expect(state.message).not.toContain('Diff und Files prüfen');
  });
});
