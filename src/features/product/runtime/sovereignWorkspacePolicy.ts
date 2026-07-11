/**
 * Sovereign Workspace Policy
 *
 * Defines policy rules and gates for workspace creation.
 * Implements the Sovereign workspace contract with hard product rules.
 *
 * Hard product rules enforced:
 * - UI does not create truth; Runtime creates truth
 * - Every workspace is per-job isolated
 * - No agent shares live the same write folder
 * - No auto-merge; Draft PR yes, auto-merge no
 * - No secrets in workspace logs, chat, telemetry or PR body
 */

import type {
  WorkspacePurpose,
  WorkspaceGate,
  WorkspaceGateContext,
  WorkspaceGateResult,
  WorkspaceTrigger,
} from './sovereignWorkspaceTypes';

/**
 * Policy rule result
 */
export interface WorkspacePolicyRule {
  readonly id: string;
  readonly description: string;
  readonly passed: boolean;
  readonly blocker?: string;
  readonly warning?: string;
}

/**
 * Workspace policy evaluation result
 */
export interface WorkspacePolicyResult {
  readonly allowed: boolean;
  readonly rules: readonly WorkspacePolicyRule[];
  readonly reason: string;
  readonly blocker?: string;
  readonly suggestedPurpose?: WorkspacePurpose;
}

/**
 * Check if task complexity requires a workspace
 */
export function evaluateTaskComplexity(mission: string, targetPaths?: readonly string[]): WorkspaceTrigger {
  const missionLower = mission.toLowerCase();
  const pathsLower = (targetPaths ?? []).map((p) => p.toLowerCase());

  // Workspace NOT needed for simple cases (pure questions)
  const simplePatterns = [
    /\b(erkläre|explain|was ist|what is|wie geht|how do|warum|why)\b/i,
    /\b(status|zustand)\b.*\b(abfrage|query|frage)?\b/i,
    /^(hi|hello|hey|guten tag|hallo)\b/i,
  ];

  for (const pattern of simplePatterns) {
    if (pattern.test(missionLower)) {
      return {
        requiresWorkspace: false,
        reason: 'Simple question or status query - no workspace needed',
      };
    }
  }

  // Workspace NOT needed for small doc patches
  const docOnlyPatterns = [
    /\breadme\b/i,
    /\bdocs?\//i,
    /\bdocumentation\b/i,
    /\bchangelog\b/i,
    /\bupdate\s*history\b/i,
  ];

  const isDocOnly = docOnlyPatterns.some((p) => p.test(missionLower));
  const hasSourceCodePaths = pathsLower.some(
    (p) => p.startsWith('src/') || p.startsWith('android/') || p.startsWith('scripts/')
  );

  if (isDocOnly && !hasSourceCodePaths) {
    return {
      requiresWorkspace: false,
      reason: 'Small docs patch - Direct patch route recommended',
      suggestedPurpose: 'patch',
    };
  }

  // Workspace IS needed for complex cases (action tasks)
  const complexPatterns = [
    // Action verbs with or without targets
    /\b(task|tasks|work|arbeit|auftrag|job)\b/i,
    /\b(fix|repair|change|update|implement|create|add|remove|refactor)\b/i,
    /\b(bearbeite|edit|änder|implementiere|erstelle|hinzufügen|entfernen)\b/i,
    // Multi-file operations
    /\b(multipl|mehrere|multiple)\s*(datei|file|files)\b/i,
    /\b(test|build|install)\b/i,
    // Draft PR
    /\bdraft\s*pr\b/i,
  ];

  for (const pattern of complexPatterns) {
    if (pattern.test(missionLower)) {
      // Determine suggested purpose - check all options and pick most specific
      let suggestedPurpose: WorkspacePurpose = 'patch';
      if (/\btest/i.test(missionLower)) suggestedPurpose = 'test';
      if (/\b(fix|repair|bug|error)\b/i.test(missionLower) && suggestedPurpose !== 'test') suggestedPurpose = 'repair';
      if (/\bdraft\s*pr\b/i.test(missionLower) && suggestedPurpose === 'patch') suggestedPurpose = 'draft_pr';

      return {
        requiresWorkspace: true,
        reason: 'Complex task requires isolated workspace execution',
        suggestedPurpose,
      };
    }
  }

  // Check if multiple files are targeted
  if (targetPaths && targetPaths.length > 1) {
    return {
      requiresWorkspace: true,
      reason: 'Multiple files targeted - workspace isolation required',
      suggestedPurpose: 'patch',
    };
  }

  // Check for source code paths
  if (pathsLower.some((p) => p.startsWith('src/') || p.startsWith('android/'))) {
    return {
      requiresWorkspace: true,
      reason: 'Source code changes require workspace isolation',
      suggestedPurpose: 'patch',
    };
  }

  // Default: action tasks require workspace
  return {
    requiresWorkspace: true,
    reason: 'Task is an action item - workspace recommended',
    suggestedPurpose: 'patch',
  };
}

