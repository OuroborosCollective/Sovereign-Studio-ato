/**
 * Sovereign Capability Router
 *
 * Central routing decision for Sovereign Studio.
 * Determines which execution route is appropriate based on user input and runtime state.
 *
 * Product rules:
 * - Never build a UI that creates truth. Build a runtime that creates truth.
 * - No fake success, no percentage progress, no mocks in live paths.
 * - Missing patch/package is not a dead end; it creates the next runtime action.
 */

import type {
  CapabilityDecision,
  CapabilityRouterInput,
  IntentClassification,
  SovereignCapability,
  SovereignNextAction,
  SovereignRoute,
  SovereignRouteBlocker,
  TaskComplexity,
} from './sovereignCapabilityTypes';

export type { CapabilityRouterInput, CapabilityDecision } from './sovereignCapabilityTypes';

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

function hasExplicitExecutorIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return OPENHANDS_TOKENS.some((token) => lower.includes(token));
}

export function classifyIntent(text: string): IntentClassification {
  const trimmed = text.trim();
  const lower = trimmed.toLowerCase();

  if (/^https?:\/\/github\.com\/[\w-]+\/[\w.-]+(?:\/.*)?$/i.test(trimmed)) {
    return 'load_repo';
  }
  if (WORKFLOW_REPAIR_TOKENS.some((token) => lower.includes(token))) return 'repair_workflow';
  if (WORKFLOW_WATCH_TOKENS.some((token) => lower.includes(token))) return 'workflow_watch';
  if (DRAFT_PR_TOKENS.some((token) => lower.includes(token))) return 'draft_pr';
  if (STATUS_QUESTION_TOKENS.some((token) => lower.includes(token))) return 'status_question';

  const hasDirectPatchKeyword = DIRECT_PATCH_TOKENS.some((token) => lower.includes(token));
  const hasComplexKeyword = COMPLEX_TASK_TOKENS.some((token) => lower.includes(token));
  if (hasDirectPatchKeyword && !hasComplexKeyword) return 'direct_patch';

  if (OPENHANDS_TOKENS.some((token) => lower.includes(token))) return 'code_generation';
  if (CODE_GENERATION_TOKENS.some((token) => lower.includes(token))) return 'code_generation';
  if (LOAD_REPO_TOKENS.some((token) => lower.includes(token))) return 'load_repo';
  if (FREE_CHAT_TOKENS.some((token) => lower.includes(token))) return 'free_chat';
  return 'unknown';
}

export function determineTaskComplexity(
  intent: IntentClassification,
  text: string,
): TaskComplexity {
  const lower = text.toLowerCase();
  switch (intent) {
    case 'direct_patch':
    case 'free_chat':
    case 'status_question':
    case 'load_repo':
      return 'simple';
    case 'workflow_watch':
    case 'repair_workflow':
      return 'medium';
    case 'code_generation':
      return COMPLEX_TASK_TOKENS.some((token) => lower.includes(token)) ? 'complex' : 'medium';
    default:
      return 'unknown' as TaskComplexity;
  }
}

export function detectBlockers(input: CapabilityRouterInput): SovereignRouteBlocker[] {
  const blockers: SovereignRouteBlocker[] = [];
  if (!input.repoReady) blockers.push('repo_missing');

  if (input.githubAccessState === 'validating' || input.githubAccessState === 'requested') {
    blockers.push('github_access_validating');
  } else if (input.githubAccessState !== 'ready') {
    blockers.push('github_access_missing');
  }

  if (!input.openhandsReady && !input.directGitHubPatchReady && !input.workspaceReady) {
    blockers.push('executor_unavailable');
  }
  return blockers;
}

function determineNextAction(blocker?: SovereignRouteBlocker): SovereignNextAction {
  if (!blocker) return 'run_worker';
  switch (blocker) {
    case 'repo_missing':
      return 'load_repo';
    case 'github_access_missing':
    case 'github_access_validating':
      return 'validate_github_access';
    case 'package_required':
      return 'generate_patch_package';
    case 'executor_unavailable':
    case 'workspace_required':
      return 'start_workspace';
    case 'unsafe_action':
      return 'ask_user';
    default:
      return 'show_blocker';
  }
}

function buildReason(
  route: SovereignRoute,
  _capability: SovereignCapability,
  blocker?: SovereignRouteBlocker,
): string {
  const routeNames: Record<SovereignRoute, string> = {
    'worker-chat': 'Worker-Chat Route',
    'code-llm': 'Code-LLM Route',
    'direct-github-patch': 'Direct GitHub Patch Route',
    'workspace-executor': 'Workspace-Executor Route',
    openhands: 'OpenHands Executor Route',
    'draft-pr-runtime': 'Draft PR Runtime',
    'local-runtime-answer': 'Lokale Runtime-Antwort',
    'repo-load': 'Repo-Lade Route',
  };

  if (!blocker) return `Route gewählt: ${routeNames[route]}`;

  const blockerReasons: Record<SovereignRouteBlocker, string> = {
    repo_missing: 'Repository fehlt',
    github_access_missing: 'GitHub-Zugang fehlt',
    github_access_validating: 'GitHub-Zugang wird geprüft',
    executor_unavailable: 'Kein Executor verfügbar',
    workspace_required: 'Workspace-Executor benötigt',
    package_required: 'Patch-Paket/Diff muss zuerst erzeugt werden',
    unsupported_intent: 'Auftrag zu komplex für diese Route',
    unsafe_action: 'Aktion würde unsichere Pfade betreffen',
  };
  return `${routeNames[route]} blockiert: ${blockerReasons[blocker]}`;
}

