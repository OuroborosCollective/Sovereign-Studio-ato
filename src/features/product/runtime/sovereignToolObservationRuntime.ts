/**
 * Sovereign Tool Observation Runtime
 *
 * Converts executor/tool activity into compact, redacted runtime events.
 * This file does not execute tools. It only records observable truth:
 * selected -> started -> observed/completed/failed/blocked.
 */

import type {
  SovereignActionEventInput,
  SovereignActionEventState,
  SovereignActionKind,
  SovereignActionRoute,
} from './sovereignActionStreamRuntime';

export type SovereignToolObservationPhase =
  | 'selected'
  | 'started'
  | 'observed'
  | 'completed'
  | 'failed'
  | 'blocked';

export interface SovereignToolObservationInput {
  readonly toolName: string;
  readonly route: SovereignActionRoute;
  readonly phase: SovereignToolObservationPhase;
  readonly target?: string;
  readonly argumentsSummary?: string;
  readonly resultSummary?: string;
  readonly blocker?: string;
  readonly createdAt?: number;
}

export interface SovereignToolObservation {
  readonly id: string;
  readonly toolName: string;
  readonly route: SovereignActionRoute;
  readonly phase: SovereignToolObservationPhase;
  readonly target?: string;
  readonly argumentsSummary?: string;
  readonly resultSummary?: string;
  readonly blocker?: string;
  readonly createdAt: number;
  readonly event: SovereignActionEventInput;
}

const SECRET_PATTERNS: readonly RegExp[] = [
  /ghp_[A-Za-z0-9_]{20,}/g,
  /github_pat_[A-Za-z0-9_]{20,}/g,
  /sk-proj-[A-Za-z0-9_-]{20,}/g,
  /sk-[A-Za-z0-9_-]{20,}/g,
  /(?:token|password|secret|api[_-]?key)\s*[=:]\s*["']?[^"',\s]+/gi,
];

const PHASE_TO_EVENT: Record<SovereignToolObservationPhase, {
  readonly kind: SovereignActionKind;
  readonly state: SovereignActionEventState;
  readonly label: string;
}> = {
  selected: {
    kind: 'route_selected',
    state: 'queued',
    label: 'Tool ausgewählt',
  },
  started: {
    kind: 'executor_started',
    state: 'running',
    label: 'Tool gestartet',
  },
  observed: {
    kind: 'answer_ready',
    state: 'done',
    label: 'Tool-Ergebnis beobachtet',
  },
  completed: {
    kind: 'done',
    state: 'done',
    label: 'Tool abgeschlossen',
  },
  failed: {
    kind: 'failed',
    state: 'failed',
    label: 'Tool fehlgeschlagen',
  },
  blocked: {
    kind: 'blocked',
    state: 'blocked',
    label: 'Tool blockiert',
  },
};

function stableSegment(value: string | undefined): string {
  return sanitizeSovereignObservationText(value ?? 'none')
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/gi, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 72) || 'none';
}

export function sanitizeSovereignObservationText(value: string): string {
  return SECRET_PATTERNS.reduce(
    (current, pattern) => current.replace(pattern, '[redacted-secret]'),
    value,
  );
}

export function containsSovereignSecretLikeText(value: string): boolean {
  return SECRET_PATTERNS.some((pattern) => {
    pattern.lastIndex = 0;
    return pattern.test(value);
  });
}

function buildDetail(input: SovereignToolObservationInput): string {
  const parts = [
    input.target ? `Target: ${input.target}` : '',
    input.argumentsSummary ? `Args: ${input.argumentsSummary}` : '',
    input.resultSummary ? `Result: ${input.resultSummary}` : '',
    input.blocker ? `Blocker: ${input.blocker}` : '',
  ].filter(Boolean);

  return sanitizeSovereignObservationText(parts.join(' · '));
}

export function createSovereignToolObservation(
  input: SovereignToolObservationInput,
): SovereignToolObservation {
  const createdAt = input.createdAt ?? Date.now();
  const phaseEvent = PHASE_TO_EVENT[input.phase];
  const toolName = sanitizeSovereignObservationText(input.toolName.trim() || 'unknown-tool');
  const target = input.target ? sanitizeSovereignObservationText(input.target) : undefined;
  const argumentsSummary = input.argumentsSummary
    ? sanitizeSovereignObservationText(input.argumentsSummary)
    : undefined;
  const resultSummary = input.resultSummary
    ? sanitizeSovereignObservationText(input.resultSummary)
    : undefined;
  const blocker = input.blocker ? sanitizeSovereignObservationText(input.blocker) : undefined;

  const detail = buildDetail({
    ...input,
    toolName,
    target,
    argumentsSummary,
    resultSummary,
    blocker,
  });

  const event: SovereignActionEventInput = {
    kind: phaseEvent.kind,
    route: input.route,
    label: `${phaseEvent.label}: ${toolName}`,
    detail: detail || undefined,
    state: phaseEvent.state,
    createdAt,
    target,
  };

  return {
    id: [
      createdAt,
      input.route,
      input.phase,
      stableSegment(toolName),
      stableSegment(target),
    ].join(':'),
    toolName,
    route: input.route,
    phase: input.phase,
    target,
    argumentsSummary,
    resultSummary,
    blocker,
    createdAt,
    event,
  };
}

export function summarizeSovereignToolObservation(
  observation: SovereignToolObservation,
): string {
  const suffix = observation.blocker
    ? ` blocked: ${observation.blocker}`
    : observation.resultSummary
      ? ` result: ${observation.resultSummary}`
      : observation.target
        ? ` target: ${observation.target}`
        : '';

  return sanitizeSovereignObservationText(
    `${observation.phase} ${observation.toolName} via ${observation.route}${suffix}`,
  );
}

export function hasRepeatedSovereignObservation(
  observations: readonly SovereignToolObservation[],
  threshold = 2,
): boolean {
  if (observations.length < threshold + 1) return false;
  const last = observations[observations.length - 1];
  const same = observations
    .slice(0, -1)
    .reverse()
    .filter((item) =>
      item.toolName === last.toolName
      && item.route === last.route
      && item.phase === last.phase
      && item.blocker === last.blocker
      && item.resultSummary === last.resultSummary,
    );

  return same.length >= threshold;
}
