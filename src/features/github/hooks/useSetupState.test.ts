import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSetupState } from './useSetupState';
import * as useGithubRepoModule from './useGithubRepo';

vi.mock('./useGithubRepo');

const mockedUseGithubRepo = useGithubRepoModule.useGithubRepo as ReturnType<typeof vi.fn>;

describe('useSetupState', () => {
  const mockUseGithubRepoReturn = {
    repoUrl: '',
    setRepoUrl: vi.fn(),
    repoBranch: '',
    setRepoBranch: vi.fn(),
    githubToken: '',
    setGithubToken: vi.fn(),
    repoFiles: [],
    repoStatus: 'Noch kein echtes Repo geladen.',
    isRepoBusy: false,
    githubDependencyLifecycle: {
      phase: 'idle' as const,
    },
    loadRepoTree: vi.fn(),
    restoreRepoSnapshot: vi.fn(),
    clearRepoSnapshot: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseGithubRepo.mockReturnValue(mockUseGithubRepoReturn);
  });

  it('returns no-token state when token is empty', () => {
    mockedUseGithubRepo.mockReturnValue({
      ...mockUseGithubRepoReturn,
      githubToken: '',
    });

    const { result } = renderHook(() => useSetupState());
    
    expect(result.current.hasToken).toBe(false);
    expect(result.current.tokenStatus).toBe('none');
    expect(result.current.redactedToken).toBe('<no-token>');
  });

  it('returns valid token state when token is set', () => {
    mockedUseGithubRepo.mockReturnValue({
      ...mockUseGithubRepoReturn,
      githubToken: 'ghp_test1234567890abcdef',
    });

    const { result } = renderHook(() => useSetupState());
    
    expect(result.current.hasToken).toBe(true);
    expect(result.current.tokenStatus).toBe('valid');
    // redactGitHubToken returns first 4 + ... + last 4 chars
    expect(result.current.redactedToken).toBe('ghp_…cdef');
  });

  it('returns no-repo phase when no URL entered', () => {
    mockedUseGithubRepo.mockReturnValue({
      ...mockUseGithubRepoReturn,
      repoUrl: '',
      repoStatus: 'Noch kein echtes Repo geladen.',
    });

    const { result } = renderHook(() => useSetupState());
    
    expect(result.current.setupPhase).toBe('no-repo');
  });

  it('returns repo-loading phase when busy', () => {
    mockedUseGithubRepo.mockReturnValue({
      ...mockUseGithubRepoReturn,
      repoUrl: 'https://github.com/owner/repo',
      isRepoBusy: true,
    });

    const { result } = renderHook(() => useSetupState());
    
    expect(result.current.setupPhase).toBe('repo-loading');
  });

  it('returns repo-loaded phase when files exist', () => {
    mockedUseGithubRepo.mockReturnValue({
      ...mockUseGithubRepoReturn,
      repoUrl: 'https://github.com/owner/repo',
      repoFiles: [{ path: 'README.md', type: 'blob', size: 100 }],
      repoStatus: '100 echte Repo-Einträge geladen',
    });

    const { result } = renderHook(() => useSetupState());
    
    expect(result.current.setupPhase).toBe('repo-loaded');
    expect(result.current.repoSnapshotStatus.ready).toBe(true);
  });

  it('returns repo-error phase on error status', () => {
    mockedUseGithubRepo.mockReturnValue({
      ...mockUseGithubRepoReturn,
      repoUrl: 'https://github.com/owner/repo',
      repoStatus: 'Repository nicht gefunden oder für diesen Token nicht sichtbar.',
    });

    const { result } = renderHook(() => useSetupState());
    
    expect(result.current.setupPhase).toBe('repo-error');
  });

  it('reports healthy dependency when phase is idle', () => {
    mockedUseGithubRepo.mockReturnValue({
      ...mockUseGithubRepoReturn,
      githubDependencyLifecycle: { phase: 'idle' as const },
    });

    const { result } = renderHook(() => useSetupState());
    
    expect(result.current.dependencyHealthy).toBe(true);
  });

  it('reports unhealthy dependency when circuit is open', () => {
    mockedUseGithubRepo.mockReturnValue({
      ...mockUseGithubRepoReturn,
      githubDependencyLifecycle: { phase: 'open' as const },
    });

    const { result } = renderHook(() => useSetupState());
    
    expect(result.current.dependencyHealthy).toBe(false);
  });
});
