/**
 * GitHub Actions Runtime - Fetch and display real GitHub workflow status
 * 
 * Only polls if a Draft PR URL or commit/branch exists.
 * No fake build status. Shows unknown when no runs exist.
 * No hard percentages.
 */

import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';

export type BuildStatus = 'success' | 'failure' | 'running' | 'pending' | 'unknown';

export interface GitHubActionsStatus {
  status: BuildStatus;
  conclusion?: 'success' | 'failure' | 'cancelled' | 'skipped' | 'timed_out' | 'action_required';
  runId?: number;
  runName?: string;
  runNumber?: number;
  headBranch?: string;
  headSha?: string;
  createdAt?: string;
  updatedAt?: string;
  htmlUrl?: string;
  /** Count of changed files from OpenHands */
  changedFiles?: number;
}

/**
 * Fetch GitHub Actions status for a given PR/commit/branch
 */
export async function fetchGitHubActionsStatus(
  repoFullName: string,
  options: {
    /** GitHub token (optional for public repos) */
    token?: string;
    /** Draft PR number */
    prNumber?: number;
    /** Commit SHA */
    commitSha?: string;
    /** Branch name */
    branch?: string;
  }
): Promise<GitHubActionsStatus> {
  const { token, prNumber, commitSha, branch } = options;
  
  // Determine what to fetch
  let workflowRunsUrl: string;
  
  if (prNumber) {
    // Get runs for the PR
    workflowRunsUrl = `https://api.github.com/repos/${repoFullName}/pulls/${prNumber}/checks`;
  } else if (commitSha) {
    // Get runs for the commit
    workflowRunsUrl = `https://api.github.com/repos/${repoFullName}/commits/${commitSha}/check-runs`;
  } else if (branch) {
    // Get latest run for the branch
    workflowRunsUrl = `https://api.github.com/repos/${repoFullName}/actions/runs?branch=${encodeURIComponent(branch)}&per_page=1`;
  } else {
    return { status: 'unknown' };
  }
  
  try {
    const headers: Record<string, string> = {
      'Accept': 'application/vnd.github.v3+json',
    };
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(workflowRunsUrl, { headers });
    
    if (!response.ok) {
      if (response.status === 404) {
        return { status: 'unknown' };
      }
      // Rate limit or server error
      console.warn(`GitHub API error: ${response.status}`);
      return { status: 'unknown' };
    }
    
    const data = await response.json();
    
    // Parse response based on what we requested
    if (prNumber && data.check_runs) {
      return parseCheckRuns(data.check_runs);
    } else if (commitSha && data.check_runs) {
      return parseCheckRuns(data.check_runs);
    } else if (branch && data.workflow_runs && data.workflow_runs.length > 0) {
      return parseWorkflowRuns(data.workflow_runs);
    }
    
    return { status: 'unknown' };
  } catch (error) {
    console.warn('Failed to fetch GitHub Actions status:', error);
    return { status: 'unknown' };
  }
}

/**
 * Parse check runs response
 */
function parseCheckRuns(checkRuns: any[]): GitHubActionsStatus {
  if (!checkRuns || checkRuns.length === 0) {
    return { status: 'unknown' };
  }
  
  // Get the most recent run
  const run = checkRuns[0];
  
  let status: BuildStatus;
  switch (run.status) {
    case 'completed':
      switch (run.conclusion) {
        case 'success':
          status = 'success';
          break;
        case 'failure':
        case 'cancelled':
        case 'timed_out':
        case 'action_required':
          status = 'failure';
          break;
        default:
          status = 'unknown';
      }
      break;
    case 'in_progress':
    case 'queued':
      status = 'running';
      break;
    case 'pending':
      status = 'pending';
      break;
    default:
      status = 'unknown';
  }
  
  return {
    status,
    conclusion: run.conclusion,
    runId: run.id,
    runName: run.name,
    htmlUrl: run.html_url,
    createdAt: run.created_at,
    updatedAt: run.updated_at,
  };
}

/**
 * Parse workflow runs response
 */
function parseWorkflowRuns(runs: any[]): GitHubActionsStatus {
  if (!runs || runs.length === 0) {
    return { status: 'unknown' };
  }
  
  const run = runs[0];
  
  let status: BuildStatus;
  switch (run.status) {
    case 'completed':
      switch (run.conclusion) {
        case 'success':
          status = 'success';
          break;
        case 'failure':
        case 'cancelled':
        case 'timed_out':
        case 'action_required':
          status = 'failure';
          break;
        default:
          status = 'unknown';
      }
      break;
    case 'in_progress':
    case 'queued':
      status = 'running';
      break;
    case 'waiting':
      status = 'pending';
      break;
    default:
      status = 'unknown';
  }
  
  return {
    status,
    conclusion: run.conclusion,
    runId: run.id,
    runName: run.name,
    runNumber: run.run_number,
    headBranch: run.head_branch,
    headSha: run.head_sha,
    createdAt: run.created_at,
    updatedAt: run.updated_at,
    htmlUrl: run.html_url,
  };
}

/**
 * Build status badge color and label
 */
export function getBuildStatusDisplay(status: BuildStatus): { color: string; label: string; icon: string } {
  switch (status) {
    case 'success':
      return { color: '#34d399', label: 'Erfolgreich', icon: '✓' };
    case 'failure':
      return { color: '#fb7185', label: 'Fehlgeschlagen', icon: '✗' };
    case 'running':
      return { color: '#22d3ee', label: 'Läuft…', icon: '◐' };
    case 'pending':
      return { color: '#fbbf24', label: 'Wartend', icon: '○' };
    case 'unknown':
    default:
      return { color: '#768390', label: 'Unbekannt', icon: '?' };
  }
}

/**
 * Format Draft PR card data from OpenHands snapshot
 */
export function getDraftPrDisplayData(
  job: OpenHandsJobSnapshot | undefined,
  draftPrUrl: string | undefined
): {
  title: string;
  branch: string;
  changedFiles: number;
  prUrl: string;
} | null {
  if (!draftPrUrl && !job) return null;
  
  // Extract branch from URL - handle both branch names and PR numbers
  let branch = job?.branch || 'unbekannt';
  if (!job?.branch && draftPrUrl) {
    const urlParts = draftPrUrl.split('/');
    const lastPart = urlParts[urlParts.length - 1];
    if (lastPart && /^\d+$/.test(lastPart)) {
      branch = `PR #${lastPart}`;
    } else if (lastPart) {
      branch = lastPart;
    }
  }
  const changedFiles = typeof job?.changedFiles === 'number' ? job.changedFiles : 0;
  
  return {
    title: 'Draft PR ready',
    branch,
    changedFiles,
    prUrl: draftPrUrl || '',
  };
}

export default {
  fetchGitHubActionsStatus,
  getBuildStatusDisplay,
  getDraftPrDisplayData,
};
