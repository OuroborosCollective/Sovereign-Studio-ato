import type {
  CapabilityDecision,
  SovereignNextAction,
  SovereignRouteBlocker,
} from './sovereignCapabilityTypes';
import type {
  SovereignActionEvent,
  SovereignActionEventInput,
  SovereignActionRoute,
  SovereignActionStreamState,
} from './sovereignActionStreamRuntime';

export type PredictiveActionSignal = 'none' | 'weak' | 'learned' | 'runtime_contract';
export type PredictiveSurface =
  | 'router'
  | 'action_stream'
  | 'menu'
  | 'inspector'
  | 'github_access'
  | 'worker'
  | 'executor'
  | 'draft_pr'
  | 'repo'
  | 'toolchain'
  | 'runtime';

export interface PredictiveActionObservation {
  readonly blocker: SovereignRouteBlocker;
  readonly predictedAction: SovereignNextAction;
  readonly actualAction: SovereignNextAction;
  readonly succeeded: boolean;
  readonly reason: string;
  readonly observedAt: number;
  readonly surface?: PredictiveSurface;
}

export interface PredictiveActionPattern {
  readonly blocker: SovereignRouteBlocker;
  readonly action: SovereignNextAction;
  readonly hits: number;
  readonly misses: number;
  readonly lastObservedAt: number | null;
  readonly surfaces: readonly PredictiveSurface[];
}

export interface PredictiveNerveNode {
  readonly surface: PredictiveSurface;
  readonly active: boolean;
  readonly lastAction: SovereignNextAction | null;
  readonly lastBlocker: SovereignRouteBlocker | null;
  readonly lastObservedAt: number | null;
}

export interface PredictiveActionState {
  readonly patterns: readonly PredictiveActionPattern[];
  readonly observations: readonly PredictiveActionObservation[];
  readonly nerve: readonly PredictiveNerveNode[];
}

export interface PredictiveActionDecision {
  readonly action: SovereignNextAction;
  readonly signal: PredictiveActionSignal;
  readonly confidence: 'none' | 'low' | 'medium' | 'high';
  readonly reason: string;
  readonly learnedFrom: number;
  readonly surfaces: readonly PredictiveSurface[];
}

export interface PredictiveMenuSuggestion {
  readonly id: string;
  readonly label: string;
  readonly detail: string;
  readonly action: SovereignNextAction;
  readonly surface: PredictiveSurface;
  readonly priority: 'low' | 'medium' | 'high';
}

export interface PredictiveInspectorSignal {
  readonly id: string;
  readonly label: string;
  readonly detail: string;
  readonly prompt: string;
  readonly lamp: 'green' | 'yellow' | 'red';
  readonly surface: PredictiveSurface;
}

const MAX_OBSERVATIONS = 80;

const SURFACES: readonly PredictiveSurface[] = [
  'router',
  'action_stream',
  'menu',
  'inspector',
  'github_access',
  'worker',
  'executor',
  'draft_pr',
  'repo',
  'toolchain',
  'runtime',
];

const CONTRACT_PATTERNS: readonly PredictiveActionPattern[] = [
  {
    blocker: 'package_required',
    action: 'generate_patch_package',
    hits: 1,
    misses: 0,
    lastObservedAt: null,
    surfaces: ['router', 'action_stream', 'menu', 'inspector', 'draft_pr', 'runtime'],
  },
  {
    blocker: 'github_access_missing',
    action: 'validate_github_access',
    hits: 1,
    misses: 0,
    lastObservedAt: null,
    surfaces: ['router', 'github_access', 'menu', 'inspector', 'runtime'],
  },
  {
    blocker: 'github_access_validating',
    action: 'show_blocker',
    hits: 1,
    misses: 0,
    lastObservedAt: null,
    surfaces: ['router', 'github_access', 'action_stream', 'runtime'],
  },
  {
    blocker: 'repo_missing',
    action: 'load_repo',
    hits: 1,
    misses: 0,
    lastObservedAt: null,
    surfaces: ['router', 'repo', 'menu', 'inspector', 'runtime'],
  },
  {
    blocker: 'executor_unavailable',
    action: 'start_workspace',
    hits: 1,
    misses: 0,
    lastObservedAt: null,
    surfaces: ['router', 'executor', 'menu', 'inspector', 'runtime'],
  },
  {
    blocker: 'workspace_required',
    action: 'start_workspace',
    hits: 1,
    misses: 0,
    lastObservedAt: null,
    surfaces: ['router', 'executor', 'menu', 'inspector', 'runtime'],
  },
];

