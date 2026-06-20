// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { publishSetupStateToWindow, type SetupState } from './features/github/hooks/useSetupState';
import type { RepoFile } from './features/github/types';
import {
  createSovereignDependencyLifecycleState,
  type SovereignDependencyLifecycleState,
} from './features/product/runtime/sovereignDependencyLifecycle';

function createLifecycle(summary = 'GitHub setup state test.'): SovereignDependencyLifecycleState {
  return createSovereignDependencyLifecycleState('github-repo-tree', 'github', summary);
}

function createSetupState(overrides: Partial<SetupState> = {}): SetupState {
  const repoFiles: RepoFile[] = [{ path: 'README.md', type: 'blob', size: 100 }];

  return {
    repoUrl: 'https://github.com/owner/repo',
    setRepoUrl: vi.fn(),
    repoBranch: 'main',
    setRepoBranch: vi.fn(),
    githubToken: 'token-for-test-only',
    setGithubToken: vi.fn(),
    hasToken: true,
    tokenStatus: 'valid',
    redactedToken: 'toke…only',
    repoFiles,
    repoStatus: '1 echte Repo-Einträge geladen',
    isRepoBusy: false,
    repoSnapshotStatus: {
      ready: true,
      fileCount: 1,
      reason: '1 repository entries loaded.',
    },
    setupPhase: 'repo-loaded',
    loadRepoTree: vi.fn(async () => undefined),
    restoreRepoSnapshot: vi.fn(),
    clearRepoSnapshot: vi.fn(),
    githubDependencyLifecycle: createLifecycle(),
    dependencyPhase: 'ready',
    dependencyHealthy: true,
    ...overrides,
  };
}

describe('App Setup State Integration', () => {
  afterEach(() => {
    delete window.__sovereignSetupState;
    vi.restoreAllMocks();
  });

  it('publishes __sovereignSetupState to window with repo-loaded structure', () => {
    publishSetupStateToWindow(createSetupState());

    expect(window.__sovereignSetupState).toMatchObject({
      hasToken: true,
      tokenStatus: 'valid',
      repoReady: true,
      setupPhase: 'repo-loaded',
      isBusy: false,
      status: '1 echte Repo-Einträge geladen',
      redactedToken: 'toke…only',
      dependencyHealthy: true,
    });
    expect(typeof window.__sovereignSetupState?.updatedAt).toBe('number');
  });

  it('dispatches sovereign:setup-state event', () => {
    const listener = vi.fn();
    window.addEventListener('sovereign:setup-state', listener);

    publishSetupStateToWindow(createSetupState({
      repoUrl: '',
      githubToken: '',
      hasToken: false,
      tokenStatus: 'none',
      redactedToken: '<no-token>',
      repoFiles: [],
      repoStatus: 'Noch kein echtes Repo geladen.',
      repoSnapshotStatus: {
        ready: false,
        fileCount: 0,
        reason: 'Load a real repository tree before generating Sovereign packages.',
      },
      setupPhase: 'no-repo',
      dependencyPhase: 'idle',
      dependencyHealthy: true,
      githubDependencyLifecycle: createLifecycle('GitHub repository tree has not been checked yet.'),
    }));

    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toMatchObject({
      hasToken: false,
      tokenStatus: 'none',
      repoReady: false,
      setupPhase: 'no-repo',
      dependencyHealthy: true,
    });

    window.removeEventListener('sovereign:setup-state', listener);
  });

  it('publishes repo-ready state for coach consumption', () => {
    publishSetupStateToWindow(createSetupState({
      repoFiles: [{ path: 'src/App.tsx', type: 'blob', size: 500 }],
      repoStatus: '500 echte Repo-Einträge geladen',
      repoSnapshotStatus: {
        ready: true,
        fileCount: 1,
        reason: '1 repository entries loaded.',
      },
      setupPhase: 'repo-loaded',
    }));

    expect(window.__sovereignSetupState?.repoReady).toBe(true);
    expect(window.__sovereignSetupState?.setupPhase).toBe('repo-loaded');
    expect(window.__sovereignSetupState?.status).toBe('500 echte Repo-Einträge geladen');
  });

  it('publishes no-repo state for coach consumption', () => {
    publishSetupStateToWindow(createSetupState({
      repoUrl: '',
      githubToken: '',
      hasToken: false,
      tokenStatus: 'none',
      redactedToken: '<no-token>',
      repoFiles: [],
      repoStatus: 'Noch kein echtes Repo geladen.',
      repoSnapshotStatus: {
        ready: false,
        fileCount: 0,
        reason: 'Load a real repository tree before generating Sovereign packages.',
      },
      setupPhase: 'no-repo',
      dependencyPhase: 'idle',
      dependencyHealthy: true,
      githubDependencyLifecycle: createLifecycle('GitHub repository tree has not been checked yet.'),
    }));

    expect(window.__sovereignSetupState?.setupPhase).toBe('no-repo');
    expect(window.__sovereignSetupState?.repoReady).toBe(false);
    expect(window.__sovereignSetupState?.hasToken).toBe(false);
  });

  it('publishes loading state for coach consumption', () => {
    publishSetupStateToWindow(createSetupState({
      repoFiles: [],
      repoStatus: 'Lade Repository...',
      isRepoBusy: true,
      repoSnapshotStatus: {
        ready: false,
        fileCount: 0,
        reason: 'Repository load in progress.',
      },
      setupPhase: 'repo-loading',
    }));

    expect(window.__sovereignSetupState?.isBusy).toBe(true);
    expect(window.__sovereignSetupState?.setupPhase).toBe('repo-loading');
    expect(window.__sovereignSetupState?.repoReady).toBe(false);
  });

  it('publishes error state for coach consumption', () => {
    publishSetupStateToWindow(createSetupState({
      githubToken: '',
      hasToken: false,
      tokenStatus: 'expired',
      redactedToken: '<no-token>',
      repoFiles: [],
      repoStatus: 'GitHub Zugang fehlt',
      repoSnapshotStatus: {
        ready: false,
        fileCount: 0,
        reason: 'Repository could not be loaded.',
      },
      setupPhase: 'repo-error',
      dependencyPhase: 'open',
      dependencyHealthy: false,
      githubDependencyLifecycle: createLifecycle('GitHub dependency is unavailable.'),
    }));

    expect(window.__sovereignSetupState?.setupPhase).toBe('repo-error');
    expect(window.__sovereignSetupState?.tokenStatus).toBe('expired');
    expect(window.__sovereignSetupState?.dependencyHealthy).toBe(false);
  });
});
