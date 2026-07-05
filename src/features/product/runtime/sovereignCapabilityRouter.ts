/**
 * Sovereign Capability Router
 *
 * Central routing decision for Sovereign Studio.
 * Determines which execution route is appropriate based on user input and runtime state.
 *
 * Issue #502: Runtime: add Sovereign Capability Router for chat, patch, workspace and Draft PR routes
 *
 * Product rules:
 * - Never build a UI that creates truth. Build a runtime that creates truth.
 * - No fake success, no percentage progress, no mocks in live paths.
 * - OpenHands is one possible executor, not the only coding route.
 * - Simple README/docs changes can use Direct Patch.
 * - Large code work can use Workspace/OpenHands.
 * - Chat questions stay fast without starting a full workspace.
 * - UI shows decision; it does not create it.
 */

import type {
  CapabilityDecision,
  CapabilityRouterInput,
  IntentClassification,
  SovereignRoute,
  SovereignCapability,
  SovereignRouteBlocker,
  SovereignNextAction,
  TaskComplexity,
} from './sovereignCapabilityTypes';

// Re-export types for consumers
export type { CapabilityRouterInput, CapabilityDecision } from './sovereignCapabilityTypes';

// ─────────────────────────────────────────────────────────────
// INTENT DETECTION TOKENS
// ─────────────────────────────────────────────────────────────

const FREE_CHAT_TOKENS = [
  'was ist', 'wie funktioniert', 'erklär', 'was bedeutet', 'was ist das',
  'wie geht', 'was machst', 'was kannst', 'wieso', 'weshalb', 'warum',
  'what is', 'how does', 'explain', 'what does', 'what are', 'how do',
  'hallo', 'hi', 'hello', 'guten tag', 'good morning',
];

const STATUS_QUESTION_TOKENS = [
  'arbeitet er schon', 'läuft das', 'läuft er', 'was macht er',
  'sehe nichts', 'status?', 'ist er fertig', 'hat er angefangen',
  'warum passiert nichts', 'macht er was', 'tut er was', 'ist er gestartet',
  'passiert etwas', 'passiert gerade', 'fertig?', 'complete?',
  'was ist der status', 'bist du fertig',
];

const LOAD_REPO_TOKENS = [
  'load repo', 'lade repository', 'repo laden', 'github repository öffnen',
  'welches repository', 'repo auswählen', 'fetch repository', 'open repo',
  'select repository', 'repo url', 'github link',
];

const DIRECT_PATCH_TOKENS = [
  'readme', 'dokumentation', 'docs', 'changelog', 'history', 'titel',
  'title', 'überschrift', 'heading', 'inhalt', 'content',
  'füge hinzu', 'hinzufügen', 'add', 'ergänze', 'änder', 'aktualisier',
  'changelog', 'zum changelog', 'in changelog', 'history', 'zur history',
];

const DRAFT_PR_TOKENS = [
  'draft pr', 'pull request', 'pr erstellen', 'pull request erstellen',
  'draft pr erstellen', 'erstelle pull request', 'veröffentliche änderungen',
  'pr raus', 'mach den pr', 'pr machen', 'draft pull request',
];

const COMPLEX_TASK_TOKENS = [
  'implementier', 'baue', 'bauen', 'komponent', 'function', 'funktio',
  'test', 'teste', 'refaktor', 'api', 'server', 'backend', 'frontend',
  'database', 'datenbank', 'security', 'sicherheit', 'workflow',
  'docker', 'kubernetes', 'deployment',
];

const CODE_GENERATION_TOKENS = [
  'baue', 'bauen', 'implementiere', 'implementieren', 'fixe', 'repariere',
  'patch', 'ändere datei', 'datei ändern', 'feature einbauen',
  'schreibe code', 'code schreiben',
];

const OPENHANDS_TOKENS = [
  'openhands', 'draft pr', 'draft-pr', 'pull request', 'pr erstellen',
  'push', 'commit', 'repo schreiben', 'github schreiben', 'branch erstellen',
];

