export type SovereignActionRoute =
  | 'repo'
  | 'free-chat'
  | 'code-llm'
  | 'worker'
  | 'openhands'
  | 'github-patch'
  | 'github-access'
  | 'toolchain'
  | 'runtime';

export type SovereignActionKind =
  | 'input_received'
  | 'repo_context_loaded'
  | 'intent_detected'
  | 'route_selected'
  | 'context_collected'
  | 'llm_request_started'
  | 'llm_response_received'
  | 'patch_generated'
  | 'patch_validating'
  | 'github_access_required'
  | 'patch_apply_blocked'
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

const TERMINAL_STATES: ReadonlySet<SovereignActionEventState> = new Set([
  'blocked',
  'done',
  'failed',
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

export function appendSovereignActionEvent(
  stream: SovereignActionStreamState,
  input: SovereignActionEventInput,
  maxEvents = 80,
): SovereignActionStreamState {
  const createdAt = input.createdAt ?? Date.now();
  const nextEvent: SovereignActionEvent = {
    ...input,
    id: eventId({ ...input, createdAt }, stream.events.length),
    createdAt,
  };
  const events = [...stream.events, nextEvent].slice(-Math.max(1, maxEvents));
  return {
    events,
    activeRoute: TERMINAL_STATES.has(nextEvent.state) ? null : nextEvent.route,
    lastEvent: nextEvent,
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
