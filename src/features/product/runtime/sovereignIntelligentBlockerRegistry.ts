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

  const targetText = observation.blocker;
  const now = Date.now();
  const blockers = state.blockers;
  const len = blockers.length;
  const updatedBlockers: TrackedBlocker[] = new Array(len);
  let activeBlockers = 0;
  let found = false;

  // ⚡ Bolt: Single-pass loop updates/adds blocker and counts active blockers concurrently,
  // eliminating multiple O(N) traversals (findIndex, map, filter) and intermediate allocations.
  for (let i = 0; i < len; i++) {
    const b = blockers[i];
    if (b.blockerText === targetText) {
      found = true;
      const updated: TrackedBlocker = {
        ...b,
        lastSeen: now,
        occurrenceCount: b.occurrenceCount + 1,
      };
      updatedBlockers[i] = updated;
      if (updated.occurrenceCount > updated.resolvedCount) {
        activeBlockers++;
      }
    } else {
      updatedBlockers[i] = b;
      if (b.occurrenceCount > b.resolvedCount) {
        activeBlockers++;
      }
    }
  }

  if (!found) {
    const category = categorizeBlocker(targetText);
    const newBlocker: TrackedBlocker = {
      blockerText: targetText,
      kind: category.kind,
      severity: category.severity,
      category: category.category,
      firstSeen: now,
      lastSeen: now,
      occurrenceCount: 1,
      resolutionHint: category.resolutionHint,
      resolvedCount: 0,
    };
    updatedBlockers.push(newBlocker);
    activeBlockers++;
  }

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
  const blockers = state.blockers;
  const len = blockers.length;

  let targetIndex = -1;
  for (let i = 0; i < len; i++) {
    if (blockers[i].blockerText === blockerText) {
      targetIndex = i;
      break;
    }
  }

  if (targetIndex < 0) return state;

  const updatedBlockers: TrackedBlocker[] = new Array(len);
  let activeBlockers = 0;

  // ⚡ Bolt: Single-pass loop updates resolved count and counts remaining active blockers concurrent with array construction
  for (let i = 0; i < len; i++) {
    const b = blockers[i];
    if (i === targetIndex) {
      const updated: TrackedBlocker = {
        ...b,
        resolvedCount: b.resolvedCount + 1,
      };
      updatedBlockers[i] = updated;
      if (updated.occurrenceCount > updated.resolvedCount) {
        activeBlockers++;
      }
    } else {
      updatedBlockers[i] = b;
      if (b.occurrenceCount > b.resolvedCount) {
        activeBlockers++;
      }
    }
  }

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
  const blockers = state.blockers;
  const len = blockers.length;
  const stuck: TrackedBlocker[] = [];

  // ⚡ Bolt: Single-pass loop filters stuck blockers directly without sorting active blockers first
  for (let i = 0; i < len; i++) {
    const b = blockers[i];
    if (b.occurrenceCount - b.resolvedCount >= threshold) {
      stuck.push(b);
    }
  }

  return stuck.sort((a, b) => {
    if (a.severity !== b.severity) {
      return a.severity === 'error' ? -1 : 1;
    }
    return b.occurrenceCount - a.occurrenceCount;
  });
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
