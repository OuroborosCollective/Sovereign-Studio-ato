// Import blocker types for registry integration
import type {
  SovereignBlockerKind,
  SovereignBlockerSeverity,
} from './sovereignBlockerRegistry';

export type SovereignActionRoute =
  | 'repo'
  | 'free-chat'
  | 'code-llm'
  | 'worker'
  | 'openhands'
  | 'github-patch'
  | 'direct-github-patch'
  | 'github-access'
  | 'toolchain'
  | 'runtime';

// Re-export blocker types for consumers
export type { SovereignBlockerKind, SovereignBlockerSeverity } from './sovereignBlockerRegistry';

export type SovereignActionKind =
  | 'input_received'
  | 'repo_context_loaded'
  | 'intent_detected'
  | 'route_selected'
  | 'context_collected'
  | 'llm_request_started'
  | 'llm_response_received'
  | 'answer_ready'
  | 'patch_generated'
  | 'patch_validating'
  | 'github_access_required'
  | 'access_required'
  | 'patch_apply_blocked'
  | 'patch_blocked'
  | 'executor_started'
  | 'draft_pr_ready'
  | 'blocked'
  | 'failed'
  | 'done';

export type SovereignActionEventState = 'queued' | 'running' | 'blocked' | 'done' | 'failed';

export interface SovereignActionEventInput {
  readonly kind: SovereignActionKind;
  readonly route: SovereignActionRoute;
  readonly label: string;
  readonly detail?: string;
  readonly state: SovereignActionEventState;
  readonly createdAt?: number;
  readonly sourceId?: string;
  readonly target?: string;
}

export interface SovereignActionEvent extends SovereignActionEventInput {
  readonly id: string;
  readonly createdAt: number;
}

export interface SovereignActionStreamState {
  readonly events: readonly SovereignActionEvent[];
  readonly activeRoute: SovereignActionRoute | null;
  readonly lastEvent: SovereignActionEvent | null;
}

/** Extended state with blocker registry integration */
export interface SovereignActionStreamStateWithBlockers extends SovereignActionStreamState {
  readonly blockerCounts: {
    readonly activeBlockers: number;
    readonly warnings: number;
    readonly errors: number;
  };
  readonly blockedEventCount: number;
}

const TERMINAL_STATES: ReadonlySet<SovereignActionEventState> = new Set([
  'blocked',
  'done',
  'failed',
]);

const CODE_RESULT_KINDS: ReadonlySet<SovereignActionKind> = new Set([
  'patch_generated',
  'patch_validating',
  'github_access_required',
  'access_required',
  'patch_apply_blocked',
  'patch_blocked',
  'executor_started',
  'draft_pr_ready',
  'blocked',
  'failed',
  'done',
]);

export function createSovereignActionStreamState(): SovereignActionStreamState {
  return {
    events: [],
    activeRoute: null,
    lastEvent: null,
  };
}

function eventId(input: SovereignActionEventInput, index: number): string {
  return [
    input.createdAt ?? 'now',
    input.route,
    input.kind,
    input.state,
    index,
  ].join(':');
}

function createActionEvent(input: SovereignActionEventInput, index: number): SovereignActionEvent {
  const createdAt = input.createdAt ?? Date.now();
  return {
    ...input,
    id: eventId({ ...input, createdAt }, index),
    createdAt,
  };
}

function eventsSinceLastInput(events: readonly SovereignActionEvent[]): readonly SovereignActionEvent[] {
  const lastInputIndex = events.reduce(
    (last, event, index) => (event.kind === 'input_received' ? index : last),
    -1,
  );
  return lastInputIndex >= 0 ? events.slice(lastInputIndex) : events;
}

function hasUnresolvedCodeResultGate(events: readonly SovereignActionEvent[]): boolean {
  const scopedEvents = eventsSinceLastInput(events);
  const hasCodeRoute = scopedEvents.some(
    (event) => event.route === 'code-llm' && event.kind === 'route_selected' && event.state === 'running',
  );
  if (!hasCodeRoute) return false;

  return !scopedEvents.some((event) => {
    if (!CODE_RESULT_KINDS.has(event.kind)) return false;
    return event.route === 'code-llm'
      || event.route === 'github-patch'
      || event.route === 'github-access'
      || event.route === 'openhands';
  });
}