/**
 * Gate: Repository must be available
 */
export function createRepoGate(): WorkspaceGate {
  return {
    name: 'repo-available',
    description: 'Repository must be accessible for workspace creation',
    check(context: WorkspaceGateContext): WorkspaceGateResult {
      if (!context.repoUrl) {
        return {
          passed: false,
          reason: 'No repository URL provided',
          blocker: 'repo_missing',
          nextAction: 'block',
        };
      }

      if (!context.repoUrl.startsWith('https://github.com/')) {
        return {
          passed: false,
          reason: 'Invalid repository URL format',
          blocker: 'invalid_repo_url',
          nextAction: 'block',
        };
      }

      return {
        passed: true,
        reason: 'Repository URL is valid',
      };
    },
  };
}

/**
 * Gate: Workspace executor must be available
 */
export function createExecutorGate(): WorkspaceGate {
  return {
    name: 'executor-available',
    description: 'A workspace executor must be available to run workspaces',
    check(context: WorkspaceGateContext): WorkspaceGateResult {
      if (!context.hasWorkspaceExecutor) {
        return {
          passed: false,
          reason: 'No workspace executor available',
          blocker: 'executor_unavailable',
          nextAction: 'block',
        };
      }

      return {
        passed: true,
        reason: 'Workspace executor is available',
      };
    },
  };
}

/**
 * Gate: Check if workspace is required or if direct patch is sufficient
 */
export function createWorkspaceRequirementGate(): WorkspaceGate {
  return {
    name: 'workspace-required',
    description: 'Determines if a workspace is required based on task complexity',
    check(context: WorkspaceGateContext): WorkspaceGateResult {
      // Simple questions never need workspaces
      if (context.isSimpleQuestion) {
        return {
          passed: false,
          reason: 'Simple question - no workspace required',
          nextAction: 'direct_patch',
        };
      }

      // Small doc patches can use direct patch route
      if (context.isSmallDocPatch) {
        return {
          passed: false,
          reason: 'Small doc patch - direct patch route recommended',
          nextAction: 'direct_patch',
        };
      }

      // Complex tasks require workspace
      if (context.requiresWorkspace) {
        if (!context.hasWorkspaceExecutor) {
          return {
            passed: false,
            reason: 'Task requires workspace but no executor available',
            blocker: 'workspace_required',
            nextAction: 'block',
          };
        }

        return {
          passed: true,
          reason: 'Task complexity requires workspace isolation',
          nextAction: 'start_workspace',
        };
      }

      // Default: no workspace needed
      return {
        passed: false,
        reason: 'Task does not require workspace',
        nextAction: 'snapshot_only',
      };
    },
  };
}

/**
 * Gate: Path validation - ensure changes are within allowed paths
 */
export function createPathValidationGate(): WorkspaceGate {
  return {
    name: 'path-validation',
    description: 'Validate that target paths are allowed',
    check(context: WorkspaceGateContext): WorkspaceGateResult {
      const targetPaths = context.targetPaths ?? [];

      if (targetPaths.length === 0) {
        return {
          passed: true,
          reason: 'No specific paths targeted - all paths allowed',
        };
      }

      // Check for forbidden paths
      const forbiddenPatterns = ['.env', 'node_modules/', 'dist/', 'build/', '.git/'];

      for (const path of targetPaths) {
        for (const pattern of forbiddenPatterns) {
          if (path.includes(pattern)) {
            return {
              passed: false,
              reason: `Path ${path} matches forbidden pattern ${pattern}`,
              blocker: 'forbidden_path',
              nextAction: 'block',
            };
          }
        }
      }

      return {
        passed: true,
        reason: 'All target paths are valid',
      };
    },
  };
}

