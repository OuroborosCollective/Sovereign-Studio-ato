/**
 * Sovereign Blocker Registry
 *
 * Tracks active blockers with key-based deduplication.
 * Prevents the same blocker from being counted multiple times.
 *
 * Runtime Contract from Issue #504:
 * - UI must not invent truth
 * - No fake successes
 * - No percentage progress
 * - Same blocker must NOT be counted as new error each time
 * - Each blocker must have a next allowed action or clear blockage
 */

import { createHash } from 'crypto';

/** Blocker kind classification */
export type SovereignBlockerKind =
  | 'github_access_required'
  | 'github_access_validating'
  | 'executor_unavailable'
  | 'patch_route_unavailable'
  | 'worker_blocked'
  | 'workspace_required'
  | 'unsafe_action'
  | 'runtime_error'
  | 'timeout';

/** Blocker severity levels */
export type SovereignBlockerSeverity = 'info' | 'warning' | 'error';

/** Active blocker with deduplication support */
export interface SovereignActiveBlocker {
  readonly key: string;
  readonly kind: SovereignBlockerKind;
  readonly route: string;
  readonly label: string;
  readonly detail: string;
  readonly firstSeenAt: number;
  readonly lastSeenAt: number;
  readonly occurrences: number;
  readonly severity: SovereignBlockerSeverity;
  readonly nextAction: string;
}

/** Input for registering a blocker event */
export interface BlockerEventInput {
  readonly kind: SovereignBlockerKind;
  readonly route: string;
  readonly label: string;
  readonly detail: string;
  readonly severity?: SovereignBlockerSeverity;
  readonly nextAction: string;
}

/** Registry state holding all active blockers */
export interface SovereignBlockerRegistryState {
  readonly blockers: readonly SovereignActiveBlocker[];
  readonly activeBlockerCount: number;
  readonly warningCount: number;
  readonly errorCount: number;
  readonly lastUpdatedAt: number;
}

/**
 * Generate a stable key for blocker deduplication.
 * Key = route + kind + normalized detail
 */
export function generateBlockerKey(input: BlockerEventInput): string {
  const normalizedDetail = input.detail
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 200);
  const keySource = `${input.route}:${input.kind}:${normalizedDetail}`;
  return createHash('sha256').update(keySource).digest('hex').slice(0, 32);
}

/**
 * Default severity based on blocker kind
 */
export function defaultSeverityForKind(kind: SovereignBlockerKind): SovereignBlockerSeverity {
  switch (kind) {
    case 'github_access_required':
    case 'workspace_required':
    case 'unsafe_action':
      return 'error';
    case 'github_access_validating':
    case 'executor_unavailable':
    case 'patch_route_unavailable':
      return 'warning';
    case 'worker_blocked':
    case 'timeout':
    case 'runtime_error':
      return 'warning';
    default:
      return 'info';
  }
}

/**
 * Create initial blocker registry state
 */
export function createBlockerRegistryState(): SovereignBlockerRegistryState {
  return {
    blockers: [],
    activeBlockerCount: 0,
    warningCount: 0,
    errorCount: 0,
    lastUpdatedAt: Date.now(),
  };
}

/**
 * Register a blocker event, updating existing or creating new entry.
 * Returns new state with deduplicated blockers.
 */
export function registerBlocker(
  state: SovereignBlockerRegistryState,
  input: BlockerEventInput,
): SovereignBlockerRegistryState {
  const key = generateBlockerKey(input);
  const now = Date.now();
  const severity = input.severity ?? defaultSeverityForKind(input.kind);

  const existingIndex = state.blockers.findIndex((b) => b.key === key);

  let updatedBlockers: SovereignActiveBlocker[];

  if (existingIndex >= 0) {
    // Update existing blocker - increment occurrences
    updatedBlockers = state.blockers.map((b, i) =>
      i === existingIndex
        ? {
            ...b,
            lastSeenAt: now,
            occurrences: b.occurrences + 1,
            // Update label/detail if provided (keep latest)
            label: input.label || b.label,
            detail: input.detail || b.detail,
            nextAction: input.nextAction || b.nextAction,
          }
        : b,
    );
  } else {
    // Create new blocker
    const newBlocker: SovereignActiveBlocker = {
      key,
      kind: input.kind,
      route: input.route,
      label: input.label,
      detail: input.detail,
      firstSeenAt: now,
      lastSeenAt: now,
      occurrences: 1,
      severity,
      nextAction: input.nextAction,
    };
    updatedBlockers = [...state.blockers, newBlocker];
  }

  return computeRegistryCounts({ ...state, blockers: updatedBlockers, lastUpdatedAt: now });
}

/**
 * Dismiss a specific blocker by key
 */
export function dismissBlocker(
  state: SovereignBlockerRegistryState,
  key: string,
): SovereignBlockerRegistryState {
  const updatedBlockers = state.blockers.filter((b) => b.key !== key);
  return computeRegistryCounts({ ...state, blockers: updatedBlockers, lastUpdatedAt: Date.now() });
}

/**
 * Clear all blockers of a specific kind
 */
export function clearBlockersByKind(
  state: SovereignBlockerRegistryState,
  kind: SovereignBlockerKind,
): SovereignBlockerRegistryState {
  const updatedBlockers = state.blockers.filter((b) => b.kind !== kind);
  return computeRegistryCounts({ ...state, blockers: updatedBlockers, lastUpdatedAt: Date.now() });
}

