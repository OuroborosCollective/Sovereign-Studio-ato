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

  it('publishes dependency telemetry through the shared publisher after repo load', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ default_branch: 'main' }))
      .mockResolvedValueOnce(jsonResponse({ tree: [{ path: 'README.md', type: 'blob', size: 10 }] }));
    const dependencyTelemetryListener = vi.fn();
    const dependencyStateListener = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    window.addEventListener('sovereign:dependency-telemetry-event', dependencyTelemetryListener);
    window.addEventListener('sovereign:dependency-lifecycle-state', dependencyStateListener);

    const { result } = renderHook(() => useGithubRepo());

    await act(async () => {
      await result.current.loadRepoTree({ repoUrl: 'https://github.com/owner/repo' });
    });

    await waitFor(() => expect(result.current.repoFiles).toHaveLength(1));
    expect(dependencyStateListener).toHaveBeenCalled();
    expect(dependencyTelemetryListener).toHaveBeenCalled();
    const telemetryEvents = dependencyTelemetryListener.mock.calls.map((call) => (call[0] as CustomEvent).detail);
    expect(telemetryEvents.some((event) => event.label === 'dependency:github:ready')).toBe(true);

    window.removeEventListener('sovereign:dependency-telemetry-event', dependencyTelemetryListener);
    window.removeEventListener('sovereign:dependency-lifecycle-state', dependencyStateListener);
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
