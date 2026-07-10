/**
 * Sovereign Workspace Runtime
 *
 * Agent-neutral isolated workspace executor for Sovereign.
 * Implements the Workspace Contract with hard product rules.
 *
 * Hard product rules:
 * - UI does not create truth; Runtime creates truth
 * - Every workspace is per-job isolated
 * - No agent shares live the same write folder
 * - No auto-merge; Draft PR yes, auto-merge no
 * - No secrets in workspace logs, chat, telemetry or PR body
 * - No mocks/stubs/facades in the live path
 *
 * This runtime is agent-neutral, not Sovereign Agent-hardcoded.
 * Sovereign Agent can be connected as the first adapter.
 */

import type {
  WorkspaceAdapter,
  WorkspacePurpose,
  WorkspaceStatus,
  SovereignWorkspaceEvent,
  SovereignWorkspaceRequest,
  SovereignWorkspaceResult,
  WorkspaceGateContext,
  WorkspaceRoutingDecision,
  WorkspaceRoute,
  WorkspaceCapability,
} from './sovereignWorkspaceTypes';
import {
  createMaskedWorkspaceEvent,
  validateWorkspaceRequest,
} from './sovereignWorkspaceTypes';
import {
  shouldCreateWorkspace,
  validateChangedFiles,
  evaluateTaskComplexity,
} from './sovereignWorkspacePolicy';

/**
 * Workspace runtime state
 */
export interface SovereignWorkspaceRuntimeState {
  readonly activeJobs: ReadonlyMap<string, SovereignWorkspaceRequest>;
  readonly completedJobs: ReadonlyMap<string, SovereignWorkspaceResult>;
  readonly adapters: readonly WorkspaceAdapter[];
}

/**
 * Create initial runtime state
 */
export function createInitialRuntimeState(adapters: readonly WorkspaceAdapter[] = []): SovereignWorkspaceRuntimeState {
  return {
    activeJobs: new Map(),
    completedJobs: new Map(),
    adapters,
  };
}

/**
 * Workspace runtime configuration
 */
export interface SovereignWorkspaceRuntimeConfig {
  readonly defaultAllowedPaths?: readonly string[];
  readonly defaultForbiddenPaths?: readonly string[];
  readonly maxConcurrentJobs?: number;
  readonly jobTimeoutMs?: number;
}

/**
 * Default configuration
 */
export const DEFAULT_WORKSPACE_CONFIG: Required<SovereignWorkspaceRuntimeConfig> = {
  defaultAllowedPaths: [],
  defaultForbiddenPaths: ['.env', 'node_modules/', 'dist/', 'build/', '.git/'],
  maxConcurrentJobs: 3,
  jobTimeoutMs: 30 * 60 * 1000, // 30 minutes
};

/**
 * Main workspace runtime class
 */
export class SovereignWorkspaceRuntime {
  private readonly config: Required<SovereignWorkspaceRuntimeConfig>;
  private readonly adapters: WorkspaceAdapter[];
  private activeJobs: Map<string, SovereignWorkspaceRequest> = new Map();
  private completedJobs: Map<string, SovereignWorkspaceResult> = new Map();
  private adaptersById: Map<string, WorkspaceAdapter> = new Map();

  constructor(adapters: readonly WorkspaceAdapter[] = [], config: Partial<SovereignWorkspaceRuntimeConfig> = {}) {
    this.config = { ...DEFAULT_WORKSPACE_CONFIG, ...config };
    this.adapters = [...adapters];
    for (const adapter of this.adapters) {
      this.adaptersById.set(adapter.id, adapter);
    }
  }

  /**
   * Register a new workspace adapter
   */
  registerAdapter(adapter: WorkspaceAdapter): void {
    if (this.adaptersById.has(adapter.id)) {
      throw new Error(`Adapter with id '${adapter.id}' is already registered`);
    }
    this.adapters.push(adapter);
    this.adaptersById.set(adapter.id, adapter);
  }

  /**
   * Unregister a workspace adapter
   */
  unregisterAdapter(adapterId: string): void {
    const index = this.adapters.findIndex((a) => a.id === adapterId);
    if (index !== -1) {
      this.adapters.splice(index, 1);
      this.adaptersById.delete(adapterId);
    }
  }

  /**
   * Get available adapters for a given purpose
   */
  async getAvailableAdapters(purpose: WorkspacePurpose): Promise<WorkspaceAdapter[]> {
    const available: WorkspaceAdapter[] = [];
    for (const adapter of this.adapters) {
      if (adapter.supportedPurposes.includes(purpose)) {
        const isAvail = await adapter.isAvailable();
        if (isAvail) {
          available.push(adapter);
        }
      }
    }
    return available;
  }

