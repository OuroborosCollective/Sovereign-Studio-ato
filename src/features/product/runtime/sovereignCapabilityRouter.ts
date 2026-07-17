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
import type {
  SovereignActionEventInput,
  SovereignActionRoute,
} from './sovereignActionStreamRuntime';

export type { CapabilityRouterInput, CapabilityDecision } from './sovereignCapabilityTypes';

const FREE_CHAT_TOKENS = [
  'was ist', 'wie funktioniert', 'erklär', 'was bedeutet', 'was ist das',
  'wie geht', 'was machst', 'was kannst', 'wieso', 'weshalb', 'warum',
  'what is', 'how does', 'explain', 'what does', 'what are', 'how do',
];

const GREETING_PATTERN = /^(?:hallo|hi|hello|guten tag|good morning)(?:[!,.]?\s|[!,.]?$)/i;

const READ_ONLY_REQUEST_PATTERN =
  /^(?:(?:can|could|would)\s+you\s+(?:show|tell|explain|describe|summarize|inspect|read|list)\b|(?:show|tell|explain|describe|summarize|inspect|read|list)\b|(?:kannst|könntest)\s+du\s+(?:(?:mir|uns)\s+)?(?:zeig|sag|erklär|beschreib|fass|lies|list)|(?:zeig|sag|erklär|beschreib|fass|lies|list))/i;

const ENGLISH_MUTATION_PATTERN =
  /\b(?:add|apply|build|change|create|delete|deploy|edit|fix|implement|merge|modify|patch|publish|refactor|remove|repair|replace|update|write)\b/i;