const WORKFLOW_WATCH_TOKENS = [
  'watch workflow', 'workflow status', 'ci status', 'github actions',
  'beobachte', 'workflow', 'workflows', 'überwach',
  'beobachte workflow', 'workflow überwachen', 'ci status prüfen',
  'läuft der workflow', 'workflow ergebnis', 'workflow-status',
];

const WORKFLOW_REPAIR_TOKENS = [
  'fix workflow', 'ci fix', 'workflow reparieren', 'behebe workflow',
  'workflowfehler beheben', 'ci fehler', 'workflowfehler', 'reparatur',
];

// ─────────────────────────────────────────────────────────────
// INTENT CLASSIFICATION
// ─────────────────────────────────────────────────────────────

/**
 * Classify user intent from text input.
 * Order matters: more specific intents first.
 */
export function classifyIntent(text: string): IntentClassification {
  const lower = text.toLowerCase();

  // Check for GitHub URL first (most specific)
  if (/^https?:\/\/github\.com\/[\w-]+\/[\w.-]+(?:\/.*)?$/i.test(text.trim())) {
    return 'load_repo';
  }

  // Workflow-specific intents (check before free chat to avoid conflicts)
  if (WORKFLOW_REPAIR_TOKENS.some((token) => lower.includes(token))) {
    return 'repair_workflow';
  }
  if (WORKFLOW_WATCH_TOKENS.some((token) => lower.includes(token))) {
    return 'workflow_watch';
  }

  // Draft PR
  if (DRAFT_PR_TOKENS.some((token) => lower.includes(token))) {
    return 'draft_pr';
  }

  // Status questions - local runtime answer
  if (STATUS_QUESTION_TOKENS.some((token) => lower.includes(token))) {
    return 'status_question';
  }

  // Direct patch (simple README/docs changes) - check before free_chat
  const hasDirectPatchKeyword = DIRECT_PATCH_TOKENS.some((token) => lower.includes(token));
  const hasComplexKeyword = COMPLEX_TASK_TOKENS.some((token) => lower.includes(token));
  if (hasDirectPatchKeyword && !hasComplexKeyword) {
    return 'direct_patch';
  }

  // OpenHands/Executor explicitly requested
  if (OPENHANDS_TOKENS.some((token) => lower.includes(token))) {
    return 'code_generation';
  }

  // Code generation
  if (CODE_GENERATION_TOKENS.some((token) => lower.includes(token))) {
    return 'code_generation';
  }

  // Load repo signals
  if (LOAD_REPO_TOKENS.some((token) => lower.includes(token))) {
    return 'load_repo';
  }

  // Free chat - no code/repo actions (least specific)
  if (FREE_CHAT_TOKENS.some((token) => lower.includes(token))) {
    return 'free_chat';
  }

  return 'unknown';
}

/**
 * Determine task complexity from intent and text.
 */
export function determineTaskComplexity(
  intent: IntentClassification,
  text: string,
): TaskComplexity {
  const lower = text.toLowerCase();

  switch (intent) {
    case 'direct_patch':
      return 'simple';
    case 'free_chat':
    case 'status_question':
    case 'load_repo':
      return 'simple';
    case 'workflow_watch':
    case 'repair_workflow':
      return 'medium';
    case 'code_generation':
      // Check for explicit large work keywords
      if (COMPLEX_TASK_TOKENS.some((token) => lower.includes(token))) {
        return 'complex';
      }
      return 'medium';
    default:
      return 'unknown' as TaskComplexity;
  }
}

// ─────────────────────────────────────────────────────────────
// BLOCKER DETECTION
// ─────────────────────────────────────────────────────────────

/**
 * Check what blockers exist based on runtime state.
 * Only "ready" allows write actions.
 * "requested" and "validating" get github_access_validating blocker.
 * "missing" and "invalid" get github_access_missing blocker.
 */
