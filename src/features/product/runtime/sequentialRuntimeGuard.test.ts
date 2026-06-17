import { describe, expect, it } from 'vitest';
import {
  assertSequentialRuntimeStateValid,
  canStartSequentialStep,
  createSequentialRuntimeState,
  finishSequentialStep,
  startSequentialStep,
  summarizeSequentialRuntime,
  validateSequentialRuntimeState,
  type SequentialRuntimeState,
} from './sequentialRuntimeGuard';

describe('sequentialRuntimeGuard', () => {
  it('allows only one active step at a time', () => {
    const state = startSequentialStep(createSequentialRuntimeState(), 'repo-load', {}, 1);
    expect(state.activeStep).toBe('repo-load');
    expect(canStartSequentialStep(state, 'package-build', { repoReady: true }).allowed).toBe(false);
    expect(() => startSequentialStep(state, 'package-build', { repoReady: true }, 2)).toThrow('still running');
  });

  it('requires a repo snapshot before downstream steps', () => {
    const state = createSequentialRuntimeState();
    expect(canStartSequentialStep(state, 'package-build', { repoReady: false }).reason).toContain('repository snapshot');
    expect(canStartSequentialStep(state, 'package-build', { repoReady: true }).allowed).toBe(true);
  });

  it('requires package, commit and workflow report for dependent steps', () => {
    const state = createSequentialRuntimeState();
    expect(canStartSequentialStep(state, 'diff-load', { repoReady: true, hasPackage: false }).reason).toContain('generated package');
    expect(canStartSequentialStep(state, 'draft-pr-publish', { repoReady: true, hasPackage: false }).reason).toContain('generated package');
    expect(canStartSequentialStep(state, 'workflow-watch', { repoReady: true, hasDraftCommit: false }).reason).toContain('commit SHA');
    expect(canStartSequentialStep(state, 'repair-plan', { repoReady: true, hasWorkflowReport: false }).reason).toContain('Workflow Watch');
  });

  it('finishes steps and records history', () => {
    const running = startSequentialStep(createSequentialRuntimeState(), 'repo-load', {}, 1);
    const finished = finishSequentialStep(running, 'repo-load', 'completed', 'loaded', 2);
    expect(finished.activeStep).toBeNull();
    expect(finished.steps['repo-load'].status).toBe('completed');
    expect(finished.history).toHaveLength(2);
    expect(validateSequentialRuntimeState(finished).valid).toBe(true);
    expect(summarizeSequentialRuntime(finished)).toContain('1 completed');
  });

  it('rejects finishing a non-active step', () => {
    const state = startSequentialStep(createSequentialRuntimeState(), 'repo-load', {}, 1);
    expect(() => finishSequentialStep(state, 'package-build', 'completed', 'done', 2)).toThrow('Cannot finish');
  });

  it('self-validates impossible double-running states', () => {
    const state = createSequentialRuntimeState();
    const broken: SequentialRuntimeState = {
      ...state,
      activeStep: 'repo-load',
      steps: {
        ...state.steps,
        'repo-load': { ...state.steps['repo-load'], status: 'running', startedAt: 1 },
        'package-build': { ...state.steps['package-build'], status: 'running', startedAt: 1 },
      },
    };

    const report = validateSequentialRuntimeState(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('More than one runtime step is running');
    expect(() => assertSequentialRuntimeStateValid(broken)).toThrow('Sequential runtime state is invalid');
  });

  it('self-validates active step mismatch', () => {
    const state = createSequentialRuntimeState();
    const broken: SequentialRuntimeState = {
      ...state,
      activeStep: 'workflow-watch',
      steps: {
        ...state.steps,
        'workflow-watch': { ...state.steps['workflow-watch'], status: 'completed', finishedAt: 1 },
      },
    };

    const report = validateSequentialRuntimeState(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('not marked as running');
  });

  it('self-validates history sequence order', () => {
    const state = createSequentialRuntimeState();
    const broken: SequentialRuntimeState = {
      ...state,
      sequence: 1,
      history: [
        { sequence: 2, step: 'repo-load', status: 'running', message: 'start', at: 1 },
        { sequence: 1, step: 'repo-load', status: 'completed', message: 'done', at: 2 },
      ],
    };

    const report = validateSequentialRuntimeState(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('strictly increasing');
  });
});