const GERMAN_MUTATION_STEMS = [
  'füg', 'hinzufüg', 'bau', 'änder', 'aktualisier', 'erstell', 'lösch',
  'implementier', 'veröffentlich', 'refaktor', 'entfern', 'reparier',
  'beheb', 'ersetz', 'schreib', 'mach',
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

/**
 * Simple-override tokens: when present they signal the user expects a lightweight
 * change even if the text also contains complex-task keywords.
 * Example: "einfachen Test fürs Backend" → complex tokens present ("test", "backend")
 * but "einfachen" overrides → medium instead of complex.
 */
const SIMPLE_MODIFIER_TOKENS = [
  'einfach', 'einfachen', 'einfache', 'einfaches', 'einfacher',
  'klein', 'kleine', 'kleinen', 'kleines', 'kleiner',
  'schnell', 'kurz', 'kurze', 'nur', 'just', 'quick', 'simple', 'small', 'minor',
  'nur ein', 'nur eine', 'only', 'single', 'one',
];

const SOVEREIGN_AGENT_TOKENS = [
  'sovereign agent',
  'sovereign-agent',
];

const WORKFLOW_WATCH_TOKENS = [
  'watch workflow', 'workflow status', 'ci status', 'github actions',
  'beobachte workflow', 'workflow überwachen', 'ci status prüfen',
  'läuft der workflow', 'workflow ergebnis', 'workflow-status',
];

const WORKFLOW_REPAIR_TOKENS = [
  'fix workflow', 'ci fix', 'workflow reparieren', 'behebe workflow',
  'workflowfehler beheben', 'ci fehler', 'workflowfehler', 'reparatur',
];

function hasExplicitMutationIntent(lower: string): boolean {
  return ENGLISH_MUTATION_PATTERN.test(lower)
    || GERMAN_MUTATION_STEMS.some((stem) => lower.includes(stem));
}

function isReadOnlyRequest(trimmed: string, lower: string): boolean {
  if (READ_ONLY_REQUEST_PATTERN.test(trimmed)) return true;
  return /\?\s*$/.test(trimmed) && !hasExplicitMutationIntent(lower);
}

/** Offline/degraded-only language fallback. Never call from an online route. */
export function classifyOfflineCapabilityIntent(text: string): IntentClassification {
  const trimmed = text.trim();
  const lower = trimmed.toLowerCase();

  if (/^https?:\/\/github\.com\/[\w-]+\/[\w.-]+(?:\/.*)?$/i.test(trimmed)) {
    return 'load_repo';
  }
  if (STATUS_QUESTION_TOKENS.some((token) => lower.includes(token))) return 'status_question';
  if (
    GREETING_PATTERN.test(trimmed)
    || FREE_CHAT_TOKENS.some((token) => lower.includes(token))
  ) return 'free_chat';
  if (WORKFLOW_WATCH_TOKENS.some((token) => lower.includes(token))) return 'workflow_watch';
  if (isReadOnlyRequest(trimmed, lower)) return 'free_chat';
  if (WORKFLOW_REPAIR_TOKENS.some((token) => lower.includes(token))) return 'repair_workflow';
  if (DRAFT_PR_TOKENS.some((token) => lower.includes(token))) return 'draft_pr';

  const hasDirectPatchKeyword = DIRECT_PATCH_TOKENS.some((token) => lower.includes(token));
  const hasComplexKeyword = COMPLEX_TASK_TOKENS.some((token) => lower.includes(token));
  if (hasDirectPatchKeyword && !hasComplexKeyword) return 'direct_patch';

  if (SOVEREIGN_AGENT_TOKENS.some((token) => lower.includes(token))) return 'code_generation';
  if (CODE_GENERATION_TOKENS.some((token) => lower.includes(token))) return 'code_generation';
  if (LOAD_REPO_TOKENS.some((token) => lower.includes(token))) return 'load_repo';
  return 'unknown';
}

/** Offline/degraded-only complexity fallback. Online complexity comes from LLM evidence. */
export function determineOfflineTaskComplexity(
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
    case 'code_generation': {
      const hasComplexKeyword = COMPLEX_TASK_TOKENS.some((token) => lower.includes(token));
      if (!hasComplexKeyword) return 'medium';
      // Mixed-signal resolution: if user signals "simple/quick/small" alongside
      // complex-task keywords, honour the intent modifier and route as medium.
      const hasSimpleModifier = SIMPLE_MODIFIER_TOKENS.some((token) => lower.includes(token));
      return hasSimpleModifier ? 'medium' : 'complex';
    }
    default:
      return 'unknown';
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

  if (!input.directGitHubPatchReady && !input.workspaceReady && !input.agentReady) {
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
    'sovereign-agent': 'Sovereign Agent Executor Route',
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

function buildRepoMissingDecision(intent: IntentClassification): CapabilityDecision {
  const route: SovereignRoute = intent === 'direct_patch'
    ? 'direct-github-patch'
    : intent === 'draft_pr'
      ? 'draft-pr-runtime'
      : intent === 'workflow_watch'
        ? 'worker-chat'
        : 'workspace-executor';
  const capability: SovereignCapability = intent === 'direct_patch'
    ? 'direct_github_patch'
    : intent === 'draft_pr'
      ? 'draft_pr'
      : intent === 'workflow_watch'
        ? 'workflow_watch'
        : 'code_patch_plan';

  return {
    route,
    capability,
    allowed: false,
    reason: buildReason(route, capability, 'repo_missing'),
    blocker: 'repo_missing',
    nextAction: 'load_repo',
  };
}

export function buildOfflineCapabilityLanguageEvidence(text: string): CapabilityRouterInput['language'] {
  const intent = classifyOfflineCapabilityIntent(text);
  return {
    intent,
    complexity: determineOfflineTaskComplexity(intent, text),
    explicitAgentRequest: SOVEREIGN_AGENT_TOKENS.some((token) => text.toLowerCase().includes(token)),
    source: 'offline_fallback',
  };
}

/**
 * Build language evidence from a verified online LLM interpretation.
 * Use this instead of buildOfflineCapabilityLanguageEvidence when the online
 * interpreter has already returned a structured intent — the source is then
 * 'online_llm', not 'offline_fallback'.
 */
export function buildOnlineCapabilityLanguageEvidence(
  onlineIntent: IntentClassification,
  complexity: TaskComplexity,
  explicitAgentRequest: boolean,
): CapabilityRouterInput['language'] {
  return {
    intent: onlineIntent,
    complexity,
    explicitAgentRequest,
    source: 'online_llm',
  };
}

export function decideSovereignCapabilityRoute(input: CapabilityRouterInput): CapabilityDecision {
  const intent = input.language.intent;
  const complexity = input.language.complexity;
  const blockers = detectBlockers(input);
  const explicitSovereignAgentIntent = input.language.explicitAgentRequest;

  if (intent === 'status_question') {
    return {
      route: 'local-runtime-answer',
      capability: 'free_chat',
      allowed: true,
      reason: buildReason('local-runtime-answer', 'free_chat'),
      nextAction: 'answer_locally',
      isTerminal: true,
    };
  }

  if (intent === 'free_chat') {
    // Worker-health check: active blocker means the worker cannot process requests.
    // Returning allowed:false here surfaces the blocker card instead of silently spinning.
    if (input.hasActiveWorkerBlocker) {
      return {
        route: 'worker-chat',
        capability: 'free_chat',
        allowed: false,
        reason: 'Worker ist blockiert. Eingabe kann nicht verarbeitet werden. Bitte Blocker beheben.',
        blocker: 'executor_unavailable',
        nextAction: 'show_blocker',
      };
    }
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

  if (intent !== 'unknown' && blockers.includes('repo_missing')) {
    return buildRepoMissingDecision(intent);
  }

  if (intent === 'workflow_watch') {
    const blocker = blockers.includes('github_access_missing')
      ? 'github_access_missing'
      : blockers.includes('github_access_validating')
        ? 'github_access_validating'
        : input.hasActiveWorkerBlocker
          ? 'executor_unavailable'
          : undefined;
    return {
      route: 'worker-chat',
      capability: 'workflow_watch',
      allowed: !blocker,
      reason: input.hasActiveWorkerBlocker && blocker === 'executor_unavailable'
        ? 'Worker ist blockiert. Workflow-Status kann nicht abgefragt werden.'
        : buildReason('worker-chat', 'workflow_watch', blocker),
      blocker,
      nextAction: input.hasActiveWorkerBlocker && blocker === 'executor_unavailable'
        ? 'show_blocker'
        : blocker
          ? determineNextAction(blocker)
          : 'run_worker',
    };
  }

  if (intent === 'draft_pr') {
    // Sovereign Agent is only used when explicitly requested by the user,
    // after repository and GitHub write access are proven.
    if (explicitSovereignAgentIntent && input.agentReady) {
      if (blockers.includes('github_access_missing')) {
        return {
          route: 'sovereign-agent',
          capability: 'draft_pr',
          allowed: false,
          reason: buildReason('sovereign-agent', 'draft_pr', 'github_access_missing'),
          blocker: 'github_access_missing',
          nextAction: 'validate_github_access',
        };
      }
      if (blockers.includes('github_access_validating')) {
        return {
          route: 'sovereign-agent',
          capability: 'draft_pr',
          allowed: false,
          reason: buildReason('sovereign-agent', 'draft_pr', 'github_access_validating'),
          blocker: 'github_access_validating',
          nextAction: 'show_blocker',
        };
      }
      return {
        route: 'sovereign-agent',
        capability: 'draft_pr',
        allowed: true,
        reason: 'Sovereign Agent wurde ausdrücklich angefordert; Repository und GitHub-Zugang sind validiert.',
        nextAction: 'start_agent',
      };
    }
    // Default: route through Sovereign draft-pr-runtime
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
    // Sovereign Agent only when explicitly requested and GitHub access is proven.
    if (explicitSovereignAgentIntent && input.agentReady) {
      if (blockers.includes('github_access_missing')) {
        return {
          route: 'sovereign-agent',
          capability: 'code_patch_plan',
          allowed: false,
          reason: buildReason('sovereign-agent', 'code_patch_plan', 'github_access_missing'),
          blocker: 'github_access_missing',
          nextAction: 'validate_github_access',
        };
      }
      if (blockers.includes('github_access_validating')) {
        return {
          route: 'sovereign-agent',
          capability: 'code_patch_plan',
          allowed: false,
          reason: buildReason('sovereign-agent', 'code_patch_plan', 'github_access_validating'),
          blocker: 'github_access_validating',
          nextAction: 'show_blocker',
        };
      }
      return {
        route: 'sovereign-agent',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('sovereign-agent', 'code_patch_plan'),
        nextAction: 'start_agent',
      };
    }
    // Default: Sovereign workspace-executor
    if (input.workspaceReady) {
      return {
        route: 'workspace-executor',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('workspace-executor', 'code_patch_plan'),
        nextAction: 'start_workspace',
      };
    }
    return {
      route: 'workspace-executor',
      capability: 'isolated_workspace',
      allowed: false,
      reason: buildReason('workspace-executor', 'code_patch_plan', 'workspace_required'),
      blocker: 'workspace_required',
      nextAction: 'start_workspace',
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
    if (explicitSovereignAgentIntent && input.agentReady) {
      if (blockers.includes('github_access_validating')) {
        return {
          route: 'sovereign-agent',
          capability: 'code_patch_plan',
          allowed: false,
          reason: buildReason('sovereign-agent', 'code_patch_plan', 'github_access_validating'),
          blocker: 'github_access_validating',
          nextAction: 'show_blocker',
        };
      }
      if (blockers.includes('github_access_missing')) {
        return {
          route: 'sovereign-agent',
          capability: 'code_patch_plan',
          allowed: false,
          reason: buildReason('sovereign-agent', 'code_patch_plan', 'github_access_missing'),
          blocker: 'github_access_missing',
          nextAction: 'validate_github_access',
        };
      }
      return {
        route: 'sovereign-agent',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('sovereign-agent', 'code_patch_plan'),
        nextAction: 'start_agent',
      };
    }
    if (blockers.includes('github_access_validating')) {
      return {
        route: 'workspace-executor',
        capability: 'code_patch_plan',
        allowed: false,
        reason: buildReason('workspace-executor', 'code_patch_plan', 'github_access_validating'),
        blocker: 'github_access_validating',
        nextAction: 'show_blocker',
      };
    }
    if (blockers.includes('github_access_missing')) {
      return {
        route: 'workspace-executor',
        capability: 'code_patch_plan',
        allowed: false,
        reason: buildReason('workspace-executor', 'code_patch_plan', 'github_access_missing'),
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
      return {
        route: 'workspace-executor',
        capability: 'isolated_workspace',
        allowed: false,
        reason: buildReason('workspace-executor', 'isolated_workspace', 'workspace_required'),
        blocker: 'workspace_required',
        nextAction: 'start_workspace',
      };
    }
    if (input.directGitHubPatchReady && complexity === 'simple') {
      return {
        route: 'direct-github-patch',
        capability: 'code_patch_plan',
        allowed: true,
        reason: buildReason('direct-github-patch', 'code_patch_plan'),
        nextAction: 'run_direct_patch',
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
    return buildRecoverablePackageDecision('code-llm', 'code_patch_plan');
  }

  // Unknown intent: if worker is already blocked, surface that — not a silent "ask_user".
  return {
    route: 'worker-chat',
    capability: 'free_chat',
    allowed: false,
    reason: input.hasActiveWorkerBlocker
      ? 'Worker ist blockiert. Auftrag kann nicht verarbeitet werden. Bitte Blocker beheben.'
      : 'Auftrag konnte nicht erkannt werden. Bitte konkretisieren.',
    blocker: input.hasActiveWorkerBlocker ? 'executor_unavailable' : 'unsupported_intent',
    nextAction: input.hasActiveWorkerBlocker ? 'show_blocker' : 'ask_user',
  };
}

export function mapCapabilityRouteToActionRoute(route: SovereignRoute): SovereignActionRoute {
  switch (route) {
    case 'worker-chat':
      return 'worker';
    case 'code-llm':
      return 'code-llm';
    case 'direct-github-patch':
      return 'direct-github-patch';
    case 'workspace-executor':
      return 'agent-workspace';
    case 'sovereign-agent':
      return 'sovereign-agent';
    case 'draft-pr-runtime':
      return 'github-patch';
    case 'local-runtime-answer':
      return 'runtime';
    case 'repo-load':
      return 'repo';
  }
}

export function buildCapabilityRouteActionEvent(
  decision: CapabilityDecision,
  _traceId: string,
  _index: number,
): SovereignActionEventInput {
  const route = mapCapabilityRouteToActionRoute(decision.route);
  if (decision.isTerminal) {
    const isLocalAnswer = decision.route === 'local-runtime-answer' && decision.nextAction === 'answer_locally';
    return {
      kind: isLocalAnswer ? 'capability_checked' : 'route_selected',
      route,
      label: isLocalAnswer ? 'Lokale Runtime-Antwort vorbereitet' : 'Route gewählt',
      detail: decision.reason,
      state: 'done',
    };
  }
  const recoverableNextActionPending = Boolean(decision.allowed && decision.blocker);
  return {
    kind: 'route_selected',
    route,
    label: recoverableNextActionPending ? 'Nächste Route eingeplant' : 'Route gewählt',
    detail: decision.reason,
    state: recoverableNextActionPending
      ? 'queued'
      : decision.allowed
        ? 'running'
        : 'blocked',
  };
}

export function requiresGitHubAccess(decision: CapabilityDecision): boolean {
  const githubRoutes: SovereignRoute[] = [
    'direct-github-patch',
    'draft-pr-runtime',
    'sovereign-agent',
    'workspace-executor',
  ];
  return githubRoutes.includes(decision.route)
    && decision.allowed
    && !decision.blocker;
}

export function requiresExecutor(decision: CapabilityDecision): boolean {
  return decision.route === 'sovereign-agent' || decision.route === 'workspace-executor';
}

export function getRouteLabel(route: SovereignRoute): string {
  const labels: Record<SovereignRoute, string> = {
    'worker-chat': 'Chat Worker',
    'code-llm': 'Code-LLM',
    'direct-github-patch': 'Direct GitHub Patch',
    'workspace-executor': 'Workspace Executor',
    'sovereign-agent': 'Sovereign Agent',
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
    executor_unavailable: 'Kein Executor verfügbar. Sovereign Agent konfigurieren oder Workspace starten.',
    workspace_required: 'Diese Aufgabe braucht einen Workspace-Executor.',
    package_required: 'Erzeuge zuerst ein Patch-Paket oder eine Diff-Vorschau; danach kann der Draft PR erstellt werden.',
    unsupported_intent: 'Der Auftrag ist zu komplex für diese Route.',
    unsafe_action: 'Diese Aktion würde unsichere Pfade betreffen.',
  };
  return explanations[blocker];
}
