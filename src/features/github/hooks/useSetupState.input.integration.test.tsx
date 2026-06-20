// @vitest-environment jsdom

import { useEffect } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { publishSetupStateToWindow, useSetupState, type SetupStateInput } from './useSetupState';
import { createSovereignDependencyLifecycleState } from '../../product/runtime/sovereignDependencyLifecycle';

function createInput(overrides: Partial<SetupStateInput> = {}): SetupStateInput {
  return {
    repoUrl: 'https://github.com/owner/repo',
    setRepoUrl: vi.fn(),
    repoBranch: 'main',
    setRepoBranch: vi.fn(),
    githubToken: 'token-for-test-only',
    setGithubToken: vi.fn(),
    repoFiles: [{ path: 'README.md', type: 'blob', size: 100 }],
    repoStatus: '1 echte Repo-Einträge geladen',
    isRepoBusy: false,
    githubDependencyLifecycle: createSovereignDependencyLifecycleState('github-repo-tree', 'github', 'ready'),
    loadRepoTree: vi.fn(async () => undefined),
    restoreRepoSnapshot: vi.fn(),
    clearRepoSnapshot: vi.fn(),
    ...overrides,
  };
}

function SetupPublisher({ input }: { input: SetupStateInput }): null {
  const setupState = useSetupState(input);

  useEffect(() => {
    publishSetupStateToWindow(setupState);
  }, [setupState]);

  return null;
}

describe('useSetupState existing input integration', () => {
  it('publishes existing repo and auth state to the window bridge', async () => {
    render(<SetupPublisher input={createInput()} />);

    await waitFor(() => {
      expect(window.__sovereignSetupState).toMatchObject({
        hasToken: true,
        tokenStatus: 'valid',
        repoReady: true,
        setupPhase: 'repo-loaded',
        isBusy: false,
      });
    });
  });

  it('keeps loading state aligned with existing input', async () => {
    render(<SetupPublisher input={createInput({
      repoFiles: [],
      repoStatus: 'Lade owner/repo...',
      isRepoBusy: true,
    })} />);

    await waitFor(() => {
      expect(window.__sovereignSetupState).toMatchObject({
        hasToken: true,
        tokenStatus: 'valid',
        repoReady: false,
        setupPhase: 'repo-loading',
        isBusy: true,
      });
    });
  });
});