function createNerve(): readonly PredictiveNerveNode[] {
  return SURFACES.map((surface) => ({
    surface,
    active: false,
    lastAction: null,
    lastBlocker: null,
    lastObservedAt: null,
  }));
}

export function createPredictiveActionState(): PredictiveActionState {
  return {
    patterns: CONTRACT_PATTERNS,
    observations: [],
    nerve: createNerve(),
  };
}

function uniqueSurfaces(values: readonly PredictiveSurface[]): readonly PredictiveSurface[] {
  return Array.from(new Set(values));
}

function findPattern(
  patterns: readonly PredictiveActionPattern[],
  blocker: SovereignRouteBlocker,
  action: SovereignNextAction,
): PredictiveActionPattern | null {
  return patterns.find((pattern) => pattern.blocker === blocker && pattern.action === action) ?? null;
}

function confidenceFrom(pattern: PredictiveActionPattern | null): PredictiveActionDecision['confidence'] {
  if (!pattern) return 'none';
  const total = pattern.hits + pattern.misses;
  if (pattern.blocker === 'package_required' && pattern.action === 'generate_patch_package') return 'high';
  if (total >= 5 && pattern.hits >= pattern.misses * 2) return 'high';
  if (total >= 2 && pattern.hits >= pattern.misses) return 'medium';
  return 'low';
}

function signalFrom(pattern: PredictiveActionPattern | null): PredictiveActionSignal {
  if (!pattern) return 'none';
  const contract = CONTRACT_PATTERNS.some(
    (entry) => entry.blocker === pattern.blocker && entry.action === pattern.action,
  );
  if (contract) return 'runtime_contract';
  return pattern.hits > pattern.misses ? 'learned' : 'weak';
}

function reasonFor(pattern: PredictiveActionPattern): string {
  switch (pattern.blocker) {
    case 'package_required':
      return 'Draft PR oder Code-Erstellung benötigt zuerst ein Patch-Paket/Diff. Nächster Runtime-Schritt ist Paket erzeugen.';
    case 'github_access_missing':
      return 'Schreib- oder Repo-Aktion braucht zuerst validierten GitHub-Zugang.';
    case 'github_access_validating':
      return 'GitHub-Zugang wird bereits geprüft; Runtime wartet auf echte API-Validierung.';
    case 'repo_missing':
      return 'Ohne geladenes Repository darf kein Patch-/Draft-PR-Pfad starten.';
    case 'executor_unavailable':
    case 'workspace_required':
      return 'Die Aufgabe benötigt einen ausführbaren Workspace-/Executor-Pfad.';
    default:
      return `Gelernter Übergang für Blocker ${pattern.blocker}.`;
  }
}

export function predictNextRuntimeAction(
  decision: CapabilityDecision,
  state: PredictiveActionState = createPredictiveActionState(),
): PredictiveActionDecision {
  if (!decision.blocker) {
    return {
      action: decision.nextAction,
      signal: 'none',
      confidence: 'none',
      reason: 'Keine Blockade vorhanden; Runtime folgt der aktuellen Router-Entscheidung.',
      learnedFrom: 0,
      surfaces: ['router'],
    };
  }

  const exact = findPattern(state.patterns, decision.blocker, decision.nextAction);
  if (exact) {
    return {
      action: exact.action,
      signal: signalFrom(exact),
      confidence: confidenceFrom(exact),
      reason: reasonFor(exact),
      learnedFrom: exact.hits,
      surfaces: exact.surfaces,
    };
  }

  const candidate = state.patterns
    .filter((pattern) => pattern.blocker === decision.blocker)
    .sort((a, b) => (b.hits - b.misses) - (a.hits - a.misses))[0];

  if (candidate) {
    return {
      action: candidate.action,
      signal: signalFrom(candidate),
      confidence: confidenceFrom(candidate),
      reason: reasonFor(candidate),
      learnedFrom: candidate.hits,
      surfaces: candidate.surfaces,
    };
  }

  return {
    action: decision.nextAction,
    signal: 'weak',
    confidence: 'low',
    reason: 'Keine gelernte Alternative vorhanden; Runtime folgt der Router-Entscheidung.',
    learnedFrom: 0,
    surfaces: ['router'],
  };
}