/**
 * Clear all blockers
 */
export function clearAllBlockers(state: SovereignBlockerRegistryState): SovereignBlockerRegistryState {
  return createBlockerRegistryState();
}

/**
 * Compute aggregated counts from blockers array
 */
function computeRegistryCounts(state: SovereignBlockerRegistryState): SovereignBlockerRegistryState {
  const blockers = [...state.blockers];
  const activeBlockerCount = blockers.length;
  const warningCount = blockers.filter((b) => b.severity === 'warning').length;
  const errorCount = blockers.filter((b) => b.severity === 'error').length;

  return {
    blockers,
    activeBlockerCount,
    warningCount,
    errorCount,
    lastUpdatedAt: state.lastUpdatedAt,
  };
}

/**
 * Get next action text based on current runtime state
 */
export function deriveBlockerNextAction(args: {
  githubReady: boolean;
  githubValidating: boolean;
  executorAvailable: boolean;
  patchRouteAvailable: boolean;
  openhandsConfigured: boolean;
}): string {
  const { githubReady, githubValidating, executorAvailable, patchRouteAvailable, openhandsConfigured } = args;

  // GitHub is validating - wait for result
  if (githubValidating) {
    return 'GitHub-Zugang wird geprüft. Bitte Ergebnis abwarten.';
  }

  // GitHub is missing
  if (!githubReady && !githubValidating) {
    return 'Sicheren GitHub-Zugang öffnen.';
  }

  // GitHub is ready but executor is unavailable
  if (githubReady && !executorAvailable) {
    if (!openhandsConfigured) {
      return 'OpenHands konfigurieren.';
    }
    return 'Workspace Executor starten.';
  }

  // GitHub is ready but patch route is blocked
  if (githubReady && !patchRouteAvailable) {
    return 'Direct GitHub Patch Runtime aktivieren.';
  }

  // GitHub ready, everything available
  if (githubReady && executorAvailable && patchRouteAvailable) {
    return 'Auftrag eingeben und ausführen.';
  }

  // Default fallback
  return 'Warte auf verfügbare Ressourcen.';
}

/**
 * Create a blocker event from a GitHub access state
 */
export function blockerFromGitHubAccess(args: {
  state: 'missing' | 'requested' | 'validating' | 'ready' | 'invalid';
  maskedToken: string | null;
}): BlockerEventInput | null {
  switch (args.state) {
    case 'missing':
      return {
        kind: 'github_access_required',
        route: 'github-access',
        label: 'GitHub-Zugang fehlt',
        detail: 'GitHub-Zugang benötigt für Draft PR.',
        severity: 'error',
        nextAction: 'Sicheren GitHub-Zugang öffnen.',
      };
    case 'validating':
      return {
        kind: 'github_access_validating',
        route: 'github-access',
        label: 'GitHub-Zugang wird geprüft',
        detail: 'GitHub-API wird auf Schreibzugriff geprüft.',
        severity: 'warning',
        nextAction: 'GitHub-Zugang wird geprüft. Bitte Ergebnis abwarten.',
      };
    case 'invalid':
      return {
        kind: 'github_access_required',
        route: 'github-access',
        label: 'GitHub-Zugang ungültig',
        detail: 'Der eingegebene GitHub-Zugang ist ungültig oder hat keinen Schreibzugriff.',
        severity: 'error',
        nextAction: 'Gültigen GitHub-Zugang eingeben.',
      };
    case 'ready':
    case 'requested':
      return null; // No blocker when ready
  }
}

/**
 * Create a blocker event from worker error
 */
export function blockerFromWorkerError(args: {
  statusCode?: number;
  errorMessage?: string;
}): BlockerEventInput {
  const { statusCode, errorMessage } = args;

  if (statusCode === 500) {
    return {
      kind: 'worker_blocked',
      route: 'worker',
      label: 'Worker-Fehler',
      detail: errorMessage || 'Worker antwortet mit HTTP 500.',
      severity: 'warning',
      nextAction: 'Worker-Status prüfen oder später erneut versuchen.',
    };
  }

  if (statusCode === 503) {
    return {
      kind: 'worker_blocked',
      route: 'worker',
      label: 'Worker nicht verfügbar',
      detail: errorMessage || 'Worker antwortet mit HTTP 503.',
      severity: 'warning',
      nextAction: 'Worker-Status prüfen.',
    };
  }

  return {
    kind: 'worker_blocked',
    route: 'worker',
    label: 'Worker-Fehler',
    detail: errorMessage || 'Unbekannter Worker-Fehler.',
    severity: 'warning',
    nextAction: 'Details im Log prüfen.',
  };
}

/**
 * Format blocker for display
 */
export function formatBlockerSummary(state: SovereignBlockerRegistryState): {
  activeBlockers: number;
  warnings: number;
  errors: number;
  summary: string;
} {
  const { activeBlockerCount, warningCount, errorCount } = state;

  const parts: string[] = [];
  if (activeBlockerCount > 0) parts.push(`${activeBlockerCount} Blocker`);
  if (warningCount > 0) parts.push(`${warningCount} Warnung(en)`);
  if (errorCount > 0) parts.push(`${errorCount} Fehler`);

  return {
    activeBlockers: activeBlockerCount,
    warnings: warningCount,
    errors: errorCount,
    summary: parts.length > 0 ? parts.join(' · ') : 'Alle Systeme bereit',
  };
}
