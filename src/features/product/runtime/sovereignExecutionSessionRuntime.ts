/**
 * Sovereign Execution Session Runtime
 *
 * Session state for the chat-controlled execution loop. Inspired by ReAct
 * agents, but intentionally stricter: a session advances only from observed
 * runtime results, never from UI optimism.
 */

import type { SovereignActionEventInput } from './sovereignActionStreamRuntime';
import {
  blockSovereignPlanStep,
  completeSovereignPlanStep,
  createSovereignPlanFromRequest,
  getSovereignPlanNextStep,
  markSovereignPlanStepInProgress,
  summarizeSovereignPlan,
  type SovereignPlan,
  type SovereignPlanNextAction,
} from './sovereignPlanRuntime';
import {
  createSovereignToolObservation,
  hasRepeatedSovereignObservation,
  sanitizeSovereignObservationText,
  type SovereignToolObservation,
  type SovereignToolObservationInput,
} from './sovereignToolObservationRuntime';

export type SovereignExecutionSessionStatus =
  | 'idle'
  | 'running'
  | 'blocked'
  | 'finished'
  | 'error';

export type SovereignExecutionSessionNextAction =
  | SovereignPlanNextAction
  | 'start_session'
  | 'observe_tool'
  | 'change_strategy'
  | 'show_result'
  | 'show_error';

export interface SovereignExecutionSession {
  readonly id: string;
  readonly request: string;
  readonly status: SovereignExecutionSessionStatus;
  readonly plan: SovereignPlan;
  readonly observations: readonly SovereignToolObservation[];
  readonly currentStepId: string | null;
  readonly blocker?: string;
  readonly error?: string;
  readonly createdAt: number;
  readonly updatedAt: number;
}

export interface SovereignExecutionSessionTransition {
  readonly session: SovereignExecutionSession;
  readonly event: SovereignActionEventInput;
  readonly nextAllowedAction: SovereignExecutionSessionNextAction;
}

export interface SovereignStuckDetectionResult {
  readonly stuck: boolean;
  readonly reason?: string;
  readonly nextAllowedAction: SovereignExecutionSessionNextAction;
}

function sessionId(now: number, request: string): string {
  const stable = request
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64) || 'request';
  return `session-${now}-${stable}`;
}

function sessionEvent(args: {
  readonly kind: SovereignActionEventInput['kind'];
  readonly label: string;
  readonly detail?: string;
  readonly state: SovereignActionEventInput['state'];
  readonly createdAt: number;
}): SovereignActionEventInput {
  return {
    kind: args.kind,
    route: 'runtime',
    label: args.label,
    detail: args.detail ? sanitizeSovereignObservationText(args.detail) : undefined,
    state: args.state,
    createdAt: args.createdAt,
  };
}

export function createSovereignExecutionSession(
  request: string,
  now = Date.now(),
): SovereignExecutionSession {
  const safeRequest = sanitizeSovereignObservationText(request.trim());
  const plan = createSovereignPlanFromRequest(safeRequest || 'Sovereign Auftrag', now);
  return {
    id: sessionId(now, safeRequest),
    request: safeRequest,
    status: 'idle',
    plan,
    observations: [],
    currentStepId: null,
    createdAt: now,
    updatedAt: now,
  };
}

export function startSovereignExecutionSession(
  session: SovereignExecutionSession,
  now = Date.now(),
): SovereignExecutionSessionTransition {
  if (session.status !== 'idle') {
    const blocked = {
      ...session,
      status: 'blocked' as const,
      blocker: `Cannot start session from ${session.status}.`,
      updatedAt: now,
    };
    return {
      session: blocked,
      nextAllowedAction: 'resolve_blocker',
      event: sessionEvent({
        kind: 'blocked',
        label: 'Execution Session Start blockiert',
        detail: blocked.blocker,
        state: 'blocked',
        createdAt: now,
      }),
    };
  }

  if (!session.request.trim()) {
    const blocked = {
      ...session,
      status: 'blocked' as const,
      blocker: 'Empty request cannot start an execution session.',
      updatedAt: now,
    };
    return {
      session: blocked,
      nextAllowedAction: 'resolve_blocker',
      event: sessionEvent({
        kind: 'blocked',
        label: 'Execution Session Start blockiert',
        detail: blocked.blocker,
        state: 'blocked',
        createdAt: now,
      }),
    };
  }

  const firstStep = getSovereignPlanNextStep(session.plan);
  const plan = firstStep
    ? markSovereignPlanStepInProgress(session.plan, firstStep.id, 'Session gestartet.', now)
    : session.plan;

  const nextStep = getSovereignPlanNextStep(plan);
  const running = {
    ...session,
    status: 'running' as const,
    plan,
    currentStepId: nextStep?.id ?? firstStep?.id ?? null,
    updatedAt: now,
  };

  return {
    session: running,
    nextAllowedAction: 'observe_tool',
    event: sessionEvent({
      kind: 'executor_started',
      label: 'Execution Session gestartet',
      detail: `Current step: ${running.currentStepId ?? 'none'}`,
      state: 'running',
      createdAt: now,
    }),
  };
}