function buildRecoverablePackageDecision(
  route: SovereignRoute,
  capability: SovereignCapability,
): CapabilityDecision {
  return {
    route,
    capability,
    allowed: true,
    reason: buildReason(route, capability, 'package_required'),
    blocker: 'package_required',
    nextAction: 'generate_patch_package',
  };
}

export function decideSovereignCapabilityRoute(input: CapabilityRouterInput): CapabilityDecision {
  const intent = classifyIntent(input.text);
  const complexity = determineTaskComplexity(intent, input.text);
  const blockers = detectBlockers(input);
  const explicitExecutorIntent = hasExplicitExecutorIntent(input.text);

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

  if (intent === 'free_chat') {
    return {
      route: 'worker-chat',
      capability: 'free_chat',
      allowed: true,
      reason: buildReason('worker-chat', 'free_chat'),
      nextAction: 'run_worker',
    };
  }

  if (intent === 'load_repo') {
    return {
      route: 'repo-load',
      capability: 'repo_read',
      allowed: true,
      reason: buildReason('repo-load', 'repo_read'),
      nextAction: 'load_repo',
    };
  }

  if (intent === 'workflow_watch') {
    const blocker = blockers.includes('github_access_missing')
      ? 'github_access_missing'
      : blockers.includes('github_access_validating')
        ? 'github_access_validating'
        : blockers.includes('executor_unavailable')
          ? 'executor_unavailable'
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

  if (intent === 'draft_pr') {
    if (!input.hasPackage) {
      return buildRecoverablePackageDecision('draft-pr-runtime', 'draft_pr');
    }
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
    return {
      route: 'draft-pr-runtime',
      capability: 'draft_pr',
      allowed: false,
      reason: buildReason('draft-pr-runtime', 'draft_pr', 'executor_unavailable'),
      blocker: 'executor_unavailable',
      nextAction: 'start_workspace',
    };
  }

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
    const route: SovereignRoute = input.workspaceReady ? 'workspace-executor' : 'openhands';
    const blocked = !input.workspaceReady && !input.openhandsReady;
    return {
      route,
      capability: 'code_patch_plan',
      allowed: !blocked,
      reason: buildReason(route, 'code_patch_plan', blocked ? 'executor_unavailable' : undefined),
      blocker: blocked ? 'executor_unavailable' : undefined,
      nextAction: blocked ? 'start_workspace' : input.openhandsReady ? 'start_openhands' : 'start_workspace',
    };
  }

  if (intent === 'direct_patch') {
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
    if (input.directGitHubPatchReady) {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: true,
        reason: buildReason('direct-github-patch', 'direct_github_patch'),
        nextAction: 'run_direct_patch',
      };
    }
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

  if (intent === 'code_generation') {
    if (explicitExecutorIntent && input.openhandsReady) {
      return {
        route: 'openhands',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('openhands', 'code_patch_plan'),
        nextAction: 'start_openhands',
      };
    }
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
    if (input.hasPackage) {
      return {
        route: 'code-llm',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('code-llm', 'code_patch_plan'),
        nextAction: 'run_worker',
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
    if (input.directGitHubPatchReady && complexity === 'simple') {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: true,
        reason: buildReason('direct-github-patch', 'direct_github_patch'),
        nextAction: 'run_direct_patch',
      };
    }
    return buildRecoverablePackageDecision('code-llm', 'code_patch_plan');
  }

  return {
    route: 'worker-chat',
    capability: 'free_chat',
    allowed: false,
    reason: 'Auftrag konnte nicht erkannt werden. Bitte konkretisieren.',
    blocker: 'unsupported_intent',
    nextAction: 'ask_user',
  };
}

export function buildCapabilityRouteActionEvent(
  decision: CapabilityDecision,
  _traceId: string,
  _index: number,
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

export function requiresGitHubAccess(decision: CapabilityDecision): boolean {
  const githubRoutes: SovereignRoute[] = [
    'direct-github-patch',
    'draft-pr-runtime',
    'openhands',
    'workspace-executor',
  ];
  return githubRoutes.includes(decision.route) && decision.allowed;
}

export function requiresExecutor(decision: CapabilityDecision): boolean {
  return decision.route === 'openhands' || decision.route === 'workspace-executor';
}

export function getRouteLabel(route: SovereignRoute): string {
  const labels: Record<SovereignRoute, string> = {
    'worker-chat': 'Chat Worker',
    'code-llm': 'Code-LLM',
    'direct-github-patch': 'Direct GitHub Patch',
    'workspace-executor': 'Workspace Executor',
    openhands: 'OpenHands',
    'draft-pr-runtime': 'Draft PR',
    'local-runtime-answer': 'Lokale Antwort',
    'repo-load': 'Repo laden',
  };
  return labels[route];
}

export function getBlockerExplanation(blocker: SovereignRouteBlocker): string {
  const explanations: Record<SovereignRouteBlocker, string> = {
    repo_missing: 'Lade zuerst ein GitHub Repository.',
    github_access_missing: 'Gib einen GitHub-Zugang ein.',
    github_access_validating: 'GitHub-Zugang wird gerade geprüft. Bitte warten.',
    executor_unavailable: 'Kein Executor verfügbar. OpenHands konfigurieren oder Workspace starten.',
    workspace_required: 'Diese Aufgabe braucht einen Workspace-Executor.',
    package_required: 'Erzeuge zuerst ein Patch-Paket oder eine Diff-Vorschau; danach kann der Draft PR erstellt werden.',
    unsupported_intent: 'Der Auftrag ist zu komplex für diese Route.',
    unsafe_action: 'Diese Aktion würde unsichere Pfade betreffen.',
  };
  return explanations[blocker];
}