  /**
   * Check if any workspace executor is available
   */
  async hasAvailableExecutor(): Promise<boolean> {
    const purposes: WorkspacePurpose[] = ['patch', 'test', 'draft_pr', 'repair'];
    for (const purpose of purposes) {
      const adapters = await this.getAvailableAdapters(purpose);
      if (adapters.length > 0) return true;
    }
    return false;
  }

  /**
   * Check if any workspace executor is available (sync version for routing)
   */
  hasExecutorSync(): boolean {
    return this.adapters.length > 0;
  }

  /**
   * Make routing decision based on context
   */
  makeRoutingDecision(context: {
    repoUrl?: string;
    baseBranch?: string;
    mission?: string;
    targetPaths?: readonly string[];
    isReadOnly?: boolean;
  }): WorkspaceRoutingDecision {
    // Use sync check for immediate routing decision
    const hasExecutor = this.hasExecutorSync();
    const policyResult = shouldCreateWorkspace(
      context.repoUrl,
      context.baseBranch,
      context.mission,
      context.targetPaths,
      hasExecutor
    );

    // Determine route based on policy result
    let route: WorkspaceRoute = 'worker-chat';
    let capability: WorkspaceCapability = 'free_chat';

    if (context.isReadOnly) {
      route = 'snapshot-analysis';
      capability = 'repo_read';
    } else if (policyResult.allowed) {
      route = 'isolated-workspace';
      capability = 'isolated_workspace';
    } else if (context.targetPaths?.some((p) => p.match(/\.(md|mdx)$/i))) {
      route = 'direct-github-patch';
      capability = 'direct_github_patch';
    }

    return {
      route,
      capability,
      allowed: policyResult.allowed,
      reason: policyResult.reason,
      blocker: policyResult.blocker,
      nextAction: policyResult.allowed ? 'start_workspace' : policyResult.rules.find((r) => !r.passed)?.id === 'workspace-required' ? 'block' : 'direct_patch',
    };
  }

  /**
   * Request a new workspace job
   */
  async requestWorkspace(request: SovereignWorkspaceRequest): Promise< SovereignWorkspaceResult> {
    // Validate request
    const validation = validateWorkspaceRequest(request);
    if (!validation.valid) {
      return this.createBlockedResult(request.jobId, validation.error ?? 'Invalid request');
    }

    // Check policy gates
    const policyResult = shouldCreateWorkspace(
      request.repoUrl,
      request.baseBranch,
      request.mission,
      request.allowedPaths,
      await this.hasAvailableExecutor()
    );

    if (!policyResult.allowed) {
      return this.createBlockedResult(request.jobId, policyResult.reason, policyResult.blocker);
    }

    // Check concurrent job limit
    if (this.activeJobs.size >= this.config.maxConcurrentJobs) {
      return this.createBlockedResult(request.jobId, 'Maximum concurrent jobs reached', 'max_concurrent_jobs');
    }

    // Find suitable adapter
    const adapters = await this.getAvailableAdapters(request.purpose);
    if (adapters.length === 0) {
      return this.createBlockedResult(
        request.jobId,
        `No executor available for purpose: ${request.purpose}`,
        'executor_unavailable'
      );
    }

    // Use first available adapter (can be extended to support adapter selection)
    const adapter = adapters[0];

    // Track active job
    this.activeJobs.set(request.jobId, request);

    try {
      // Execute workspace
      const result = await adapter.execute(request);

      // Validate changed files against policy
      if (result.changedFiles.length > 0) {
        const validation = validateChangedFiles(
          result.changedFiles,
          request.allowedPaths,
          request.forbiddenPaths
        );

        if (!validation.valid) {
          // Return blocked result with violations
          return {
            ...result,
            status: 'blocked',
            blocker: `Changed files violate policy: ${validation.violations.join('; ')}`,
            changedFiles: result.changedFiles,
          };
        }
      }

      // Validate Draft PR creation
      if (result.draftPrUrl && !request.allowDraftPr) {
        return {
          ...result,
          status: 'blocked',
          blocker: 'Draft PR created without explicit permission (allowDraftPr === false)',
          draftPrUrl: undefined,
        };
      }

      // Store completed result
      this.completedJobs.set(request.jobId, result);

      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      const failedResult: SovereignWorkspaceResult = {
        jobId: request.jobId,
        status: 'failed',
        events: [
          createMaskedWorkspaceEvent('failed', request.jobId, errorMessage),
        ],
        changedFiles: [],
        error: errorMessage,
      };
      this.completedJobs.set(request.jobId, failedResult);
      return failedResult;
    } finally {
      // Remove from active jobs
      this.activeJobs.delete(request.jobId);
    }
  }

  /**
   * Clean up a workspace job
   */
  async cleanupJob(jobId: string): Promise<void> {
    // Find which adapter handled this job
    for (const adapter of this.adapters) {
      try {
        await adapter.cleanup(jobId);
      } catch {
        // Ignore cleanup errors
      }
    }

    // Remove from active jobs
    this.activeJobs.delete(jobId);
  }

