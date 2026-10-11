import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { toolchainApi } from '../../toolchain/toolchainApi';
import { createDurableRepoSnapshot, saveDurableRepoSnapshot } from '../repoSnapshotPersistence';
import { useGithubRepo } from './useGithubRepo';

vi.mock('../../toolchain/toolchainApi', () => ({
  toolchainApi: {
    listBranches: vi.fn(),
    listDirectory: vi.fn(),
  },
}));

const listBranchesMock = vi.mocked(toolchainApi.listBranches);
const listDirectoryMock = vi.mocked(toolchainApi.listDirectory);

describe('useGithubRepo', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    listBranchesMock.mockResolvedValue({ branches: [{ name: 'main' }] });
    listDirectoryMock.mockResolvedValue({
      items: [{ name: 'README.md', path: 'README.md', type: 'file', size: 10 }],
    });
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('loads a repo using explicit setup values before React state catches up', async () => {
    const { result } = renderHook(() => useGithubRepo());

    await act(async () => {
      await result.current.loadRepoTree({ repoUrl: 'https://github.com/owner/repo' });
    });

    await waitFor(() => expect(result.current.repoFiles).toHaveLength(1));
    expect(result.current.repoUrl).toBe('https://github.com/owner/repo');
    expect(result.current.repoBranch).toBe('main');
    expect(result.current.repoStatus).toContain('1 echte Repo-Einträge über den Sovereign-Gateway geladen');
    expect(listBranchesMock).toHaveBeenCalledWith({ owner: 'owner', repo: 'repo' });
    expect(listDirectoryMock).toHaveBeenCalledWith({
      owner: 'owner',
      repo: 'repo',
      path: '',
      ref: 'main',
    });
  });

  it('publishes dependency telemetry through the shared publisher after repo load', async () => {
    const dependencyTelemetryListener = vi.fn();
    const dependencyStateListener = vi.fn();
    window.addEventListener('sovereign:dependency-telemetry-event', dependencyTelemetryListener);
    window.addEventListener('sovereign:dependency-lifecycle-state', dependencyStateListener);

    try {
      const { result } = renderHook(() => useGithubRepo());

      await act(async () => {
        await result.current.loadRepoTree({ repoUrl: 'https://github.com/owner/repo' });
      });

      await waitFor(() => expect(result.current.repoFiles).toHaveLength(1));
      expect(dependencyStateListener).toHaveBeenCalled();
      expect(dependencyTelemetryListener).toHaveBeenCalled();
      const telemetryEvents = dependencyTelemetryListener.mock.calls.map((call) => (call[0] as CustomEvent).detail);
      expect(telemetryEvents.some((event) => event.label === 'dependency:github:ready')).toBe(true);
    } finally {
      window.removeEventListener('sovereign:dependency-telemetry-event', dependencyTelemetryListener);
      window.removeEventListener('sovereign:dependency-lifecycle-state', dependencyStateListener);
    }
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

  it('restores repo snapshot via restoreRepoSnapshot with single pass loop optimization and filters safe files up to 500 limit', () => {
    const { result } = renderHook(() => useGithubRepo());

    const manyFiles = [];
    for (let i = 0; i < 600; i++) {
      if (i % 3 === 0) {
         manyFiles.push({ path: `file${i}.md`, type: 'blob', size: 10 });
      } else if (i % 3 === 1) {
         manyFiles.push({ path: `dir${i}`, type: 'tree' });
      } else {
         manyFiles.push({ path: `invalid${i}`, type: 'invalid' });
      }
    }

    act(() => {
      result.current.restoreRepoSnapshot({
        repoUrl: 'https://github.com/owner/many',
        repoBranch: 'dev',
        repoStatus: 'Many files loaded',
        repoFiles: manyFiles
      });
    });

    expect(result.current.repoUrl).toBe('https://github.com/owner/many');
    expect(result.current.repoBranch).toBe('dev');
    expect(result.current.repoStatus).toBe('Many files loaded [session restored]');
    expect(result.current.repoFiles).toHaveLength(400); // 600 * 2/3 = 400 safe files

    const tooManySafeFiles = [];
    for (let i = 0; i < 1000; i++) {
       tooManySafeFiles.push({ path: `safe${i}.md`, type: 'blob', size: 10 });
    }

    act(() => {
      result.current.restoreRepoSnapshot({
        repoUrl: 'https://github.com/owner/too-many',
        repoBranch: 'dev',
        repoStatus: 'Too many files loaded',
        repoFiles: tooManySafeFiles
      });
    });

    expect(result.current.repoFiles).toHaveLength(500); // truncated
  });
});
