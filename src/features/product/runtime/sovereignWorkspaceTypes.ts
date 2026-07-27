/**
 * Sovereign Workspace Types
 *
 * Type definitions for the Sovereign Agent Workspace Runtime.
 * Defines the Workspace Contract for agent-neutral isolated execution.
 *
 * Hard product rules:
 * - UI does not create truth; Runtime creates truth.
 * - Every workspace is per-job isolated.
 * - No agent shares live the same write folder.
 * - No auto-merge.
 * - Draft PR yes, auto-merge no.
 * - No secrets in workspace logs, chat, telemetry or PR body.
 * - No mocks/stubs/facades in the live path.
 */

/** Workspace purpose types - determines what kind of work the workspace will perform */
export type WorkspacePurpose =
  | 'analysis'   // Read-only analysis, no file changes
  | 'patch'     // Small file changes
  | 'test'      // Test execution
  | 'draft_pr'  // Draft PR creation
  | 'repair';   // Bug/error repair

/** Workspace status - represents the current state of a workspace */
export type WorkspaceStatus =
  | 'idle'      // No active workspace
  | 'queued'    // Workspace requested but not yet started
  | 'running'   // Workspace is actively executing
  | 'blocked'   // Workspace blocked by a condition
  | 'failed'    // Workspace execution failed
  | 'completed' // Workspace completed successfully
  | 'cleaned';  // Workspace resources cleaned up

/**
 * Workspace event kinds - every workspace step must emit events
 */
export type SovereignWorkspaceEventKind =
  | 'workspace_requested'
  | 'workspace_created'
  | 'repo_cloned'
  | 'dependencies_checked'
  | 'files_changed'
  | 'tests_started'
  | 'tests_finished'
  | 'diff_ready'
  | 'draft_pr_ready'
  | 'blocked'
  | 'failed';

/**
 * Single workspace event - emitted during workspace lifecycle
 */
export interface SovereignWorkspaceEvent {
  readonly kind: SovereignWorkspaceEventKind;
  readonly timestamp: number;
  readonly jobId: string;
  readonly detail?: string;
  readonly data?: Record<string, unknown>;
}

/**
 * Request to create a new Sovereign workspace
 */
export interface SovereignWorkspaceRequest {
  readonly jobId: string;
  readonly purpose: WorkspacePurpose;
  readonly repoUrl: string;
  readonly baseBranch: string;
  readonly mission: string;
  readonly allowedPaths: readonly string[];
  readonly forbiddenPaths: readonly string[];
  readonly memoryHints?: readonly string[];
  readonly requireTests: boolean;
  readonly allowCommit: boolean;
  readonly allowDraftPr: boolean;
}

/**
 * Result from a Sovereign workspace execution
 */
export interface SovereignWorkspaceResult {
  readonly jobId: string;
  readonly status: WorkspaceStatus;
  readonly events: readonly SovereignWorkspaceEvent[];
  readonly changedFiles: readonly string[];
  readonly diffSummary?: string;
  readonly testSummary?: string;
  readonly draftPrUrl?: string;
  readonly blocker?: string;
  readonly workspaceInspectorUrl?: string;
  readonly error?: string;
}

/**
 * Workspace adapter interface - for plugging in different executors
 * This makes the runtime agent-neutral, not Sovereign Agent-hardcoded.
 */
export interface WorkspaceAdapter {
  readonly id: string;
  readonly label: string;
  readonly supportedPurposes: readonly WorkspacePurpose[];
  readonly isAvailable: () => Promise<boolean>;

  /**
   * Execute a workspace request
   * Returns the result with events, changed files, and status
   */
  execute(request: SovereignWorkspaceRequest): Promise<SovereignWorkspaceResult>;

  /**
   * Clean up workspace resources
   */
  cleanup(jobId: string): Promise<void>;
}

/**
 * Workspace gate - decision point for whether a workspace should be created
 */
export interface WorkspaceGate {
  readonly name: string;
  readonly description: string;
  readonly check: (context: WorkspaceGateContext) => WorkspaceGateResult;
}

export interface WorkspaceGateContext {
  readonly repoUrl?: string;
  readonly baseBranch?: string;
  readonly mission?: string;
  readonly targetPaths?: readonly string[];
  readonly requiresWorkspace: boolean;  // True if task complexity demands a workspace
  readonly isSimpleQuestion: boolean;    // True if this is a simple Q&A task
  readonly isReadOnlyAnalysis: boolean;  // True if only analysis is needed
  readonly isSmallDocPatch: boolean;     // True if this is a small docs patch
  readonly hasWorkspaceExecutor: boolean; // True if a workspace executor is available
}

export interface WorkspaceGateResult {
  readonly passed: boolean;
  readonly reason: string;
  readonly blocker?: string;
  readonly nextAction?: WorkspaceGateNextAction;
}

export type WorkspaceGateNextAction =
  | 'direct_patch'
  | 'start_workspace'
  | 'snapshot_only'
  | 'block'
  | 'ask_user';

/**
 * Routing decision from the capability router
 */