export function detectBlockers(input: CapabilityRouterInput): SovereignRouteBlocker[] {
  const blockers: SovereignRouteBlocker[] = [];

  if (!input.repoReady) {
    blockers.push('repo_missing');
  }

  // Only "ready" allows write actions
  if (input.githubAccessState === 'ready') {
    // GitHub is ready - no blocker from GitHub
  } else if (input.githubAccessState === 'validating' || input.githubAccessState === 'requested') {
    // Both validating and requested block write actions
    blockers.push('github_access_validating');
  } else {
    // missing or invalid
    blockers.push('github_access_missing');
  }

  if (!input.openhandsReady && !input.directGitHubPatchReady && !input.workspaceReady) {
    blockers.push('executor_unavailable');
  }

  return blockers;
}

// ─────────────────────────────────────────────────────────────
// ROUTE DECISION
// ─────────────────────────────────────────────────────────────

/**
 * Determine next action based on blockers and capability.
 */
function determineNextAction(
  blocker?: SovereignRouteBlocker,
  capability?: SovereignCapability,
): SovereignNextAction {
  if (!blocker) {
    return 'run_worker';
  }

  switch (blocker) {
    case 'repo_missing':
      return 'load_repo';
    case 'github_access_missing':
    case 'github_access_validating':
      return 'validate_github_access';
    case 'executor_unavailable':
      return 'start_workspace';
    case 'workspace_required':
      return 'start_workspace';
    case 'unsafe_action':
      return 'ask_user';
    default:
      return 'show_blocker';
  }
}

/**
 * Build route reason message.
 */
function buildReason(
  route: SovereignRoute,
  capability: SovereignCapability,
  blocker?: SovereignRouteBlocker,
): string {
  const routeNames: Record<SovereignRoute, string> = {
    'worker-chat': 'Worker-Chat Route',
    'code-llm': 'Code-LLM Route',
    'direct-github-patch': 'Direct GitHub Patch Route',
    'workspace-executor': 'Workspace-Executor Route',
    'openhands': 'OpenHands Executor Route',
    'draft-pr-runtime': 'Draft PR Runtime',
    'local-runtime-answer': 'Lokale Runtime-Antwort',
    'repo-load': 'Repo-Lade Route',
  };

  if (blocker) {
    const blockerReasons: Record<SovereignRouteBlocker, string> = {
      repo_missing: 'Repository fehlt',
      github_access_missing: 'GitHub-Zugang fehlt',
      github_access_validating: 'GitHub-Zugang wird geprüft',
      executor_unavailable: 'Kein Executor verfügbar',
      workspace_required: 'Workspace-Executor benötigt',
      unsupported_intent: 'Auftrag zu komplex für diese Route',
      unsafe_action: 'Aktion würde unsichere Pfade betreffen',
    };
    return `${routeNames[route]} blockiert: ${blockerReasons[blocker]}`;
  }

  return `Route gewählt: ${routeNames[route]}`;
}

/**
 * Map intent to capability.
 */
function intentToCapability(intent: IntentClassification): SovereignCapability {
  switch (intent) {
    case 'free_chat':
      return 'free_chat';
    case 'status_question':
      return 'free_chat';
    case 'load_repo':
      return 'repo_read';
    case 'direct_patch':
      return 'direct_github_patch';
    case 'code_generation':
      return 'code_patch_plan';
    case 'draft_pr':
      return 'draft_pr';
    case 'workflow_watch':
      return 'workflow_watch';
    case 'repair_workflow':
      return 'code_patch_plan';
    default:
      return 'free_chat';
  }
}

/**
 * Core routing decision based on intent and runtime state.
 *
 * This is the central function that BuilderContainer.tsx should call
 * instead of making routing decisions internally.
 */
