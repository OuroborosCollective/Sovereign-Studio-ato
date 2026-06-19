/**
 * Centralized Repo Access State
 * 
 * Single source of truth for repository state across the entire app.
 * All UI components, robot status, guards, and automation decisions
 * must read from this state.
 */

import type { RepoFile } from '../../github/types';
import { getRepoSnapshotStatus } from './sovereignFunctionalGuards';

/**
 * Repo Access State - Single source of truth for repository state
 */
export interface RepoAccessState {
  repoUrl: string;
  repoBranch: string;
  githubTokenPresent: boolean;
  repoFiles: RepoFile[];
  repoSnapshotStatus: {
    ready: boolean;
    fileCount: number;
    reason: string;
  };
  lastRepoLoadAt: number | null;
  lastRepoLoadError: string | null;
}

/**
 * Create initial RepoAccessState
 */
export function createInitialRepoAccessState(): RepoAccessState {
  return {
    repoUrl: '',
    repoBranch: 'main',
    githubTokenPresent: false,
    repoFiles: [],
    repoSnapshotStatus: {
      ready: false,
      fileCount: 0,
      reason: 'No repository loaded',
    },
    lastRepoLoadAt: null,
    lastRepoLoadError: null,
  };
}

/**
 * Compute derived state from raw values
 */
export function computeRepoAccessState(
  repoUrl: string,
  repoBranch: string,
  githubTokenPresent: boolean,
  repoFiles: RepoFile[],
  lastRepoLoadAt: number | null,
  lastRepoLoadError: string | null
): RepoAccessState {
  const repoSnapshotStatus = getRepoSnapshotStatus(repoFiles);
  
  return {
    repoUrl,
    repoBranch,
    githubTokenPresent,
    repoFiles,
    repoSnapshotStatus,
    lastRepoLoadAt,
    lastRepoLoadError,
  };
}

/**
 * Check if repo is truly ready:
 * - repoFiles.length > 0
 * - repoSnapshotStatus.ready === true
 */
export function isRepoReady(state: RepoAccessState): boolean {
  return state.repoFiles.length > 0 && state.repoSnapshotStatus.ready;
}

/**
 * Get blocking error for automation decisions
 * Returns null if no blocking error exists
 */
export function getBlockingError(state: RepoAccessState): string | null {
  if (state.lastRepoLoadError) {
    return state.lastRepoLoadError;
  }
  
  if (!state.repoUrl) {
    return 'No repository URL configured';
  }
  
  if (!state.repoSnapshotStatus.ready) {
    return state.repoSnapshotStatus.reason;
  }
  
  return null;
}

/**
 * Compute automation readiness
 */
export function computeAutomationReadiness(
  state: RepoAccessState,
  mission: string,
  solutionPatternVersion: string | null
): {
  canRun: boolean;
  reason: string;
  blockingError: string | null;
} {
  const blockingError = getBlockingError(state);
  
  if (blockingError) {
    return { canRun: false, reason: blockingError, blockingError };
  }
  
  if (!mission.trim()) {
    return { canRun: false, reason: 'No mission/auftrag provided', blockingError: 'No mission provided' };
  }
  
  return { canRun: true, reason: 'Ready for automation', blockingError: null };
}

/**
 * Build a deterministic automation run key from state
 */
export function buildAutomationRunKey(
  state: RepoAccessState,
  mission: string,
  solutionPatternVersion: string | null,
  lastBlockingErrorHash: string | null
): string {
  const parts = [
    // Core identity
    state.repoUrl || 'none',
    state.repoBranch || 'main',
    // Auth state (just presence, never the token itself)
    state.githubTokenPresent ? 'has-token' : 'no-token',
    // Repo state
    state.repoSnapshotStatus.ready ? 'ready' : 'not-ready',
    state.repoFiles.length.toString(),
    // Mission (trimmed)
    mission.trim() || 'no-mission',
    // Pattern memory version
    solutionPatternVersion || 'no-patterns',
    // Last blocking error hash
    lastBlockingErrorHash || 'no-error',
  ];
  
  return parts.join('|');
}

/**
 * Bot status colors
 */
export type BotStatusColor = 'red' | 'yellow' | 'green' | 'neutral';

/**
 * Bot status based on real runtime state
 */
export interface BotStatus {
  color: BotStatusColor;
  message: string;
  isActiveWork: boolean;
}

/**
 * Compute bot status from real runtime state
 * 
 * Rules:
 * - Red: last blocking error exists (fatal)
 * - Yellow: repo missing, PAT missing for private repo, mission missing, user decision needed
 * - Green: active runtime step running OR result ready for review
 * - Neutral: ready for mission
 */
export function computeBotStatus(
  state: RepoAccessState,
  mission: string,
  activeStep: string | null,
  hasResultReady: boolean,
  isRepoBusy: boolean,
  isPublishing: boolean,
  isWatchingWorkflow: boolean,
  isRemoteMemoryBusy: boolean
): BotStatus {
  // Check for fatal blocking error - RED
  const blockingError = getBlockingError(state);
  if (blockingError && state.lastRepoLoadError) {
    // Only RED if there's an actual load error
    return {
      color: 'red',
      message: blockingError,
      isActiveWork: false,
    };
  }
  
  // Check for active work - GREEN (only if truly active)
  const isActiveWork = Boolean(
    activeStep || // real runtime step
    isRepoBusy ||
    isPublishing ||
    isWatchingWorkflow ||
    isRemoteMemoryBusy
  );
  
  if (isActiveWork) {
    if (activeStep) {
      return {
        color: 'green',
        message: `Working: ${activeStep}`,
        isActiveWork: true,
      };
    }
    if (isPublishing) {
      return {
        color: 'green',
        message: 'Publishing...',
        isActiveWork: true,
      };
    }
    if (isWatchingWorkflow) {
      return {
        color: 'green',
        message: 'Watching workflow...',
        isActiveWork: true,
      };
    }
    return {
      color: 'green',
      message: 'Working...',
      isActiveWork: true,
    };
  }
  
  // Check for yellow conditions (recoverable issues)
  if (!state.repoUrl) {
    return {
      color: 'yellow',
      message: 'No repository URL configured',
      isActiveWork: false,
    };
  }
  
  if (state.repoFiles.length === 0) {
    return {
      color: 'yellow',
      message: 'Repository needs to be loaded',
      isActiveWork: false,
    };
  }
  
  if (!state.repoSnapshotStatus.ready) {
    return {
      color: 'yellow',
      message: state.repoSnapshotStatus.reason || 'Repository not ready',
      isActiveWork: false,
    };
  }
  
  if (!mission.trim()) {
    return {
      color: 'yellow',
      message: 'No mission/auftrag provided',
      isActiveWork: false,
    };
  }
  
  if (hasResultReady) {
    return {
      color: 'green',
      message: 'Result ready for review',
      isActiveWork: false,
    };
  }
  
  // Neutral - ready for mission
  return {
    color: 'neutral',
    message: 'Ready',
    isActiveWork: false,
  };
}
