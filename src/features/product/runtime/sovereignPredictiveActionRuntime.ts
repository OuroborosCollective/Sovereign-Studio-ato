import type {
  CapabilityDecision,
  SovereignNextAction,
  SovereignRouteBlocker,
} from './sovereignCapabilityTypes';

export type PredictiveActionSignal = 'none' | 'weak' | 'learned' | 'runtime_contract';

export interface PredictiveActionObservation {
  readonly blocker: SovereignRouteBlocker;
  readonly predictedAction: SovereignNextAction;
  readonly actualAction: SovereignNextAction;
  readonly succeeded: boolean;
  readonly reason: string;
  readonly observedAt: number;
}

export interface PredictiveActionPattern {
  readonly blocker: SovereignRouteBlocker;
  readonly action: SovereignNextAction;
  readonly hits: number;
  readonly misses: number;
  readonly lastObservedAt: number | null;
}

export interface PredictiveActionState {
  readonly patterns: readonly PredictiveActionPattern[];
  readonly observations: readonly PredictiveActionObservation[];
}

export interface PredictiveActionDecision {
  readonly action: SovereignNextAction;
  readonly signal: PredictiveActionSignal;
  readonly confidence: 'none' | 'low' | 'medium' | 'high';
  readonly reason: string;
  readonly learnedFrom: number;
}

const MAX_OBSERVATIONS = 50;

const CONTRACT_PATTERNS: readonly PredictiveActionPattern[] = [
  {
    blocker: 'package_required',
    action: 'generate_patch_package',
    hits: 1,
    misses: 0,
    lastObservedAt: null,
  },
];

export function createPredictiveActionState(): PredictiveActionState {
  return {
    patterns: CONTRACT_PATTERNS,
    observations: [],
  };
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
  if (pattern.blocker === 'package_required' && pattern.action === 'generate_patch_package') {
    return 'runtime_contract';
  }
  return pattern.hits > pattern.misses ? 'learned' : 'weak';
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
    };
  }

  const exact = findPattern(state.patterns, decision.blocker, decision.nextAction);
  if (exact) {
    return {
      action: exact.action,
      signal: signalFrom(exact),
      confidence: confidenceFrom(exact),
      reason: exact.blocker === 'package_required'
        ? 'Draft PR oder Code-Erstellung benötigt zuerst ein Patch-Paket/Diff. Nächster Runtime-Schritt ist Paket erzeugen.'
        : `Gelernter Übergang für Blocker ${exact.blocker}.`,
      learnedFrom: exact.hits,
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
      reason: `Aus aktiven Lernbeobachtungen abgeleiteter nächster Schritt für Blocker ${candidate.blocker}.`,
      learnedFrom: candidate.hits,
    };
  }

  return {
    action: decision.nextAction,
    signal: 'weak',
    confidence: 'low',
    reason: 'Keine gelernte Alternative vorhanden; Runtime folgt der Router-Entscheidung.',
    learnedFrom: 0,
  };
}

export function recordPredictiveActionOutcome(
  state: PredictiveActionState,
  observation: Omit<PredictiveActionObservation, 'observedAt'> & { readonly observedAt?: number },
): PredictiveActionState {
  const observedAt = observation.observedAt ?? Date.now();
  const nextObservation: PredictiveActionObservation = {
    ...observation,
    observedAt,
  };

  const patterns = [...state.patterns];
  const existingIndex = patterns.findIndex(
    (pattern) => pattern.blocker === observation.blocker && pattern.action === observation.predictedAction,
  );

  if (existingIndex >= 0) {
    const existing = patterns[existingIndex];
    patterns[existingIndex] = {
      ...existing,
      hits: existing.hits + (observation.succeeded && observation.actualAction === observation.predictedAction ? 1 : 0),
      misses: existing.misses + (!observation.succeeded || observation.actualAction !== observation.predictedAction ? 1 : 0),
      lastObservedAt: observedAt,
    };
  } else {
    patterns.push({
      blocker: observation.blocker,
      action: observation.predictedAction,
      hits: observation.succeeded && observation.actualAction === observation.predictedAction ? 1 : 0,
      misses: !observation.succeeded || observation.actualAction !== observation.predictedAction ? 1 : 0,
      lastObservedAt: observedAt,
    });
  }

  return {
    patterns,
    observations: [...state.observations, nextObservation].slice(-MAX_OBSERVATIONS),
  };
}

export function buildPredictiveActionSummary(decision: PredictiveActionDecision): string {
  if (decision.signal === 'none') return 'Keine Vorhersage nötig.';
  return `${decision.reason} Nächste Aktion: ${decision.action}. Sicherheit: ${decision.confidence}.`;
}
