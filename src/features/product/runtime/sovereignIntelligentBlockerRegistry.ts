/**
 * Sovereign Intelligent Blocker Registry
 *
 * Extends sovereignBlockerRegistry with intelligence:
 * - Tracks blocker history
 * - Suggests resolutions based on past patterns
 * - Detects repeated blockers
 *
 * @module sovereignIntelligentBlockerRegistry
 */

import type { SovereignToolObservation } from './sovereignToolObservationRuntime';
import type { ContainerDecisionLearningSignal } from './containerDecisionLearning';

/**
 * Known blocker categories with resolution hints
 */
export interface BlockerCategory {
  readonly kind: string;
  readonly pattern: RegExp;
  readonly severity: 'warning' | 'error';
  readonly resolutionHint: string;
  readonly category: 'auth' | 'resource' | 'network' | 'config' | 'rate-limit' | 'unknown';
}

const BLOCKER_CATEGORIES: readonly BlockerCategory[] = [
  {
    kind: 'github_access_required',
    pattern: /token|auth|password|credential|permission|unauthorized|401|403|ghp_|github_pat/i,
    severity: 'error',
    resolutionHint: 'GitHub Token in Kanal bereitstellen oder GitHub Access Route öffnen',
    category: 'auth',
  },
  {
    kind: 'network_error',
    pattern: /dns|connection|refused|econnreset|enotfound/i,
    severity: 'error',
    resolutionHint: 'Netzwerk-Verbindung prüfen oder Proxy-Einstellungen kontrollieren',
    category: 'network',
  },
  {
    kind: 'patch_route_unavailable',
    pattern: /patch|diff|pr|merge|conflict|branch/i,
    severity: 'warning',
    resolutionHint: 'Alternative Patch-Strategie wählen oder Branch-Konfiguration prüfen',
    category: 'config',
  },
  {
    kind: 'worker_blocked',
    pattern: /worker|busy|queue|pending|rate limit|429/i,
    severity: 'warning',
    resolutionHint: 'Wartezeit einplanen oder Worker-Kapazität prüfen',
    category: 'rate-limit',
  },
  {
    kind: 'resource_exhausted',
    pattern: /memory|heap|cpu|disk|space|quota|limit exceeded|out of/i,
    severity: 'error',
    resolutionHint: 'Ressourcen-Limits prüfen oder Wartungsfenster abwarten',
    category: 'resource',
  },
  {
    kind: 'runtime_error',
    pattern: /error|exception|failed|crash|panic|abort/i,
    severity: 'error',
    resolutionHint: 'Logs analysieren und Fehlerursache beheben',
    category: 'unknown',
  },
];

/**
 * Tracked blocker occurrence
 */
export interface TrackedBlocker {
  readonly blockerText: string;
  readonly kind: string;
  readonly severity: 'warning' | 'error';
  readonly category: string;
  readonly firstSeen: number;
  readonly lastSeen: number;
  readonly occurrenceCount: number;
  readonly resolutionHint: string;
  readonly resolvedCount: number;
}

/**
 * Registry state for blocker tracking
 */
export interface BlockerRegistryState {
  readonly blockers: readonly TrackedBlocker[];
  readonly totalBlockers: number;
  readonly activeBlockers: number;
  readonly resolvedBlockers: number;
}

/**
 * Creates initial registry state
 */
export function createBlockerRegistryState(): BlockerRegistryState {
  return {
    blockers: [],
    totalBlockers: 0,
    activeBlockers: 0,
    resolvedBlockers: 0,
  };
}

/**
 * Categorizes a blocker based on its text
 */
export function categorizeBlocker(blockerText: string): BlockerCategory {
  for (const category of BLOCKER_CATEGORIES) {
    if (category.pattern.test(blockerText)) {
      return category;
    }
  }

  // Default fallback
  return {
    kind: 'unknown_blocker',
    pattern: /./,
    severity: 'warning',
    resolutionHint: 'Blocker analysieren und manuell prüfen',
    category: 'unknown',
  };
}

/**
 * Updates registry state with new blocker observation
 */