export interface WorkspaceRoutingDecision {
  readonly route: WorkspaceRoute;
  readonly capability: WorkspaceCapability;
  readonly allowed: boolean;
  readonly reason: string;
  readonly blocker?: string;
  readonly nextAction: WorkspaceGateNextAction;
}

export type WorkspaceRoute =
  | 'worker-chat'
  | 'direct-github-patch'
  | 'isolated-workspace'
  | 'sovereign-agent'
  | 'snapshot-analysis';

export type WorkspaceCapability =
  | 'free_chat'
  | 'repo_read'
  | 'direct_github_patch'
  | 'isolated_workspace'
  | 'test_runner'
  | 'draft_pr';

/**
 * Helper type for checking if a workspace should be created
 */
export interface WorkspaceTrigger {
  readonly requiresWorkspace: boolean;
  readonly reason: string;
  readonly suggestedPurpose?: WorkspacePurpose;
}

// Bolt ⚡ Optimization: Hoist and compile regular expression patterns at module level
// to avoid dynamic re-compilation of pattern instances on every function call or recursion.
const GITHUB_TOKEN_MASK_REGEX = /ghp_[a-zA-Z0-9]{36}/g;
const API_KEY_MASK_REGEX = /sk-[a-zA-Z0-9]{48}/g;
const BEARER_TOKEN_MASK_REGEX = /Bearer\s+[a-zA-Z0-9_-]+/gi;
const TOKEN_LABEL_MASK_REGEX = /token["']?\s*[:=]\s*["']?[a-zA-Z0-9_-]+/gi;

const WORKSPACE_SECRET_PATTERNS = [
  GITHUB_TOKEN_MASK_REGEX,
  API_KEY_MASK_REGEX,
  BEARER_TOKEN_MASK_REGEX,
  TOKEN_LABEL_MASK_REGEX,
];

/**
 * Create a workspace event with secret masking
 * Ensures no tokens/secrets leak into events, logs, or PR body
 */
export function createMaskedWorkspaceEvent(
  kind: SovereignWorkspaceEventKind,
  jobId: string,
  detail?: string,
  data?: Record<string, unknown>
): SovereignWorkspaceEvent {
  // Mask any potential secrets in detail using pre-compiled regexes
  const maskedDetail = detail
    ? detail.replace(GITHUB_TOKEN_MASK_REGEX, '[GITHUB_TOKEN_MASKED]')
           .replace(API_KEY_MASK_REGEX, '[API_KEY_MASKED]')
           .replace(BEARER_TOKEN_MASK_REGEX, 'Bearer [TOKEN_MASKED]')
    : undefined;

  // Mask secrets in data
  const maskedData = data ? maskSecretsInObject(data) : undefined;

  return {
    kind,
    timestamp: Date.now(),
    jobId,
    detail: maskedDetail,
    data: maskedData,
  };
}

/**
 * Recursively mask secrets in an object
 */
function maskSecretsInObject(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === 'string') {
      let masked = value;
      for (let i = 0; i < WORKSPACE_SECRET_PATTERNS.length; i++) {
        masked = masked.replace(WORKSPACE_SECRET_PATTERNS[i], '[SECRET_MASKED]');
      }
      result[key] = masked;
    } else if (typeof value === 'object' && value !== null) {
      result[key] = maskSecretsInObject(value as Record<string, unknown>);
    } else {
      result[key] = value;
    }
  }

  return result;
}

/**
 * Validate that a workspace request is properly formed
 */
export function validateWorkspaceRequest(request: SovereignWorkspaceRequest): { valid: boolean; error?: string } {
  if (!request.jobId || typeof request.jobId !== 'string') {
    return { valid: false, error: 'jobId is required and must be a string' };
  }

  if (!request.repoUrl || typeof request.repoUrl !== 'string') {
    return { valid: false, error: 'repoUrl is required and must be a string' };
  }

  if (!request.repoUrl.startsWith('https://github.com/')) {
    return { valid: false, error: 'repoUrl must start with https://github.com/' };
  }

  if (!request.baseBranch || typeof request.baseBranch !== 'string') {
    return { valid: false, error: 'baseBranch is required and must be a string' };
  }

  if (!request.mission || typeof request.mission !== 'string') {
    return { valid: false, error: 'mission is required and must be a string' };
  }

  if (!Array.isArray(request.allowedPaths)) {
    return { valid: false, error: 'allowedPaths must be an array' };
  }

  if (!Array.isArray(request.forbiddenPaths)) {
    return { valid: false, error: 'forbiddenPaths must be an array' };
  }

  return { valid: true };
}

/**
 * Check if a changed file path is within allowed paths
 */
export function isPathAllowed(filePath: string, allowedPaths: readonly string[], forbiddenPaths: readonly string[]): boolean {
  // Check forbidden paths first
  for (const forbidden of forbiddenPaths) {
    if (filePath.startsWith(forbidden) || filePath === forbidden) {
      return false;
    }
  }

  // Check allowed paths
  if (allowedPaths.length === 0) return false; // No allowed paths means nothing is allowed

  for (const allowed of allowedPaths) {
    if (filePath.startsWith(allowed) || filePath === allowed) {
      return true;
    }
  }

  return false;
}
