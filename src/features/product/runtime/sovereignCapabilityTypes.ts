/**
 * Sovereign Capability Types
 *
 * Central type definitions for the Sovereign Capability Router.
 * These types define the capability model and routing contract.
 *
 * Issue #502: Runtime: add Sovereign Capability Router for chat, patch, workspace and Draft PR routes
 */

/**
 * Sovereign capabilities - what the runtime can do.
 * Sovereign Agent is one possible executor, not the only coding route.
 */
export type SovereignCapability =
  | 'free_chat'         // Pure chat questions, no code/repo actions
  | 'repo_read'         // Load and analyze repository
  | 'code_patch_plan'   // Generate code patches via LLM
  | 'direct_github_patch' // Small README/docs changes via direct GitHub API
  | 'isolated_workspace' // Isolated workspace executor for complex work
  | 'test_runner'       // Run tests
  | 'draft_pr'          // Create draft PR
  | 'workflow_watch'    // Watch GitHub Actions workflow
  | 'memory_search';    // Search memory/patterns

/**
 * Sovereign routes - execution paths for different capabilities.
 */
export type SovereignRoute =
  | 'worker-chat'          // Cloudflare Worker chat route
  | 'code-llm'            // Code-capable LLM for patches
  | 'direct-github-patch' // Direct GitHub API for simple changes
  | 'workspace-executor'   // Isolated workspace (Replit/CodeSandbox)
  | 'sovereign-agent'           // Sovereign Agent executor
  | 'draft-pr-runtime'     // Draft PR creation
  | 'local-runtime-answer' // Local runtime answer, no external call
  | 'repo-load';          // Repository loading

/**
 * Blocker types - why an action cannot proceed.
 * Used to provide accurate next-action guidance.
 */
export type SovereignRouteBlocker =
  | 'repo_missing'               // No repository loaded
  | 'github_access_missing'       // GitHub access not configured
  | 'github_access_validating'    // GitHub access in validation
  | 'executor_unavailable'        // No executor (Sovereign Agent/workspace) available
  | 'workspace_required'          // Workspace executor required but unavailable
  | 'package_required'            // Patch/package must be generated before Draft PR
  | 'unsupported_intent'          // Intent too complex for direct patch
  | 'unsafe_action';              // Action would write to forbidden paths

/**
 * Next actions - what the user/runtime should do next.
 * Predictive may suggest these actions, but must never execute them directly.
 */
export type SovereignNextAction =
  | 'ask_user'                    // Ask user for clarification
  | 'load_repo'                   // Load a repository first
  | 'validate_github_access'      // Validate GitHub access
  | 'generate_patch_package'      // Generate patch/package before Draft PR
  | 'run_worker'                  // Run chat worker
  | 'run_direct_patch'            // Run direct GitHub patch
  | 'start_workspace'             // Start workspace executor
  | 'start_agent'             // Start Sovereign Agent executor
  | 'create_draft_pr'             // Create draft PR
  | 'show_blocker'                // Show blocker explanation
  | 'answer_locally'              // Answer from existing runtime state without external route
  | 'create_agent_job'            // Explicitly create a backend Sovereign Agent Job
  | 'provision_agent_workspace'   // Provision agent workspace through backend state
  | 'run_agent_tool'              // Run a guarded backend agent tool
  | 'validate_agent_result'       // Validate changedFiles/diff/tests evidence
  | 'prepare_agent_draft_pr'      // Prepare draft PR readiness state only
  | 'learn_agent_pattern'         // Persist validated local pattern candidate only
  | 'cleanup_agent_workspace';    // Cleanup terminal agent workspace

/**
 * Decision produced by the capability router.
 * This is the central truth source for routing.
 */
export interface CapabilityDecision {
  readonly route: SovereignRoute;
  readonly capability: SovereignCapability;
  readonly allowed: boolean;
  readonly reason: string;
  readonly blocker?: SovereignRouteBlocker;
  readonly nextAction: SovereignNextAction;
  /** If true, this is a terminal decision - no further routing should happen */
  readonly isTerminal?: boolean;
}

/**
 * Input for capability routing decision.
 */
export interface CapabilityRouterInput {
  readonly text: string;
  readonly repoReady: boolean;
  readonly githubAccessState: 'missing' | 'requested' | 'validating' | 'ready' | 'invalid';
  readonly agentReady: boolean;
  readonly directGitHubPatchReady: boolean;
  readonly workspaceReady: boolean;
  readonly hasActiveWorkerBlocker: boolean;
  readonly hasPackage?: boolean;
  readonly hasDraft?: boolean;
  readonly hasWorkflowReport?: boolean;
}

/**
 * Task complexity classification.
 * Determines which executor is appropriate.
 */
export type TaskComplexity = 'simple' | 'medium' | 'complex' | 'unknown';

/**
 * Intent classification from text analysis.
 */
export type IntentClassification =
  | 'free_chat'
  | 'status_question'
  | 'load_repo'
  | 'direct_patch'
  | 'code_generation'
  | 'draft_pr'
  | 'workflow_watch'
  | 'repair_workflow'
  | 'unknown';