export function trackBlocker(
  state: BlockerRegistryState,
  observation: SovereignToolObservation,
): BlockerRegistryState {
  if (!observation.blocker) return state;

  const category = categorizeBlocker(observation.blocker);
  const now = Date.now();

  // Check if blocker already exists
  const existingIndex = state.blockers.findIndex(
    (b) => b.blockerText === observation.blocker,
  );

  let updatedBlockers: TrackedBlocker[];

  if (existingIndex >= 0) {
    // Update existing blocker
    updatedBlockers = state.blockers.map((b, i) => {
      if (i !== existingIndex) return b;
      return {
        ...b,
        lastSeen: now,
        occurrenceCount: b.occurrenceCount + 1,
        // Reset resolved count if blocker recurs
        resolvedCount: observation.phase === 'completed' ? b.resolvedCount : b.resolvedCount,
      };
    });
  } else {
    // Add new blocker
    const newBlocker: TrackedBlocker = {
      blockerText: observation.blocker,
      kind: category.kind,
      severity: category.severity,
      category: category.category,
      firstSeen: now,
      lastSeen: now,
      occurrenceCount: 1,
      resolutionHint: category.resolutionHint,
      resolvedCount: 0,
    };
    updatedBlockers = [...state.blockers, newBlocker];
  }

  const activeBlockers = updatedBlockers.filter(
    (b) => b.occurrenceCount > b.resolvedCount,
  ).length;

  return {
    blockers: updatedBlockers,
    totalBlockers: state.totalBlockers + 1,
    activeBlockers,
    resolvedBlockers: state.resolvedBlockers,
  };
}

/**
 * Marks a blocker as resolved
 */
export function resolveBlocker(
  state: BlockerRegistryState,
  blockerText: string,
): BlockerRegistryState {
  const blockerIndex = state.blockers.findIndex(
    (b) => b.blockerText === blockerText,
  );

  if (blockerIndex < 0) return state;

  const updatedBlockers = state.blockers.map((b, i) => {
    if (i !== blockerIndex) return b;
    return {
      ...b,
      resolvedCount: b.resolvedCount + 1,
    };
  });

  const activeBlockers = updatedBlockers.filter(
    (b) => b.occurrenceCount > b.resolvedCount,
  ).length;

  return {
    blockers: updatedBlockers,
    totalBlockers: state.totalBlockers,
    activeBlockers,
    resolvedBlockers: state.resolvedBlockers + 1,
  };
}

/**
 * Detects if a blocker is stuck (repeated more than threshold)
 */
export function isBlockerStuck(
  blocker: TrackedBlocker,
  threshold = 3,
): boolean {
  return blocker.occurrenceCount - blocker.resolvedCount >= threshold;
}

/**
 * Gets active blockers sorted by severity and recurrence
 */
export function getActiveBlockers(state: BlockerRegistryState): TrackedBlocker[] {
  return state.blockers
    .filter((b) => b.occurrenceCount > b.resolvedCount)
    .sort((a, b) => {
      // Sort by severity first (errors before warnings)
      if (a.severity !== b.severity) {
        return a.severity === 'error' ? -1 : 1;
      }
      // Then by occurrence count (most frequent first)
      return b.occurrenceCount - a.occurrenceCount;
    });
}

/**
 * Gets stuck blockers that need attention
 */
export function getStuckBlockers(
  state: BlockerRegistryState,
  threshold = 3,
): TrackedBlocker[] {
  return getActiveBlockers(state).filter((b) => isBlockerStuck(b, threshold));
}

/**
 * Gets resolution hint for a blocker
 */
export function getResolutionHint(blockerText: string): string {
  const category = categorizeBlocker(blockerText);
  return category.resolutionHint;
}

/**
 * Analyzes blocker patterns from learning signals
 */
export function analyzeBlockerPatterns(
  signals: readonly ContainerDecisionLearningSignal[],
): Map<string, { count: number; lastSeen: number; category: string }> {
  const patterns = new Map<string, { count: number; lastSeen: number; category: string }>();

  for (const signal of signals) {
    if (signal.outcome !== 'failure') continue;

    // Extract blocker info from reason
    const reason = signal.reason;
    const category = categorizeBlocker(reason);

    const existing = patterns.get(reason);
    if (existing) {
      existing.count++;
      existing.lastSeen = Math.max(existing.lastSeen, signal.timestamp);
    } else {
      patterns.set(reason, {
        count: 1,
        lastSeen: signal.timestamp,
        category: category.category,
      });
    }
  }

  return patterns;
}
