/**
 * Sovereign Capability Router
 *
 * Central routing decision for Sovereign Studio. This runtime decides which
 * execution route is allowed from current state; the UI may only display the
 * resulting decision.
 */

import type {
  CapabilityDecision,
  CapabilityRouterInput,
  IntentClassification,
  SovereignNextAction,
  SovereignRoute,
  SovereignRouteBlocker,
  TaskComplexity,
} from './sovereignCapabilityTypes';

export type { CapabilityDecision, CapabilityRouterInput } from './sovereignCapabilityTypes';

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
  'zum changelog', 'in changelog', 'zur history',
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

export function classifyIntent(text: string): IntentClassification {
  const clean = text.trim();
  const lower = clean.toLowerCase();

  if (/^https?:\/\/github\.com\/[\w-]+\/[\w.-]+(?:\/.*)?$/i.test(clean)) {
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
  if (input.githubAccessState === 'missing' || input.githubAccessState === 'invalid') {
    blockers.push('github_access_missing');
  }
  if (input.githubAccessState === 'validating') blockers.push('github_access_validating');
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
    case 'executor_unavailable':
    case 'workspace_required':
      return 'start_workspace';
    case 'unsafe_action':
      return 'ask_user';
    default:
      return 'show_blocker';
  }
}

function buildReason(route: SovereignRoute, blocker?: SovereignRouteBlocker): string {
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

export function decideSovereignCapabilityRoute(input: CapabilityRouterInput): CapabilityDecision {
  const intent = classifyIntent(input.text);
  const complexity = determineTaskComplexity(intent, input.text);
  const blockers = detectBlockers(input);

  if (intent === 'status_question') {
    return {
      route: 'local-runtime-answer',
      capability: 'free_chat',
      allowed: true,
      reason: buildReason('local-runtime-answer'),
      nextAction: 'show_blocker',
    };
  }

  if (intent === 'free_chat') {
    return {
      route: 'worker-chat',
      capability: 'free_chat',
      allowed: true,
      reason: buildReason('worker-chat'),
      nextAction: 'run_worker',
    };
  }

  if (intent === 'load_repo') {
    return {
      route: 'repo-load',
      capability: 'repo_read',
      allowed: true,
      reason: buildReason('repo-load'),
      nextAction: 'load_repo',
    };
  }

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
      reason: buildReason('worker-chat', blocker),
      blocker,
      nextAction: blocker ? determineNextAction(blocker) : 'run_worker',
    };
  }

  if (intent === 'draft_pr') {
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

    if (blockers.includes('github_access_missing')) {
      return {
        route: 'draft-pr-runtime',
        capability: 'draft_pr',
        allowed: false,
        reason: buildReason('draft-pr-runtime', 'github_access_missing'),
        blocker: 'github_access_missing',
        nextAction: 'validate_github_access',
      };
    }

    if (blockers.includes('github_access_validating')) {
      return {
        route: 'draft-pr-runtime',
        capability: 'draft_pr',
        allowed: false,
        reason: buildReason('draft-pr-runtime', 'github_access_validating'),
        blocker: 'github_access_validating',
        nextAction: 'show_blocker',
      };
    }

    if (input.openhandsReady) {
      return {
        route: 'openhands',
        capability: 'draft_pr',
        allowed: true,
        reason: buildReason('openhands'),
        nextAction: 'start_openhands',
      };
    }

    if (input.workspaceReady) {
      return {
        route: 'workspace-executor',
        capability: 'draft_pr',
        allowed: true,
        reason: buildReason('workspace-executor'),
        nextAction: 'start_workspace',
      };
    }

    return {
      route: 'draft-pr-runtime',
      capability: 'draft_pr',
      allowed: false,
      reason: buildReason('draft-pr-runtime', 'executor_unavailable'),
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

    const hasExecutor = input.workspaceReady || input.openhandsReady;
    return {
      route: input.workspaceReady ? 'workspace-executor' : 'openhands',
      capability: 'code_patch_plan',
      allowed: hasExecutor,
      reason: buildReason(
        input.workspaceReady ? 'workspace-executor' : 'openhands',
        hasExecutor ? undefined : 'executor_unavailable',
      ),
      blocker: hasExecutor ? undefined : 'executor_unavailable',
      nextAction: hasExecutor
        ? input.openhandsReady ? 'start_openhands' : 'start_workspace'
        : 'start_workspace',
    };
  }

  if (intent === 'direct_patch') {
    if (blockers.includes('github_access_missing')) {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: false,
        reason: buildReason('direct-github-patch', 'github_access_missing'),
        blocker: 'github_access_missing',
        nextAction: 'validate_github_access',
      };
    }

    if (blockers.includes('github_access_validating')) {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: false,
        reason: buildReason('direct-github-patch', 'github_access_validating'),
        blocker: 'github_access_validating',
        nextAction: 'show_blocker',
      };
    }

    if (input.directGitHubPatchReady) {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: true,
        reason: buildReason('direct-github-patch'),
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
      reason: buildReason('direct-github-patch', 'executor_unavailable'),
      blocker: 'executor_unavailable',
      nextAction: 'start_workspace',
    };
  }

  if (intent === 'code_generation') {
    if (complexity === 'complex') {
      if (input.workspaceReady) {
        return {
          route: 'workspace-executor',
          capability: 'isolated_workspace',
          allowed: true,
          reason: buildReason('workspace-executor'),
          nextAction: 'start_workspace',
        };
      }

      if (input.openhandsReady) {
        return {
          route: 'openhands',
          capability: 'code_patch_plan',
          allowed: true,
          reason: buildReason('openhands'),
          nextAction: 'start_openhands',
        };
      }

      return {
        route: 'workspace-executor',
        capability: 'isolated_workspace',
        allowed: false,
        reason: buildReason('workspace-executor', 'workspace_required'),
        blocker: 'workspace_required',
        nextAction: 'start_workspace',
      };
    }

    if (input.hasPackage) {
      return {
        route: 'code-llm',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('code-llm'),
        nextAction: 'run_worker',
      };
    }

    if (input.openhandsReady) {
      return {
        route: 'openhands',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('openhands'),
        nextAction: 'start_openhands',
      };
    }

    if (input.directGitHubPatchReady && complexity === 'simple') {
      return {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: true,
        reason: buildReason('direct-github-patch'),
        nextAction: 'run_direct_patch',
      };
    }

    return {
      route: 'openhands',
      capability: 'code_patch_plan',
      allowed: false,
      reason: buildReason('openhands', 'executor_unavailable'),
      blocker: 'executor_unavailable',
      nextAction: 'start_workspace',
    };
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
  traceId: string,
  index: number,
): { kind: 'route_selected' | 'capability_checked'; route: string; label: string; detail: string; state: 'running' | 'blocked' } {
  void traceId;
  void index;
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
  const executorRoutes: SovereignRoute[] = ['openhands', 'workspace-executor'];
  return executorRoutes.includes(decision.route);
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
    unsupported_intent: 'Der Auftrag ist zu komplex für diese Route.',
    unsafe_action: 'Diese Aktion würde unsichere Pfade betreffen.',
  };
  return explanations[blocker];
}