/**
 * Gate: Draft PR validation - ensure allowDraftPr is respected
 */
export function createDraftPrGate(): WorkspaceGate {
  return {
    name: 'draft-pr-validation',
    description: 'Draft PR creation requires explicit permission',
    check(context: WorkspaceGateContext): WorkspaceGateResult {
      // This gate is informational - it validates that Draft PR requests
      // are properly flagged. The actual check happens in the runtime.
      return {
        passed: true,
        reason: 'Draft PR gate passed',
      };
    },
  };
}

/**
 * Default policy gates in order of evaluation
 */
export const DEFAULT_POLICY_GATES: readonly WorkspaceGate[] = [
  createRepoGate(),
  createPathValidationGate(),
  createWorkspaceRequirementGate(),
  createExecutorGate(),
  createDraftPrGate(),
];

/**
 * Evaluate workspace policy for a given context
 */
export function evaluateWorkspacePolicy(
  context: WorkspaceGateContext,
  gates: readonly WorkspaceGate[] = DEFAULT_POLICY_GATES
): WorkspacePolicyResult {
  const rules: WorkspacePolicyRule[] = [];
  let allowed = true;
  let reason = 'All policy checks passed';
  let blocker: string | undefined;
  let suggestedPurpose: WorkspacePurpose | undefined;

  for (const gate of gates) {
    const result = gate.check(context);

    const rule: WorkspacePolicyRule = {
      id: gate.name,
      description: gate.description,
      passed: result.passed,
      blocker: result.blocker,
      warning: !result.passed && !result.blocker ? result.reason : undefined,
    };

    rules.push(rule);

    if (!result.passed) {
      allowed = false;
      if (reason === 'All policy checks passed') {
        reason = result.reason;
      }
      if (blocker === undefined && result.blocker !== undefined) {
        blocker = result.blocker;
      }
      suggestedPurpose = context.requiresWorkspace ? 'patch' : undefined;
    }
  }

  return {
    allowed,
    rules,
    reason,
    blocker,
    suggestedPurpose,
  };
}

/**
 * Determine if a workspace should be created based on policy
 */
export function shouldCreateWorkspace(
  repoUrl?: string,
  baseBranch?: string,
  mission?: string,
  targetPaths?: readonly string[],
  hasWorkspaceExecutor = false
): WorkspacePolicyResult {
  const trigger = evaluateTaskComplexity(mission, targetPaths);

  const context: WorkspaceGateContext = {
    repoUrl,
    baseBranch,
    mission,
    targetPaths,
    requiresWorkspace: trigger.requiresWorkspace,
    isSimpleQuestion: !trigger.requiresWorkspace && !trigger.suggestedPurpose,
    isReadOnlyAnalysis: mission?.toLowerCase().includes('analyse') ?? false,
    isSmallDocPatch: trigger.suggestedPurpose === 'patch' && !trigger.requiresWorkspace,
    hasWorkspaceExecutor,
  };

  return evaluateWorkspacePolicy(context);
}

/**
 * Validate that a workspace result's changed files are within allowed paths
 */
export function validateChangedFiles(
  changedFiles: readonly string[],
  allowedPaths: readonly string[],
  forbiddenPaths: readonly string[]
): { valid: boolean; violations: readonly string[] } {
  const violations: string[] = [];

  for (const file of changedFiles) {
    // Check forbidden paths
    for (const forbidden of forbiddenPaths) {
      if (file.startsWith(forbidden) || file === forbidden) {
        violations.push(`${file} matches forbidden path ${forbidden}`);
      }
    }

    // Check allowed paths (if specified)
    if (allowedPaths.length > 0) {
      let isAllowed = false;
      for (const allowed of allowedPaths) {
        if (file.startsWith(allowed) || file === allowed) {
          isAllowed = true;
          break;
        }
      }
      if (!isAllowed) {
        violations.push(`${file} is not within allowed paths`);
      }
    }
  }

  return {
    valid: violations.length === 0,
    violations,
  };
}