export function decideSovereignCapabilityRoute(
  input: CapabilityRouterInput,
): CapabilityDecision {
  const intent = classifyIntent(input.text);
  const complexity = determineTaskComplexity(intent, input.text);
  const blockers = detectBlockers(input);

  // ─── STATUS QUESTION: Local runtime answer ───
  if (intent === 'status_question') {
    return {
      route: 'local-runtime-answer',
      capability: 'free_chat',
      allowed: true,
      reason: buildReason('local-runtime-answer', 'free_chat'),
      nextAction: 'show_blocker',
      isTerminal: true,
    };
  }

  // ─── FREE CHAT: Worker chat route ───
  if (intent === 'free_chat') {
    return {
      route: 'worker-chat',
      capability: 'free_chat',
      allowed: true,
      reason: buildReason('worker-chat', 'free_chat'),
      nextAction: 'run_worker',
    };
  }

  // ─── LOAD REPO: Repo load route ───
  if (intent === 'load_repo') {
    return {
      route: 'repo-load',
      capability: 'repo_read',
      allowed: true,
      reason: buildReason('repo-load', 'repo_read'),
      nextAction: 'load_repo',
    };
  }

  // ─── WORKFLOW WATCH ───
  if (intent === 'workflow_watch') {
    const blocker = blockers.includes('github_access_missing')
      ? 'github_access_missing' as SovereignRouteBlocker
      : blockers.includes('github_access_validating')
        ? 'github_access_validating' as SovereignRouteBlocker
        : blockers.includes('executor_unavailable')
          ? 'executor_unavailable' as SovereignRouteBlocker
          : undefined;

    return {
      route: 'worker-chat',
      capability: 'workflow_watch',
      allowed: !blocker,
      reason: buildReason('worker-chat', 'workflow_watch', blocker),
      blocker,
      nextAction: blocker ? determineNextAction(blocker) : 'run_worker',
    };
  }

  // ─── DRAFT PR ───
  if (intent === 'draft_pr') {
    // Check GitHub access blockers first - these always block Draft PR
    if (blockers.includes('github_access_missing')) {
      return {
        route: 'draft-pr-runtime',
        capability: 'draft_pr',
        allowed: false,
        reason: buildReason('draft-pr-runtime', 'draft_pr', 'github_access_missing'),
        blocker: 'github_access_missing',
        nextAction: 'validate_github_access',
      };
    }

    if (blockers.includes('github_access_validating')) {
      return {
        route: 'draft-pr-runtime',
        capability: 'draft_pr',
        allowed: false,
        reason: buildReason('draft-pr-runtime', 'draft_pr', 'github_access_validating'),
        blocker: 'github_access_validating',
        nextAction: 'show_blocker',
      };
    }

    // Check executor readiness - if available, allow Draft PR (executor will generate package if needed)
    if (input.openhandsReady) {
      return {
        route: 'openhands',
        capability: 'draft_pr',
        allowed: true,
        reason: buildReason('openhands', 'draft_pr'),
        nextAction: 'start_openhands',
      };
    }

    if (input.workspaceReady) {
      return {
        route: 'workspace-executor',
        capability: 'draft_pr',
        allowed: true,
        reason: buildReason('workspace-executor', 'draft_pr'),
        nextAction: 'start_workspace',
      };
    }

    // No executor available - block with appropriate message
    if (!input.hasPackage) {
      return {
        route: 'draft-pr-runtime',
        capability: 'draft_pr',
        allowed: false,
        reason: 'Paket muss zuerst generiert werden.',
        blocker: 'unsupported_intent',
        nextAction: 'ask_user',
      };
    }

    return {
      route: 'draft-pr-runtime',
      capability: 'draft_pr',
      allowed: false,
      reason: buildReason('draft-pr-runtime', 'draft_pr', 'executor_unavailable'),
      blocker: 'executor_unavailable',
      nextAction: 'start_workspace',
    };
  }

  // ─── REPAIR WORKFLOW ───
  if (intent === 'repair_workflow') {
    if (!input.hasWorkflowReport) {
      return {
        route: 'worker-chat',
        capability: 'workflow_watch',
        allowed: false,
        reason: 'Workflow-Fehlerbericht erforderlich für Repair.',
        blocker: 'executor_unavailable',
        nextAction: 'show_blocker',
      };
    }

    return {
      route: 'workspace-executor',
      capability: 'code_patch_plan',
      allowed: input.workspaceReady || input.openhandsReady,
      reason: buildReason(
        input.workspaceReady ? 'workspace-executor' : 'openhands',
        'code_patch_plan',
        !input.workspaceReady && !input.openhandsReady ? 'executor_unavailable' : undefined,
      ),
      blocker: !input.workspaceReady && !input.openhandsReady ? 'executor_unavailable' : undefined,
      nextAction: !input.workspaceReady && !input.openhandsReady
        ? 'start_workspace'
        : input.openhandsReady ? 'start_openhands' : 'start_workspace',
    };
  }

  // ─── DIRECT PATCH (simple README/docs changes) ───
  if (intent === 'direct_patch') {
    // GitHub access is required
    if (blockers.includes('github_access_missing')) {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: false,
        reason: buildReason('direct-github-patch', 'direct_github_patch', 'github_access_missing'),
        blocker: 'github_access_missing',
        nextAction: 'validate_github_access',
      };
    }

    if (blockers.includes('github_access_validating')) {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: false,
        reason: buildReason('direct-github-patch', 'direct_github_patch', 'github_access_validating'),
        blocker: 'github_access_validating',
        nextAction: 'show_blocker',
      };
    }

    // Direct patch available
    if (input.directGitHubPatchReady) {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: true,
        reason: buildReason('direct-github-patch', 'direct_github_patch'),
        nextAction: 'run_direct_patch',
      };
    }

    // Fall back to OpenHands if direct patch not ready
    if (input.openhandsReady) {
      return {
        route: 'openhands',
        capability: 'direct_github_patch',
        allowed: true,
        reason: 'Direct Patch nicht bereit. OpenHands für kleine Änderungen.',
        nextAction: 'start_openhands',
      };
    }

    return {
      route: 'direct-github-patch',
      capability: 'direct_github_patch',
      allowed: false,
      reason: buildReason('direct-github-patch', 'direct_github_patch', 'executor_unavailable'),
      blocker: 'executor_unavailable',
      nextAction: 'start_workspace',
    };
  }

  // ─── CODE GENERATION ───
  if (intent === 'code_generation') {
    // Check GitHub access first - write actions require GitHub
    if (blockers.includes('github_access_validating')) {
      return {
        route: 'openhands',
        capability: 'code_patch_plan',
        allowed: false,
        reason: buildReason('openhands', 'code_patch_plan', 'github_access_validating'),
        blocker: 'github_access_validating',
        nextAction: 'show_blocker',
      };
    }

    if (blockers.includes('github_access_missing')) {
      return {
        route: 'openhands',
        capability: 'code_patch_plan',
        allowed: false,
        reason: buildReason('openhands', 'code_patch_plan', 'github_access_missing'),
        blocker: 'github_access_missing',
        nextAction: 'validate_github_access',
      };
    }

    // Complex work requires workspace
    if (complexity === 'complex') {
      if (input.workspaceReady) {
        return {
          route: 'workspace-executor',
          capability: 'isolated_workspace',
          allowed: true,
          reason: buildReason('workspace-executor', 'isolated_workspace'),
          nextAction: 'start_workspace',
        };
      }

      if (input.openhandsReady) {
        return {
          route: 'openhands',
          capability: 'code_patch_plan',
          allowed: true,
          reason: buildReason('openhands', 'code_patch_plan'),
          nextAction: 'start_openhands',
        };
      }

      return {
        route: 'workspace-executor',
        capability: 'isolated_workspace',
        allowed: false,
        reason: buildReason('workspace-executor', 'isolated_workspace', 'workspace_required'),
        blocker: 'workspace_required',
        nextAction: 'start_workspace',
      };
    }

    // Medium complexity can use code-llm or OpenHands
    if (input.hasPackage) {
      return {
        route: 'code-llm',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('code-llm', 'code_patch_plan'),
        nextAction: 'run_worker',
      };
    }

    // No package yet - use OpenHands if available
    if (input.openhandsReady) {
      return {
        route: 'openhands',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('openhands', 'code_patch_plan'),
        nextAction: 'start_openhands',
      };
    }

    // Check if Direct Patch is appropriate
    if (input.directGitHubPatchReady && complexity === 'simple') {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: true,
        reason: buildReason('direct-github-patch', 'direct_github_patch'),
        nextAction: 'run_direct_patch',
      };
    }

    return {
      route: 'openhands',
      capability: 'code_patch_plan',
      allowed: false,
      reason: buildReason('openhands', 'code_patch_plan', 'executor_unavailable'),
      blocker: 'executor_unavailable',
      nextAction: 'start_workspace',
    };
  }

  // ─── UNKNOWN INTENT ───
  return {
    route: 'worker-chat',
    capability: 'free_chat',
    allowed: false,
    reason: 'Auftrag konnte nicht erkannt werden. Bitte konkretisieren.',
    blocker: 'unsupported_intent',
    nextAction: 'ask_user',
  };
}