function updateNerve(
  nerve: readonly PredictiveNerveNode[],
  observation: PredictiveActionObservation,
): readonly PredictiveNerveNode[] {
  const surfaces: readonly PredictiveSurface[] = observation.surface ? [observation.surface] : ['runtime'];
  return nerve.map((node) => {
    if (!surfaces.includes(node.surface)) return node;
    return {
      surface: node.surface,
      active: true,
      lastAction: observation.actualAction,
      lastBlocker: observation.blocker,
      lastObservedAt: observation.observedAt,
    };
  });
}

export function recordPredictiveActionOutcome(
  state: PredictiveActionState,
  observation: Omit<PredictiveActionObservation, 'observedAt'> & { readonly observedAt?: number },
): PredictiveActionState {
  const observedAt = observation.observedAt ?? Date.now();
  const nextObservation: PredictiveActionObservation = { ...observation, observedAt };
  const patterns = [...state.patterns];
  const existingIndex = patterns.findIndex(
    (pattern) => pattern.blocker === observation.blocker && pattern.action === observation.predictedAction,
  );
  const hit = observation.succeeded && observation.actualAction === observation.predictedAction;

  if (existingIndex >= 0) {
    const existing = patterns[existingIndex];
    patterns[existingIndex] = {
      ...existing,
      hits: existing.hits + (hit ? 1 : 0),
      misses: existing.misses + (hit ? 0 : 1),
      lastObservedAt: observedAt,
      surfaces: uniqueSurfaces([
        ...existing.surfaces,
        observation.surface ?? 'runtime',
      ]),
    };
  } else {
    patterns.push({
      blocker: observation.blocker,
      action: observation.predictedAction,
      hits: hit ? 1 : 0,
      misses: hit ? 0 : 1,
      lastObservedAt: observedAt,
      surfaces: [observation.surface ?? 'runtime'],
    });
  }

  return {
    patterns,
    observations: [...state.observations, nextObservation].slice(-MAX_OBSERVATIONS),
    nerve: updateNerve(state.nerve, nextObservation),
  };
}

export function derivePredictiveActionEvent(
  decision: PredictiveActionDecision,
  route: SovereignActionRoute = 'runtime',
): SovereignActionEventInput | null {
  if (decision.signal === 'none') return null;
  return {
    kind: 'blocked',
    route,
    label: 'Predictive Runtime empfiehlt nächste Aktion',
    detail: buildPredictiveActionSummary(decision),
    state: 'blocked',
  };
}

function blockerFromActionEvent(event: SovereignActionEvent): SovereignRouteBlocker | null {
  const detail = `${event.label}\n${event.detail ?? ''}`.toLowerCase();
  if (detail.includes('patch-paket') || detail.includes('paket muss') || detail.includes('package')) return 'package_required';
  if (detail.includes('github-zugang fehlt') || detail.includes('github-schreibzugang erforderlich')) return 'github_access_missing';
  if (detail.includes('github-zugang wird geprüft')) return 'github_access_validating';
  if (detail.includes('repo fehlt') || detail.includes('kein repo')) return 'repo_missing';
  if (detail.includes('workspace') && detail.includes('benötigt')) return 'workspace_required';
  if (detail.includes('executor') && detail.includes('nicht')) return 'executor_unavailable';
  return null;
}