function buildCodeResultGateEvent(createdAt: number): SovereignActionEventInput {
  return {
    kind: 'github_access_required',
    route: 'github-access',
    label: 'Code-Auftrag braucht Ergebnis-Gate',
    detail:
      'Worker-Antwort ist nur Beratung. Für echte Umsetzung muss Sovereign Patch/Diff erzeugen oder GitHub-Zugang/Draft-PR-Route öffnen.',
    state: 'blocked',
    createdAt: createdAt + 1,
  };
}

function sameActiveBlocker(left: SovereignActionEvent | null, right: SovereignActionEventInput): boolean {
  if (!left) return false;
  if (left.state !== 'blocked' && left.state !== 'failed') return false;
  if (right.state !== 'blocked' && right.state !== 'failed') return false;
  return left.route === right.route
    && left.kind === right.kind
    && left.label.trim() === right.label.trim()
    && (left.detail ?? '').trim() === (right.detail ?? '').trim();
}

export function appendSovereignActionEvent(
  stream: SovereignActionStreamState,
  input: SovereignActionEventInput,
  maxEvents = 80,
): SovereignActionStreamState {
  if (sameActiveBlocker(stream.lastEvent, input)) {
    return stream;
  }

  const createdAt = input.createdAt ?? Date.now();
  const nextEvent = createActionEvent({ ...input, createdAt }, stream.events.length);
  const shouldAddCodeGate =
    input.kind === 'llm_response_received'
    && input.route === 'worker'
    && input.state === 'done'
    && hasUnresolvedCodeResultGate(stream.events);
  const appendedEvents = shouldAddCodeGate
    ? [
        nextEvent,
        createActionEvent(buildCodeResultGateEvent(createdAt), stream.events.length + 1),
      ]
    : [nextEvent];
  const events = [...stream.events, ...appendedEvents].slice(-Math.max(1, maxEvents));
  const lastEvent = events[events.length - 1] ?? null;
  return {
    events,
    activeRoute: lastEvent && !TERMINAL_STATES.has(lastEvent.state) ? lastEvent.route : null,
    lastEvent,
  };
}

export function appendSovereignActionEvents(
  stream: SovereignActionStreamState,
  inputs: readonly SovereignActionEventInput[],
  maxEvents = 80,
): SovereignActionStreamState {
  return inputs.reduce(
    (current, input) => appendSovereignActionEvent(current, input, maxEvents),
    stream,
  );
}

export function latestSovereignActionByRoute(
  stream: SovereignActionStreamState,
): Partial<Record<SovereignActionRoute, SovereignActionEvent>> {
  return stream.events.reduce<Partial<Record<SovereignActionRoute, SovereignActionEvent>>>(
    (latest, event) => ({ ...latest, [event.route]: event }),
    {},
  );
}

export function findActiveSovereignActionBlocker(stream: SovereignActionStreamState): SovereignActionEvent | null {
  for (let index = stream.events.length - 1; index >= 0; index -= 1) {
    const event = stream.events[index];
    if (event.state === 'blocked' || event.state === 'failed') return event;
    if (event.kind === 'input_received') return null;
  }
  return null;
}

export function buildLocalStatusAnswerFromActionStream(stream: SovereignActionStreamState): string {
  const blocker = findActiveSovereignActionBlocker(stream);
  if (blocker) {
    return [
      `Status: blockiert durch ${blocker.label}.`,
      blocker.detail ? `Grund: ${blocker.detail}` : '',
      'Ich wiederhole keinen kaputten Worker-/Executor-Call blind. Nächste Aktion: Blocker prüfen oder passende Reparaturroute öffnen.',
    ].filter(Boolean).join('\n');
  }

  if (stream.activeRoute) {
    return `Status: ${stream.activeRoute} läuft. Ich warte auf ein echtes Ergebnis, bevor ich Erfolg melde.`;
  }

  const last = stream.lastEvent;
  if (!last) return 'Status: noch keine Runtime-Aktion im Action Stream.';
  return `Status: letzte Runtime-Aktion: ${describeSovereignActionEvent(last)} (${last.state}).`;
}

export function describeSovereignActionEvent(event: SovereignActionEvent): string {
  const detail = event.detail?.trim();
  return detail ? `${event.label}: ${detail}` : event.label;
}

export function buildRouteSelectionEvent(args: {
  readonly route: SovereignActionRoute;
  readonly reason: string;
  readonly state?: SovereignActionEventState;
}): SovereignActionEventInput {
  return {
    kind: 'route_selected',
    route: args.route,
    label: `Route gewählt: ${args.route}`,
    detail: args.reason,
    state: args.state ?? 'done',
  };
}

