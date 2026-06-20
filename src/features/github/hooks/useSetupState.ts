/**
 * Unified Setup State Hook
 * 
 * Central source for all Repo/PAT setup detection.
 * Used by: Gear, Direct UI, Coach, GitHub-Hook, Automation Mode.
 * 
 * Provides derived state including:
 * - hasToken: boolean (normalized from raw token)
 * - repoReady: boolean (from file count)
 * - setupPhase: enum (no-repo | repo-loading | repo-loaded | repo-error)
 * - tokenStatus: enum (none | missing | valid | expired)
 * - redactedToken: string (for display)
 */

import { useMemo } from 'react';
import { useGithubRepo } from './useGithubRepo';
import { hasGitHubToken, createGitHubAuthSession } from '../githubAuthSession';
import { getRepoSnapshotStatus } from '../../product/runtime/sovereignFunctionalGuards';
import type { RepoSnapshotStatus } from '../../product/runtime/sovereignFunctionalGuards';
import type { RepoFile } from '../types';

export type SetupPhase = 
  | 'no-repo'           // No repo URL entered
  | 'repo-loading'      // Currently loading repo
  | 'repo-loaded'       // Repo successfully loaded
  | 'repo-error';       // Error loading repo

export type TokenStatus =
  | 'none'              // No token entered
  | 'missing'           // Token entered but invalid/empty
  | 'valid'             // Token is present and non-empty
  | 'expired';          // Token expired or rejected (403/401)

export interface SetupState {
  // Core inputs
  repoUrl: string;
  setRepoUrl: (url: string) => void;
  repoBranch: string;
  setRepoBranch: (branch: string) => void;
  githubToken: string;
  setGithubToken: (token: string) => void;
  
  // Derived state
  hasToken: boolean;
  tokenStatus: TokenStatus;
  redactedToken: string;
  
  // Repo state
  repoFiles: RepoFile[];
  repoStatus: string;
  isRepoBusy: boolean;
  repoSnapshotStatus: RepoSnapshotStatus;
  setupPhase: SetupPhase;
  
  // Actions
  loadRepoTree: (options?: { repoUrl?: string; repoBranch?: string; githubToken?: string }) => Promise<void>;
  restoreRepoSnapshot: (snapshot: { repoUrl: string; repoBranch: string; repoStatus: string; repoFiles: RepoFile[] }) => void;
  clearRepoSnapshot: () => void;
  
  // Dependency lifecycle (for circuit breaker visibility)
  dependencyPhase: string;
  dependencyHealthy: boolean;
}

export function useSetupState(): SetupState {
  const {
    repoUrl,
    setRepoUrl,
    repoBranch,
    setRepoBranch,
    githubToken,
    setGithubToken,
    repoFiles,
    repoStatus,
    isRepoBusy,
    githubDependencyLifecycle,
    loadRepoTree,
    restoreRepoSnapshot,
    clearRepoSnapshot,
  } = useGithubRepo();

  // Derive token status
  const hasToken = useMemo(() => hasGitHubToken(githubToken), [githubToken]);
  
  const tokenStatus = useMemo<TokenStatus>(() => {
    if (!githubToken.trim()) return 'none';
    if (!hasToken) return 'missing';
    // Note: expired/valid distinction happens at load time
    return 'valid';
  }, [githubToken, hasToken]);
  
  const redactedToken = useMemo(() => {
    const session = createGitHubAuthSession(githubToken);
    return session.redactedToken;
  }, [githubToken]);
  
  // Derive repo snapshot status
  const repoSnapshotStatus = useMemo(() => {
    return getRepoSnapshotStatus(repoFiles);
  }, [repoFiles]);
  
  // Derive setup phase
  const setupPhase = useMemo<SetupPhase>(() => {
    if (isRepoBusy) return 'repo-loading';
    if (repoSnapshotStatus.ready) return 'repo-loaded';
    if (repoStatus.includes('fehlt') || repoStatus.includes('Noch kein') || !repoUrl.trim()) {
      return 'no-repo';
    }
    return 'repo-error';
  }, [isRepoBusy, repoSnapshotStatus.ready, repoStatus, repoUrl]);
  
  // Dependency lifecycle info
  const dependencyPhase = useMemo(() => {
    return githubDependencyLifecycle.phase;
  }, [githubDependencyLifecycle.phase]);
  
  const dependencyHealthy = useMemo(() => {
    return githubDependencyLifecycle.phase === 'ready' || githubDependencyLifecycle.phase === 'idle';
  }, [githubDependencyLifecycle.phase]);

  return {
    // Core inputs
    repoUrl,
    setRepoUrl,
    repoBranch,
    setRepoBranch,
    githubToken,
    setGithubToken,
    
    // Derived state
    hasToken,
    tokenStatus,
    redactedToken,
    
    // Repo state
    repoFiles,
    repoStatus,
    isRepoBusy,
    repoSnapshotStatus,
    setupPhase,
    
    // Actions
    loadRepoTree,
    restoreRepoSnapshot,
    clearRepoSnapshot,
    
    // Dependency lifecycle
    dependencyPhase,
    dependencyHealthy,
  };
}

/**
 * Publish Setup State to window for non-React consumers (Coach, etc.)
 * Call this in useEffect to keep window.__sovereignSetupState in sync.
 */
export function publishSetupStateToWindow(state: SetupState): void {
  if (typeof window === 'undefined') return;
  
  window.__sovereignSetupState = {
    hasToken: state.hasToken,
    tokenStatus: state.tokenStatus,
    repoReady: state.repoSnapshotStatus.ready,
    setupPhase: state.setupPhase,
    isBusy: state.isRepoBusy,
    status: state.repoStatus,
    redactedToken: state.redactedToken,
    dependencyHealthy: state.dependencyHealthy,
    updatedAt: Date.now(),
  };
  
  // Dispatch event so Coach can react immediately
  window.dispatchEvent(new CustomEvent('sovereign:setup-state', {
    detail: window.__sovereignSetupState,
  }));
}

// Type for window extension
declare global {
  interface Window {
    __sovereignSetupState?: {
      hasToken: boolean;
      tokenStatus: TokenStatus;
      repoReady: boolean;
      setupPhase: SetupPhase;
      isBusy: boolean;
      status: string;
      redactedToken: string;
      dependencyHealthy: boolean;
      updatedAt: number;
    };
  }
}