export function detectSovereignExecutionStuck(
  session: SovereignExecutionSession,
  duplicateThreshold = 2,
): SovereignStuckDetectionResult {
  if (hasRepeatedSovereignObservation(session.observations, duplicateThreshold)) {
    return {
      stuck: true,
      reason: 'Repeated identical tool observations detected.',
      nextAllowedAction: 'change_strategy',
    };
  }

  const blockedObservations = session.observations.filter((item) => item.phase === 'blocked');
  const last = blockedObservations[blockedObservations.length - 1];
  if (last) {
    const sameBlockerCount = blockedObservations.filter((item) =>
      item.blocker === last.blocker && item.toolName === last.toolName,
    ).length;
    if (sameBlockerCount > duplicateThreshold) {
      return {
        stuck: true,
        reason: `Repeated blocker: ${last.blocker ?? 'unknown'}`,
        nextAllowedAction: 'change_strategy',
      };
    }
  }

  return {
    stuck: false,
    nextAllowedAction: deriveSovereignExecutionNextAction(session),
  };
}

export function observeSovereignExecutionTool(
  session: SovereignExecutionSession,
  input: SovereignToolObservationInput,
): SovereignExecutionSessionTransition {
  const observation = createSovereignToolObservation(input);
  const observations = [...session.observations, observation];
  const now = observation.createdAt;
  const activeStep = session.currentStepId ?? getSovereignPlanNextStep(session.plan)?.id ?? null;

  let plan = session.plan;
  let status: SovereignExecutionSessionStatus = session.status;
  let blocker = session.blocker;
  let error = session.error;

  if (activeStep && observation.phase === 'started') {
    plan = markSovereignPlanStepInProgress(plan, activeStep, observation.resultSummary, now);
    status = 'running';
  }

  if (activeStep && (observation.phase === 'completed' || observation.phase === 'observed')) {
    plan = completeSovereignPlanStep(
      plan,
      activeStep,
      observation.resultSummary ?? observation.argumentsSummary,
      observation.target,
      now,
    );
    status = summarizeSovereignPlan(plan).nextAllowedAction === 'finish_plan' ? 'finished' : 'running';
    blocker = undefined;
    error = undefined;
  }

  if (activeStep && observation.phase === 'blocked') {
    plan = blockSovereignPlanStep(
      plan,
      activeStep,
      observation.blocker ?? 'Tool blocked.',
      observation.resultSummary,
      now,
    );
    status = 'blocked';
    blocker = observation.blocker ?? 'Tool blocked.';
  }

  if (activeStep && observation.phase === 'failed') {
    plan = blockSovereignPlanStep(
      plan,
      activeStep,
      observation.blocker ?? observation.resultSummary ?? 'Tool failed.',
      observation.resultSummary,
      now,
    );
    status = 'error';
    error = observation.blocker ?? observation.resultSummary ?? 'Tool failed.';
  }

  const nextStep = getSovereignPlanNextStep(plan);
  const nextSession: SovereignExecutionSession = {
    ...session,
    status,
    plan,
    observations,
    currentStepId: nextStep?.id ?? null,
    blocker,
    error,
    updatedAt: now,
  };

  const stuck = detectSovereignExecutionStuck(nextSession);
  if (stuck.stuck) {
    const stuckSession = {
      ...nextSession,
      status: 'blocked' as const,
      blocker: stuck.reason,
      updatedAt: now,
    };
    return {
      session: stuckSession,
      nextAllowedAction: stuck.nextAllowedAction,
      event: sessionEvent({
        kind: 'blocked',
        label: 'Execution Session hängt',
        detail: stuck.reason,
        state: 'blocked',
        createdAt: now,
      }),
    };
  }

  return {
    session: nextSession,
    nextAllowedAction: deriveSovereignExecutionNextAction(nextSession),
    event: observation.event,
  };
}

export function deriveSovereignExecutionNextAction(
  session: SovereignExecutionSession,
): SovereignExecutionSessionNextAction {
  if (session.status === 'idle') return 'start_session';
  if (session.status === 'error') return 'show_error';
  if (session.status === 'blocked') return 'resolve_blocker';
  if (session.status === 'finished') return 'show_result';
  return summarizeSovereignPlan(session.plan).nextAllowedAction;
}

export function summarizeSovereignExecutionSession(session: SovereignExecutionSession): string {
  const planSummary = summarizeSovereignPlan(session.plan);
  const lastObservation = session.observations[session.observations.length - 1];

  return [
    `Session: ${session.id}`,
    `State: ${session.status}`,
    session.blocker ? `Blocker: ${session.blocker}` : '',
    session.error ? `Error: ${session.error}` : '',
    `Next allowed action: ${deriveSovereignExecutionNextAction(session)}`,
    lastObservation ? `Last observation: ${lastObservation.phase} ${lastObservation.toolName}` : 'Last observation: none',
    '',
    planSummary.text,
  ].filter(Boolean).join('\n');
}