// ─────────────────────────────────────────────────────────────
// ACTION EVENT CREATION
// ─────────────────────────────────────────────────────────────

/**
 * Build an action event for the Sovereign Action Stream.
 * Every decision must produce an ActionEvent.
 * Returns a plain object compatible with SovereignActionEventInput.
 * 
 * Terminal decisions (isTerminal=true, local-runtime-answer) get state "done".
 * Blocked decisions get state "blocked".
 * Running decisions get state "running".
 */
export function buildCapabilityRouteActionEvent(
  decision: CapabilityDecision,
  traceId: string,
  index: number,
): { kind: 'route_selected' | 'capability_checked'; route: string; label: string; detail: string; state: 'running' | 'blocked' | 'done' } {
  if (decision.isTerminal) {
    return {
      kind: 'route_selected',
      route: decision.route,
      label: 'Route gewählt',
      detail: decision.reason,
      state: 'done',
    };
  }
  return {
    kind: 'route_selected',
    route: decision.route,
    label: 'Route gewählt',
    detail: decision.reason,
    state: decision.allowed ? 'running' : 'blocked',
  };
}

// ─────────────────────────────────────────────────────────────
// HELPER FUNCTIONS
// ─────────────────────────────────────────────────────────────

/**
 * Check if a decision requires GitHub access.
 */