export function buildBlockedActionEvent(args: {
  readonly route: SovereignActionRoute;
  readonly label: string;
  readonly detail: string;
  readonly kind?: SovereignActionKind;
}): SovereignActionEventInput {
  return {
    kind: args.kind ?? 'blocked',
    route: args.route,
    label: args.label,
    detail: args.detail,
    state: 'blocked',
  };
}

export function buildAnswerReadyEvent(detail = 'Antwort bereit.'): SovereignActionEventInput {
  return {
    kind: 'answer_ready',
    route: 'free-chat',
    label: 'Antwort bereit',
    detail,
    state: 'done',
  };
}

export function buildInputReceivedEvent(text: string): SovereignActionEventInput {
  return {
    kind: 'input_received',
    route: 'runtime',
    label: 'Auftrag empfangen',
    detail: text.length > 120 ? `${text.slice(0, 117)}...` : text,
    state: 'done',
  };
}

export function buildRepoLoadedEvent(detail: string): SovereignActionEventInput {
  return {
    kind: 'repo_context_loaded',
    route: 'repo',
    label: 'Repo-Kontext geladen',
    detail,
    state: 'done',
  };
}

export function buildWorkerRequestEvent(modelLabel: string): SovereignActionEventInput {
  return {
    kind: 'llm_request_started',
    route: 'worker',
    label: 'Worker-Route fragt Modell an',
    detail: modelLabel,
    state: 'running',
  };
}

export function buildWorkerResponseEvent(): SovereignActionEventInput {
  return {
    kind: 'llm_response_received',
    route: 'worker',
    label: 'Worker-Antwort erhalten',
    state: 'done',
  };
}

/**
 * Map action event kinds to blocker kinds for registry integration
 */
function mapEventKindToBlockerKind(kind: SovereignActionKind): SovereignBlockerKind | null {
  switch (kind) {
    case 'github_access_required':
      return 'github_access_required';
    case 'access_required':
      return 'github_access_required';
    case 'patch_apply_blocked':
      return 'patch_route_unavailable';
    case 'patch_blocked':
      return 'patch_route_unavailable';
    case 'blocked':
      return 'worker_blocked';
    case 'failed':
      return 'runtime_error';
    default:
      return null;
  }
}

/**
 * Map action event state to severity
 */
function mapEventStateToSeverity(state: SovereignActionEventState): SovereignBlockerSeverity {
  switch (state) {
    case 'blocked':
      return 'warning';
    case 'failed':
      return 'error';
    default:
      return 'info';
  }
}

/**
 * Get blocker counts from events without registry (for inline display).
 * This deduplicates by route+kind so repeated blocked events don't inflate counts.
 */
export function deriveBlockerCountsFromEvents(
  events: readonly SovereignActionEvent[],
): { activeBlockers: number; warnings: number; errors: number; blockedEventCount: number } {
  // Track unique blockers by route+kind
  const uniqueBlockers = new Map<string, { kind: SovereignBlockerKind; severity: SovereignBlockerSeverity }>();
  
  let blockedCount = 0;

  for (const event of events) {
    if (event.state === 'blocked' || event.state === 'failed') {
      blockedCount++;
      
      const blockerKind = mapEventKindToBlockerKind(event.kind);
      if (blockerKind) {
        const key = `${event.route}:${blockerKind}`;
        if (!uniqueBlockers.has(key)) {
          uniqueBlockers.set(key, {
            kind: blockerKind,
            severity: mapEventStateToSeverity(event.state),
          });
        }
      }
    }
  }

  const blockers = Array.from(uniqueBlockers.values());
  const warnings = blockers.filter((b) => b.severity === 'warning').length;
  const errors = blockers.filter((b) => b.severity === 'error').length;

  return {
    activeBlockers: blockers.length,
    warnings,
    errors,
    blockedEventCount: blockedCount,
  };
}

/**
 * Extend action stream state with blocker counts
 */
export function extendWithBlockerCounts(
  stream: SovereignActionStreamState,
): SovereignActionStreamStateWithBlockers {
  const counts = deriveBlockerCountsFromEvents(stream.events);
  return {
    ...stream,
    blockerCounts: {
      activeBlockers: counts.activeBlockers,
      warnings: counts.warnings,
      errors: counts.errors,
    },
    blockedEventCount: counts.blockedEventCount,
  };
}
