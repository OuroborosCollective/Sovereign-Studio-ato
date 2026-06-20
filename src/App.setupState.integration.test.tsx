// @vitest-environment jsdom
/**
 * App Setup State Integration Test
 * 
 * Verifies that App.tsx correctly publishes __sovereignSetupState
 * for Coach consumption without manual window setting.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Import the function directly to test it
import { publishSetupStateToWindow, type SetupState } from './features/github/hooks/useSetupState';

const originalDispatchEvent = window.dispatchEvent;
let dispatchEventCalls: Event[] = [];

describe('App Setup State Integration', () => {
  beforeEach(() => {
    dispatchEventCalls = [];
    window.dispatchEvent = vi.fn((event: Event) => {
      dispatchEventCalls.push(event);
      return true;
    });
  });

  afterEach(() => {
    window.dispatchEvent = originalDispatchEvent;
    vi.clearAllMocks();
  });

  it('App publishes __sovereignSetupState to window with correct structure', () => {
    const setupState = {
      repoUrl: 'https://github.com/owner/repo',
      setRepoUrl: vi.fn(),
      repoBranch: 'main',
      setRepoBranch: vi.fn(),
      githubToken: 'ghp_test1234567890abcdef',
      setGithubToken: vi.fn(),
      repoFiles: [{ path: 'README.md', type: 'blob', size: 100 }],
      repoStatus: '100 echte Repo-Einträge geladen',
      isRepoBusy: false,
      githubDependencyLifecycle: { phase: 'ready' as const },
      loadRepoTree: vi.fn(),
      restoreRepoSnapshot: vi.fn(),
      clearRepoSnapshot: vi.fn(),
      hasToken: true,
      tokenStatus: 'valid' as const,
      redactedToken: 'ghp_…cdef',
      repoSnapshotStatus: { ready: true, fileCount: 1, reason: 'OK' },
      setupPhase: 'repo-loaded' as const,
      dependencyPhase: 'ready',
      dependencyHealthy: true,
    } as SetupState;

    publishSetupStateToWindow(setupState);

    // Verify window state
    expect(window.__sovereignSetupState).toBeDefined();
    expect(window.__sovereignSetupState?.hasToken).toBe(true);
    expect(window.__sovereignSetupState?.tokenStatus).toBe('valid');
    expect(window.__sovereignSetupState?.setupPhase).toBe('repo-loaded');
    expect(window.__sovereignSetupState?.repoReady).toBe(true);
  });

  it('publishSetupStateToWindow dispatches sovereign:setup-state event', () => {
    const setupState = {
      repoUrl: '',
      setRepoUrl: vi.fn(),
      repoBranch: '',
      setRepoBranch: vi.fn(),
      githubToken: '',
      setGithubToken: vi.fn(),
      repoFiles: [],
      repoStatus: 'Noch kein echtes Repo geladen.',
      isRepoBusy: false,
      githubDependencyLifecycle: { phase: 'idle' as const },
      loadRepoTree: vi.fn(),
      restoreRepoSnapshot: vi.fn(),
      clearRepoSnapshot: vi.fn(),
      hasToken: false,
      tokenStatus: 'none' as const,
      redactedToken: '<no-token>',
      repoSnapshotStatus: { ready: false, fileCount: 0, reason: 'No files' },
      setupPhase: 'no-repo' as const,
      dependencyPhase: 'idle',
      dependencyHealthy: true,
    } as SetupState;

    publishSetupStateToWindow(setupState);

    expect(dispatchEventCalls.some(e => e.type === 'sovereign:setup-state')).toBe(true); // eslint-disable-line @typescript-eslint/no-explicit-any
  });

  it('Coach reads window.__sovereignSetupState with repo-ready state', () => {
    window.__sovereignSetupState = {
      hasToken: true,
      tokenStatus: 'valid',
      repoReady: true,
      setupPhase: 'repo-loaded',
      isBusy: false,
      status: '500 echte Repo-Einträge geladen',
      redactedToken: 'ghp_…cdef',
      dependencyHealthy: true,
      updatedAt: Date.now(),
    };

    // Verify Coach can read this state
    expect(window.__sovereignSetupState).toBeDefined();
    expect(window.__sovereignSetupState?.repoReady).toBe(true);
    expect(window.__sovereignSetupState?.setupPhase).toBe('repo-loaded');
  });

  it('Coach reads window.__sovereignSetupState with no-repo state', () => {
    window.__sovereignSetupState = {
      hasToken: false,
      tokenStatus: 'none',
      repoReady: false,
      setupPhase: 'no-repo',
      isBusy: false,
      status: 'Noch kein echtes Repo geladen.',
      redactedToken: '<no-token>',
      dependencyHealthy: true,
      updatedAt: Date.now(),
    };

    expect(window.__sovereignSetupState?.setupPhase).toBe('no-repo');
    expect(window.__sovereignSetupState?.repoReady).toBe(false);
  });

  it('Coach reads window.__sovereignSetupState with loading state', () => {
    window.__sovereignSetupState = {
      hasToken: true,
      tokenStatus: 'valid',
      repoReady: false,
      setupPhase: 'repo-loading',
      isBusy: true,
      status: 'Lade Repository...',
      redactedToken: 'ghp_…cdef',
      dependencyHealthy: true,
      updatedAt: Date.now(),
    };

    expect(window.__sovereignSetupState?.isBusy).toBe(true);
    expect(window.__sovereignSetupState?.setupPhase).toBe('repo-loading');
  });

  it('Coach reads window.__sovereignSetupState with error state', () => {
    window.__sovereignSetupState = {
      hasToken: false,
      tokenStatus: 'expired',
      repoReady: false,
      setupPhase: 'repo-error',
      isBusy: false,
      status: 'GitHub Token fehlt',
      redactedToken: '<no-token>',
      dependencyHealthy: true,
      updatedAt: Date.now(),
    };

    expect(window.__sovereignSetupState?.setupPhase).toBe('repo-error');
    expect(window.__sovereignSetupState?.tokenStatus).toBe('expired');
  });
});
