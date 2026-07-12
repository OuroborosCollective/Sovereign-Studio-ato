import { describe, expect, it } from 'vitest';
import {
  createEmptySovereignToolShortcutContext,
  deriveSovereignToolShortcutGates,
  evaluateSovereignToolShortcutGate,
  SOVEREIGN_TOOL_SHORTCUTS,
  type SovereignToolShortcutContext,
  type SovereignToolShortcutId,
} from './sovereignToolShortcutRuntime';

function context(overrides: Partial<SovereignToolShortcutContext> = {}): SovereignToolShortcutContext {
  return { ...createEmptySovereignToolShortcutContext(), ...overrides };
}

function gate(id: SovereignToolShortcutId, overrides: Partial<SovereignToolShortcutContext> = {}) {
  const definition = SOVEREIGN_TOOL_SHORTCUTS.find((entry) => entry.id === id);
  if (!definition) throw new Error(`missing shortcut ${id}`);
  return evaluateSovereignToolShortcutGate(definition, context(overrides));
}

describe('sovereignToolShortcutRuntime', () => {
  it('defines exactly the ten compact launcher shortcuts', () => {
    expect(SOVEREIGN_TOOL_SHORTCUTS.map((entry) => entry.id)).toEqual([
      'repo', 'files', 'diff', 'github_access', 'executor',
      'runtime_logs', 'health', 'memory', 'coverage', 'settings',
    ]);
  });

  it('opens repo setup without claiming that a repo is loaded', () => {
    expect(gate('repo')).toMatchObject({ canOpen: true, state: 'setup_required', statusLabel: 'Repo laden' });
    expect(gate('repo', { repoReady: true })).toMatchObject({ canOpen: true, state: 'ready', statusLabel: 'Repo geladen' });
  });

  it('blocks Files until repo and file-list evidence both exist', () => {
    expect(gate('files')).toMatchObject({ canOpen: false, state: 'setup_required' });
    expect(gate('files', { repoReady: true })).toMatchObject({ canOpen: false, state: 'evidence_missing' });
    expect(gate('files', { repoReady: true, repoFileCount: 12 })).toMatchObject({ canOpen: true, state: 'ready', statusLabel: '12 Dateien' });
  });

  it('blocks Diff until patch or changed-file evidence exists', () => {
    expect(gate('diff')).toMatchObject({ canOpen: false, state: 'evidence_missing', statusLabel: 'Kein Diff' });
    expect(gate('diff', { hasDiffEvidence: true })).toMatchObject({ canOpen: true, state: 'ready', statusLabel: 'Diff vorhanden' });
  });

  it('keeps GitHub access setup open while preserving missing, invalid and validated state', () => {
    expect(gate('github_access')).toMatchObject({ canOpen: true, state: 'setup_required', statusLabel: 'Zugang fehlt' });
    expect(gate('github_access', { githubAccessState: 'validating' })).toMatchObject({ canOpen: true, state: 'setup_required', statusLabel: 'Prüfung läuft' });
    expect(gate('github_access', { githubAccessState: 'invalid' })).toMatchObject({ canOpen: true, state: 'evidence_missing', statusLabel: 'Zugang ungültig' });
    expect(gate('github_access', { githubAccessState: 'ready' })).toMatchObject({ canOpen: true, state: 'ready', statusLabel: 'Validiert' });
  });

  it('reports missing execution intent before asking for GitHub access', () => {
    expect(gate('executor', { repoReady: true, executorAvailable: true, hasExecutorMission: true, executorIntent: 'question' })).toMatchObject({
      canOpen: false,
      state: 'evidence_missing',
      statusLabel: 'Ausführungsauftrag fehlt',
    });
  });

  it('shows a running Executor job instead of exposing another start action', () => {
    expect(gate('executor', { repoReady: true, executorActive: true })).toMatchObject({
      canOpen: true,
      state: 'inspection',
      statusLabel: 'Job läuft',
    });
  });

  it('blocks Executor until repo, execution-intent, GitHub and runtime evidence exist', () => {
    expect(gate('executor')).toMatchObject({ canOpen: false, statusLabel: 'Repo fehlt' });
    expect(gate('executor', { repoReady: true })).toMatchObject({ canOpen: false, statusLabel: 'Ausführungsauftrag fehlt' });
    expect(gate('executor', { repoReady: true, hasExecutorMission: true, executorIntent: 'code_execution' })).toMatchObject({ canOpen: false, statusLabel: 'GitHub-Zugang fehlt' });
    expect(gate('executor', { repoReady: true, githubAccessState: 'ready', hasExecutorMission: true, executorIntent: 'code_execution' })).toMatchObject({ canOpen: false, statusLabel: 'Nicht verbunden' });
    expect(gate('executor', { repoReady: true, githubAccessState: 'ready', executorAvailable: true, hasExecutorMission: true, executorIntent: 'question' })).toMatchObject({ canOpen: false, statusLabel: 'Ausführungsauftrag fehlt' });
    expect(gate('executor', { repoReady: true, githubAccessState: 'ready', executorAvailable: true, hasExecutorMission: true, executorIntent: 'code_execution' })).toMatchObject({ canOpen: true, statusLabel: 'Start möglich' });
  });

  it('opens Runtime Logs without fabricating events', () => {
    expect(gate('runtime_logs')).toMatchObject({ canOpen: true, state: 'inspection', statusLabel: 'Noch leer' });
    expect(gate('runtime_logs', { runtimeLogCount: 3 })).toMatchObject({ canOpen: true, state: 'ready', statusLabel: '3 Events' });
  });

  it.each(['health', 'memory', 'coverage', 'settings'] as const)(
    'keeps %s as inspection instead of pre-claiming success',
    (id) => {
      const result = gate(id);
      expect(result.canOpen).toBe(true);
      expect(result.state).toBe('inspection');
      expect(result.statusLabel.toLowerCase()).not.toContain('bereit');
      expect(result.reason.length).toBeGreaterThan(10);
    },
  );

  it('assigns one explicit route to every shortcut', () => {
    expect(Object.fromEntries(SOVEREIGN_TOOL_SHORTCUTS.map((entry) => [entry.id, entry.route]))).toEqual({
      repo: 'repo',
      files: 'files',
      diff: 'diff',
      github_access: 'github-access',
      executor: 'agent-job',
      runtime_logs: 'runtime-logs',
      health: 'health',
      memory: 'memory',
      coverage: 'coverage',
      settings: 'settings',
    });
  });

  it('replaces inspection placeholders only after stored runtime evidence exists', () => {
    expect(gate('health')).toMatchObject({ state: 'inspection', statusLabel: 'Prüft beim Öffnen' });
    expect(gate('health', {
      inspectionEvidence: {
        health: {
          outcome: 'ready',
          statusLabel: 'Client-Checks bestanden',
          reason: 'Echte Client-Evidence vorhanden.',
          nextAction: 'CI separat prüfen.',
          observedAt: Date.now(),
        },
      },
    })).toMatchObject({ state: 'ready', statusLabel: 'Client-Checks bestanden' });
    expect(gate('coverage', {
      inspectionEvidence: {
        coverage: {
          outcome: 'failed',
          statusLabel: 'Coverage Map fehlt',
          reason: 'HTTP 404',
          nextAction: 'Coverage-Job prüfen.',
          observedAt: Date.now(),
        },
      },
    })).toMatchObject({ canOpen: true, state: 'evidence_missing', statusLabel: 'Coverage Map fehlt' });
  });

  it('returns one explicit gate for every shortcut', () => {
    const gates = deriveSovereignToolShortcutGates(context());
    expect(gates).toHaveLength(10);
    expect(new Set(gates.map((entry) => entry.id)).size).toBe(10);
    expect(gates.every((entry) => entry.reason && entry.nextAction)).toBe(true);
  });
});