export function requiresGitHubAccess(decision: CapabilityDecision): boolean {
  const githubRoutes: SovereignRoute[] = [
    'direct-github-patch',
    'draft-pr-runtime',
    'openhands',
    'workspace-executor',
  ];
  return githubRoutes.includes(decision.route) && decision.allowed;
}

/**
 * Check if a decision requires an executor.
 */
export function requiresExecutor(decision: CapabilityDecision): boolean {
  const executorRoutes: SovereignRoute[] = [
    'openhands',
    'workspace-executor',
  ];
  return executorRoutes.includes(decision.route);
}

/**
 * Get user-facing label for a route.
 */
export function getRouteLabel(route: SovereignRoute): string {
  const labels: Record<SovereignRoute, string> = {
    'worker-chat': 'Chat Worker',
    'code-llm': 'Code-LLM',
    'direct-github-patch': 'Direct GitHub Patch',
    'workspace-executor': 'Workspace Executor',
    'openhands': 'OpenHands',
    'draft-pr-runtime': 'Draft PR',
    'local-runtime-answer': 'Lokale Antwort',
    'repo-load': 'Repo laden',
  };
  return labels[route];
}

/**
 * Get blocker explanation in plain language.
 */
export function getBlockerExplanation(blocker: SovereignRouteBlocker): string {
  const explanations: Record<SovereignRouteBlocker, string> = {
    repo_missing: 'Lade zuerst ein GitHub Repository.',
    github_access_missing: 'Gib einen GitHub-Zugang ein.',
    github_access_validating: 'GitHub-Zugang wird gerade geprüft. Bitte warten.',
    executor_unavailable: 'Kein Executor verfügbar. OpenHands konfigurieren oder Workspace starten.',
    workspace_required: 'Diese Aufgabe braucht einen Workspace-Executor.',
    unsupported_intent: 'Der Auftrag ist zu komplex für diese Route.',
    unsafe_action: 'Diese Aktion würde unsichere Pfade betreffen.',
  };
  return explanations[blocker];
}