  /**
   * Get job status
   */
  getJobStatus(jobId: string): { active: boolean; completed: boolean; result?: SovereignWorkspaceResult } {
    if (this.activeJobs.has(jobId)) {
      return { active: true, completed: false };
    }

    const completed = this.completedJobs.get(jobId);
    return {
      active: false,
      completed: completed !== undefined,
      result: completed,
    };
  }

  /**
   * Get all active jobs
   */
  getActiveJobs(): readonly SovereignWorkspaceRequest[] {
    return Array.from(this.activeJobs.values());
  }

  /**
   * Get all completed jobs
   */
  getCompletedJobs(): readonly SovereignWorkspaceResult[] {
    return Array.from(this.completedJobs.values());
  }

  /**
   * Create a blocked result with proper event
   */
  private createBlockedResult(jobId: string, reason: string, blocker?: string): SovereignWorkspaceResult {
    return {
      jobId,
      status: 'blocked',
      events: [
        createMaskedWorkspaceEvent('blocked', jobId, reason),
      ],
      changedFiles: [],
      blocker: blocker ?? reason,
    };
  }
}

function isTestWorkspaceAdapterRuntime(): boolean {
  const runtime = globalThis as {
    process?: { env?: { NODE_ENV?: string; VITEST?: string } };
  };

  return runtime.process?.env?.NODE_ENV === 'test' || runtime.process?.env?.VITEST === 'true';
}

/**
 * Create a test-only adapter that tracks workspace requests.
 *
 * Live-path invariant: this adapter never reports availability or completion
 * outside a test runtime. Runtime truth must come from real executors only.
 */
export function createMockWorkspaceAdapter(id: string, label: string): WorkspaceAdapter {
  const jobs = new Map<string, SovereignWorkspaceRequest>();

  return {
    id,
    label,
    supportedPurposes: ['analysis', 'patch', 'test', 'draft_pr', 'repair'],

    isAvailable: async () => isTestWorkspaceAdapterRuntime(),

    execute: async (request: SovereignWorkspaceRequest): Promise<SovereignWorkspaceResult> => {
      if (!isTestWorkspaceAdapterRuntime()) {
        return {
          jobId: request.jobId,
          status: 'blocked',
          events: [
            createMaskedWorkspaceEvent(
              'blocked',
              request.jobId,
              'Test workspace adapter is unavailable outside test runtime'
            ),
          ],
          changedFiles: [],
          blocker: 'test_workspace_adapter_not_available',
        };
      }

      jobs.set(request.jobId, request);

      const events: SovereignWorkspaceEvent[] = [
        createMaskedWorkspaceEvent('workspace_requested', request.jobId, `Workspace requested for purpose: ${request.purpose}`),
        createMaskedWorkspaceEvent('workspace_created', request.jobId, `Workspace created with adapter: ${id}`),
        createMaskedWorkspaceEvent('repo_cloned', request.jobId, `Repository cloned: ${request.repoUrl}`),
      ];

      if (request.requireTests) {
        events.push(createMaskedWorkspaceEvent('tests_started', request.jobId, 'Running tests...'));
        events.push(createMaskedWorkspaceEvent('tests_finished', request.jobId, 'Tests completed'));
      }

      events.push(createMaskedWorkspaceEvent('diff_ready', request.jobId, 'Changes ready for review'));

      if (request.allowDraftPr) {
        events.push(createMaskedWorkspaceEvent('draft_pr_ready', request.jobId, 'Draft PR available'));
      }

      return {
        jobId: request.jobId,
        status: 'completed',
        events,
        changedFiles: [],
        diffSummary: `Test adapter ${id} completed workspace for job ${request.jobId}`,
      };
    },

    cleanup: async (jobId: string): Promise<void> => {
      jobs.delete(jobId);
    },
  };
}

/**
 * Determine workspace purpose from mission text
 */
export function determineWorkspacePurpose(mission: string): WorkspacePurpose {
  const lower = mission.toLowerCase();

  if (/\b(test|spec|coverage)\b/.test(lower)) return 'test';
  if (/\bdraft\s*pr\b/.test(lower)) return 'draft_pr';
  if (/\b(fix|repair|bug|error)\b/.test(lower)) return 'repair';
  if (/\b(analyse|analyze|review|check)\b/.test(lower) && !/\b(änder|edit|change)\b/.test(lower)) return 'analysis';

  return 'patch';
}

/**
 * Check if a mission should trigger workspace creation
 */
export function shouldTriggerWorkspace(
  mission: string,
  targetPaths?: readonly string[]
): { shouldTrigger: boolean; reason: string; suggestedPurpose?: WorkspacePurpose } {
  const trigger = evaluateTaskComplexity(mission, targetPaths);

  return {
    shouldTrigger: trigger.requiresWorkspace,
    reason: trigger.reason,
    suggestedPurpose: trigger.suggestedPurpose,
  };
}