function nextActionForBlocker(blocker: SovereignRouteBlocker): SovereignNextAction {
  switch (blocker) {
    case 'package_required':
      return 'generate_patch_package';
    case 'github_access_missing':
      return 'validate_github_access';
    case 'github_access_validating':
      return 'show_blocker';
    case 'repo_missing':
      return 'load_repo';
    case 'workspace_required':
    case 'executor_unavailable':
      return 'start_workspace';
    case 'unsafe_action':
      return 'ask_user';
    default:
      return 'show_blocker';
  }
}

export function learnFromActionStream(
  state: PredictiveActionState,
  stream: SovereignActionStreamState,
): PredictiveActionState {
  return stream.events.reduce((current, event) => {
    if (event.state !== 'blocked' && event.state !== 'failed') return current;
    const blocker = blockerFromActionEvent(event);
    if (!blocker) return current;
    const action = nextActionForBlocker(blocker);
    return recordPredictiveActionOutcome(current, {
      blocker,
      predictedAction: action,
      actualAction: action,
      succeeded: event.state === 'blocked',
      reason: event.detail ?? event.label,
      observedAt: event.createdAt,
      surface: 'action_stream',
    });
  }, state);
}

export function derivePredictiveMenuSuggestions(
  decision: PredictiveActionDecision,
): readonly PredictiveMenuSuggestion[] {
  if (decision.signal === 'none') return [];
  const priority = decision.confidence === 'high' ? 'high' : decision.confidence === 'medium' ? 'medium' : 'low';
  return decision.surfaces.map((surface) => ({
    id: `predictive-${surface}-${decision.action}`,
    label: labelForAction(decision.action),
    detail: decision.reason,
    action: decision.action,
    surface,
    priority,
  }));
}

function labelForAction(action: SovereignNextAction): string {
  switch (action) {
    case 'generate_patch_package':
      return 'Patch/Diff erzeugen';
    case 'validate_github_access':
      return 'GitHub-Zugang prüfen';
    case 'load_repo':
      return 'Repo laden';
    case 'start_workspace':
      return 'Workspace starten';
    case 'start_openhands':
      return 'OpenHands starten';
    case 'run_direct_patch':
      return 'Direct Patch ausführen';
    case 'create_draft_pr':
      return 'Draft PR erstellen';
    case 'run_worker':
      return 'Worker starten';
    default:
      return 'Blocker anzeigen';
  }
}

export function derivePredictiveInspectorSignals(
  state: PredictiveActionState,
  decision?: PredictiveActionDecision | null,
): readonly PredictiveInspectorSignal[] {
  const activeNodes = state.nerve.filter((node) => node.active);
  const signals: PredictiveInspectorSignal[] = [];

  if (decision && decision.signal !== 'none') {
    signals.push({
      id: `predictive-next-${decision.action}`,
      label: 'Predictive Runtime',
      detail: `${labelForAction(decision.action)} · ${decision.confidence}`,
      prompt: buildPredictiveActionSummary(decision),
      lamp: decision.confidence === 'high' ? 'green' : 'yellow',
      surface: 'inspector',
    });
  }

  if (activeNodes.length > 0) {
    signals.push({
      id: 'predictive-nerve-active',
      label: 'Predictive Nervensystem',
      detail: `${activeNodes.length} aktive Oberfläche(n): ${activeNodes.map((node) => node.surface).join(' · ')}`,
      prompt: 'Zeige mir die aktiven Predictive-Runtime-Knoten und ihre letzten Aktionen.',
      lamp: 'green',
      surface: 'inspector',
    });
  }

  if (signals.length === 0) {
    signals.push({
      id: 'predictive-idle',
      label: 'Predictive Runtime',
      detail: 'Noch keine aktiven Lernsignale.',
      prompt: 'Zeige mir, welche Runtime-Übergänge Predictive Learning aktuell kennt.',
      lamp: 'yellow',
      surface: 'inspector',
    });
  }

  return signals;
}

export function buildPredictiveActionSummary(decision: PredictiveActionDecision): string {
  if (decision.signal === 'none') return 'Keine Vorhersage nötig.';
  return `${decision.reason} Nächste Aktion: ${decision.action}. Sicherheit: ${decision.confidence}. Oberflächen: ${decision.surfaces.join(' · ')}.`;
}
