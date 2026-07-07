import type { SovereignActionEventInput, SovereignActionRoute } from './sovereignActionStreamRuntime';

export type RouteFailoverTaskKind = 'analysis' | 'small_patch' | 'complex_patch' | 'draft_pr' | 'status';
export type RouteFailoverDecisionKind = 'route' | 'blocked' | 'local_status';

export interface RouteFailoverInput {
  readonly taskKind: RouteFailoverTaskKind;
  readonly workerAvailable: boolean;
  readonly githubWriteReady: boolean;
  readonly openhandsReady: boolean;
  readonly directPatchAvailable: boolean;
  readonly activeBlocker?: string | null;
}

export interface RouteFailoverDecision {
  readonly kind: RouteFailoverDecisionKind;
  readonly route: SovereignActionRoute;
  readonly allowed: boolean;
  readonly reason: string;
  readonly nextAction: string;
  readonly event: SovereignActionEventInput;
}

function eventFor(decision: Omit<RouteFailoverDecision, 'event'>): SovereignActionEventInput {
  return {
    kind: decision.kind === 'blocked' ? 'blocked' : 'route_selected',
    route: decision.route,
    label: decision.kind === 'blocked' ? 'Route blockiert' : `Route gewählt: ${decision.route}`,
    detail: `${decision.reason} Nächste Aktion: ${decision.nextAction}`,
    state: decision.kind === 'blocked' ? 'blocked' : decision.kind === 'local_status' ? 'done' : 'running',
  };
}

function decision(input: Omit<RouteFailoverDecision, 'event'>): RouteFailoverDecision {
  return { ...input, event: eventFor(input) };
}

export function decideRouteFailover(input: RouteFailoverInput): RouteFailoverDecision {
  if (input.taskKind === 'status') {
    return decision({
      kind: 'local_status',
      route: 'runtime',
      allowed: true,
      reason: input.activeBlocker ? `Lokaler Status aus aktivem Blocker: ${input.activeBlocker}.` : 'Lokaler Status kann aus Runtime-State beantwortet werden.',
      nextAction: 'Status im Chat beantworten; keinen Worker/Executor starten.',
    });
  }

  if (input.taskKind === 'analysis') {
    if (input.workerAvailable) {
      return decision({
        kind: 'route',
        route: 'worker',
        allowed: true,
        reason: 'Analyseauftrag ohne Schreibabsicht nutzt Worker/LLM-Route.',
        nextAction: 'Worker anfragen und Ergebnis als Beratung markieren.',
      });
    }
    return decision({
      kind: 'blocked',
      route: 'worker',
      allowed: false,
      reason: 'Worker/LLM-Route ist nicht verfügbar.',
      nextAction: 'Worker-Health prüfen oder lokal aus Runtime-State antworten.',
    });
  }

  if ((input.taskKind === 'small_patch' || input.taskKind === 'draft_pr' || input.taskKind === 'complex_patch') && !input.githubWriteReady) {
    return decision({
      kind: 'blocked',
      route: 'github-access',
      allowed: false,
      reason: 'Schreibroute braucht validierten GitHub-Schreibzugang.',
      nextAction: 'GitHubAccessCard öffnen und echte API-Prüfung ausführen.',
    });
  }

  if (input.taskKind === 'small_patch') {
    if (input.directPatchAvailable) {
      return decision({
        kind: 'route',
        route: 'direct-github-patch',
        allowed: true,
        reason: 'Kleiner README/docs-Patch kann über Direct GitHub Patch laufen.',
        nextAction: 'Patch planen, Diff anzeigen und erst danach Draft PR/Apply erlauben.',
      });
    }
    if (input.openhandsReady) {
      return decision({
        kind: 'route',
        route: 'openhands',
        allowed: true,
        reason: 'Direct Patch ist nicht verfügbar; OpenHands ist bereit.',
        nextAction: 'Isolierten Executor-Job starten.',
      });
    }
    return decision({
      kind: 'blocked',
      route: 'github-patch',
      allowed: false,
      reason: 'Weder Direct Patch noch OpenHands ist verfügbar.',
      nextAction: 'Direct-Patch-Voraussetzungen oder OpenHands-Konfiguration prüfen.',
    });
  }

  if (input.openhandsReady) {
    return decision({
      kind: 'route',
      route: 'openhands',
      allowed: true,
      reason: `${input.taskKind === 'draft_pr' ? 'Draft-PR' : 'Komplexer Patch'} braucht Executor-Route.`,
      nextAction: 'OpenHands/Workspace-Executor starten; Ergebnis bleibt Draft PR.',
    });
  }

  return decision({
    kind: 'blocked',
    route: 'openhands',
    allowed: false,
    reason: 'Executor-Route ist nicht bereit.',
    nextAction: 'OpenHands/Workspace-Health prüfen oder Auftrag verkleinern.',
  });
}
