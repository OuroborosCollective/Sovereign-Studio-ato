import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createDurableRepoSnapshot, saveDurableRepoSnapshot } from '../repoSnapshotPersistence';
import { useGithubRepo } from './useGithubRepo';

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => body,
  } as Response;
}

describe('useGithubRepo', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    window.localStorage.clear();
  });

  it('loads a repo using explicit setup values before React state catches up', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ default_branch: 'main' }))
      .mockResolvedValueOnce(jsonResponse({ tree: [{ path: 'README.md', type: 'blob', size: 10 }] }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { result } = renderHook(() => useGithubRepo());

    await act(async () => {
      await result.current.loadRepoTree({ repoUrl: 'https://github.com/owner/repo' });
    });

    await waitFor(() => expect(result.current.repoFiles).toHaveLength(1));
    expect(result.current.repoUrl).toBe('https://github.com/owner/repo');
    expect(result.current.repoBranch).toBe('main');
    expect(result.current.repoStatus).toContain('1 echte Repo-Einträge geladen');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('restores durable repo snapshot on a new hook session', () => {
    saveDurableRepoSnapshot(window.localStorage, createDurableRepoSnapshot({
      repoUrl: 'https://github.com/owner/repo',
      repoBranch: 'main',
      repoStatus: '1 echte Repo-Einträge geladen (main)',
      repoFiles: [{ path: 'README.md', type: 'blob', size: 10 }],
      savedAt: 123,
    }));

    const { result } = renderHook(() => useGithubRepo());

    expect(result.current.repoUrl).toBe('https://github.com/owner/repo');
    expect(result.current.repoBranch).toBe('main');
    expect(result.current.repoFiles).toHaveLength(1);
    expect(result.current.repoStatus).toContain('durable restored');
  });
});
