import { describe, expect, it } from 'vitest';
import {
  buildSovereignRuntimeEvidenceLog,
  decideSovereignCompactShortcutExecution,
} from './sovereignCompactShortcutExecutionRuntime';
import { appendSovereignActionEvent, createSovereignActionStreamState } from './sovereignActionStreamRuntime';

function input(overrides: Partial<Parameters<typeof decideSovereignCompactShortcutExecution>[0]> = {}) {
  return {
    id: 'repo' as const,
    repoSnapshotReady: false,
    repoFileCount: 0,
    changedFiles: [],
    patchDiffAvailable: false,
    githubAccessState: 'missing' as const,
    executorAvailable: false,
    executorIntent: 'unknown' as const,
    runtimeEventCount: 0,
    ...overrides,
  };
}

describe('sovereignCompactShortcutExecutionRuntime', () => {
  it('opens real repo setup instead of an empty explorer when no snapshot exists', () => {
    const decision = decideSovereignCompactShortcutExecution(input({ id: 'repo' }));
    expect(decision).toMatchObject({ canExecute: true, surface: 'repo-setup' });
    expect(decision.event?.label).toBe('Repo-Setup geöffnet');
    expect(decision.event?.detail).not.toContain('Repo geladen');
  });

  it('routes Diff to stored patch evidence when changed files do not exist', () => {
    expect(decideSovereignCompactShortcutExecution(input({ id: 'diff', patchDiffAvailable: true }))).toMatchObject({
      canExecute: true,
      surface: 'patch-diff',
    });
  });

  it('blocks executor for questions, missing repo and missing GitHub access', () => {
    expect(decideSovereignCompactShortcutExecution(input({ id: 'executor', executorAvailable: true, executorIntent: 'question' })).canExecute).toBe(false);
    expect(decideSovereignCompactShortcutExecution(input({ id: 'executor', executorAvailable: true, executorIntent: 'code_execution' })).nextAction).toContain('Repo');
    expect(decideSovereignCompactShortcutExecution(input({ id: 'executor', repoSnapshotReady: true, executorAvailable: true, executorIntent: 'code_execution' }))).toMatchObject({ canExecute: false, surface: 'github-access' });
  });

  it('allows executor only with complete runtime evidence', () => {
    expect(decideSovereignCompactShortcutExecution(input({
      id: 'executor',
      repoSnapshotReady: true,
      repoFileCount: 2,
      githubAccessState: 'ready',
      executorAvailable: true,
      executorIntent: 'draft_pr',
    }))).toMatchObject({ canExecute: true, surface: 'executor-request' });
  });

  it('builds runtime logs only from Action Stream and agent runtime events', () => {
    let stream = appendSovereignActionEvent(createSovereignActionStreamState(), {
      kind: 'done', route: 'repo', label: 'Repo geprüft', state: 'done', createdAt: 10,
    });
    stream = appendSovereignActionEvent(stream, {
      kind: 'done', route: 'runtime-logs', label: 'Runtime-Evidence-Log geöffnet', state: 'done', createdAt: 15,
    });
    stream = appendSovereignActionEvent(stream, {
      kind: 'done', route: 'files', label: 'Datei-Explorer geöffnet', state: 'done', createdAt: 16,
    });
    const log = buildSovereignRuntimeEvidenceLog(stream.events, [
      { at: 20, level: 'info', stage: 'agent-request', message: 'Job angefragt · token=super-secret-value' },
    ]);
    expect(log).toHaveLength(2);
    expect(log.map((entry) => entry.source)).toEqual(['action-stream', 'agent-runtime']);
    expect(log[1]?.message).not.toContain('super-secret-value');
    expect(log[1]?.message).toContain('****');
  });
});
