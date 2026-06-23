/**
 * Unified Setup State Hook
 * 
 * Central source for all Repo/PAT setup detection.
 * Used by: Gear, Direct UI, Coach, GitHub-Hook, Automation Mode.
 */

import { useMemo, useState } from 'react';
import { useGithubRepo } from './useGithubRepo';
import { hasGitHubToken, createGitHubAuthSession } from '../githubAuthSession';
import { getRepoSnapshotStatus } from '../../product/runtime/sovereignFunctionalGuards';
import { defaultSettings } from '../../product/constants';
import type { ProjectSettings } from '../../product/types';
import type { RepoSnapshotStatus } from '../../product/runtime/sovereignFunctionalGuards';
import type { RepoFile } from '../types';
import type { SovereignDependencyLifecycleState } from '../../product/runtime/sovereignDependencyLifecycle';

export type SetupPhase = 'no-repo' | 'repo-loading' | 'repo-loaded' | 'repo-error';
export type TokenStatus = 'none' | 'missing' | 'valid' | 'expired';

export interface SetupStateInput {
  repoUrl: string;
  setRepoUrl: (url: string) => void;
  repoBranch: string;
  setRepoBranch: (branch: string) => void;
  githubToken: string;
  setGithubToken: (token: string) => void;
  repoFiles: RepoFile[];
  repoStatus: string;
  isRepoBusy: boolean;
  githubDependencyLifecycle: SovereignDependencyLifecycleState;
  loadRepoTree: (options?: { repoUrl?: string; repoBranch?: string; githubToken?: string }) => Promise<void>;
  restoreRepoSnapshot: (snapshot: { repoUrl: string; repoBranch: string; repoStatus: string; repoFiles: RepoFile[] }) => void;
  clearRepoSnapshot: () => void;
}

export interface SetupState extends SetupStateInput {
  hasToken: boolean;
  tokenStatus: TokenStatus;
  redactedToken: string;
  repoSnapshotStatus: RepoSnapshotStatus;
  setupPhase: SetupPhase;
  dependencyPhase: string;
  dependencyHealthy: boolean;
  settings?: ProjectSettings;
  setSettings?: (settings: ProjectSettings) => void;
}

function deriveSetupPhase(input: {
  isRepoBusy: boolean;
  ready: boolean;
  repoStatus: string;
  repoUrl: string;
}): SetupPhase {
  if (input.isRepoBusy) return 'repo-loading';
  if (input.ready) return 'repo-loaded';
  if (input.repoStatus.includes('fehlt') || input.repoStatus.includes('Noch kein') || !input.repoUrl.trim()) {
    return 'no-repo';
  }
  return 'repo-error';
}

export function useSetupState(existingGithubState?: SetupStateInput): SetupState {
  const internalGithubState = useGithubRepo();
  const githubState = existingGithubState ?? internalGithubState;
  const [settings, setSettings] = useState<ProjectSettings>(defaultSettings);

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
  } = githubState;

  const hasToken = useMemo(() => hasGitHubToken(githubToken), [githubToken]);
  const tokenStatus = useMemo<TokenStatus>(() => {
    if (!githubToken.trim()) return 'none';
    if (!hasToken) return 'missing';
    return 'valid';
  }, [githubToken, hasToken]);
  const redactedToken = useMemo(() => createGitHubAuthSession(githubToken).redactedToken, [githubToken]);
  const repoSnapshotStatus = useMemo(() => getRepoSnapshotStatus(repoFiles), [repoFiles]);
  const setupPhase = useMemo(
    () => deriveSetupPhase({ isRepoBusy, ready: repoSnapshotStatus.ready, repoStatus, repoUrl }),
    [isRepoBusy, repoSnapshotStatus.ready, repoStatus, repoUrl],
  );
  const dependencyPhase = useMemo(() => githubDependencyLifecycle.phase, [githubDependencyLifecycle.phase]);
  const dependencyHealthy = useMemo(
    () => githubDependencyLifecycle.phase === 'ready' || githubDependencyLifecycle.phase === 'idle',
    [githubDependencyLifecycle.phase],
  );

  return {
    repoUrl,
    setRepoUrl,
    repoBranch,
    setRepoBranch,
    githubToken,
    setGithubToken,
    hasToken,
    tokenStatus,
    redactedToken,
    repoFiles,
    repoStatus,
    isRepoBusy,
    repoSnapshotStatus,
    setupPhase,
    loadRepoTree,
    restoreRepoSnapshot,
    clearRepoSnapshot,
    githubDependencyLifecycle,
    dependencyPhase,
    dependencyHealthy,
    settings,
    setSettings,
  };
}

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

  window.dispatchEvent(new CustomEvent('sovereign:setup-state', {
    detail: window.__sovereignSetupState,
  }));
}

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
