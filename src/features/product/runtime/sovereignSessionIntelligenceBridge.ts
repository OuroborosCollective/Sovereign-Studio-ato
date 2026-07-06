/**
 * Sovereign Session Intelligence Bridge
 *
 * Connects SovereignExecutionSession with:
 * - PredictiveLayer for neural signal processing
 * - containerDecisionLearning for outcome tracking
 *
 * Rule: This bridge does not create truth. It observes runtime truth
 * and feeds it to intelligence systems that learn from patterns.
 *
 * @module sovereignSessionIntelligenceBridge
 */

import type { SovereignExecutionSession } from './sovereignExecutionSessionRuntime';
import type { SovereignToolObservation } from './sovereignToolObservationRuntime';
import type { ContainerDecisionLearningSignal, LearningOutcome } from './containerDecisionLearning';

// Direct imports - lazy loading not needed since these don't cause circular deps
import { getDefaultPredictiveLayer } from '../../../predictive/predictiveLayer';
import {
  createContainerDecisionLearningSignal,
  applyContainerDecisionOutcome,
} from './containerDecisionLearning';

let predictiveLayerInstance: ReturnType<typeof getDefaultPredictiveLayer> | null = null;

function getPredictiveLayer() {
  if (!predictiveLayerInstance) {
    predictiveLayerInstance = getDefaultPredictiveLayer();
  }
  return predictiveLayerInstance;
}

// ============================================================================
// Node Definitions for Predictive Layer
// ============================================================================

/**
 * Simplified session node for intelligence layer
 */
export interface SovereignSessionNode {
  readonly id: string;
  readonly type: 'session';
  readonly activation: number;
  readonly metadata: {
    sessionId: string;
    status: SovereignExecutionSession['status'];
    blocker: string | null;
    currentStepId: string | null;
  };
}

/**
 * Simplified tool node for intelligence layer
 */
export interface SovereignToolNode {
  readonly id: string;
  readonly type: 'tool';
  readonly activation: number;
  readonly metadata: {
    toolName: string;
    route: string;
    phase: string;
  };
}

const SESSION_NODE_PREFIX = 'session';
const TOOL_NODE_PREFIX = 'tool';

/**
 * Creates a node for session-level signals
 */
export function createSovereignSessionNode(session: SovereignExecutionSession): SovereignSessionNode {
  return {
    id: `${SESSION_NODE_PREFIX}:${session.id}`,
    type: 'session',
    activation: session.status === 'running' ? 1 : session.status === 'idle' ? 0.5 : 0,
    metadata: {
      sessionId: session.id,
      status: session.status,
      blocker: session.blocker ?? null,
      currentStepId: session.currentStepId,
    },
  };
}

/**
 * Creates a node for tool-level signals
 */
export function createSovereignToolNode(
  toolName: string,
  route: string,
  phase: string,
): SovereignToolNode {
  const activation = phase === 'completed' ? 1 : phase === 'blocked' ? -1 : phase === 'failed' ? -0.5 : 0.3;
  return {
    id: `${TOOL_NODE_PREFIX}:${toolName}:${route}`,
    type: 'tool',
    activation,
    metadata: {
      toolName,
      route,
      phase,
    },
  };
}

// ============================================================================
// Signal Emission to Predictive Layer
// ============================================================================

/**
 * Session lifecycle signal types
 */
export type SovereignSessionSignalType =
  | 'session.created'
  | 'session.started'
  | 'session.blocked'
  | 'session.finished'
  | 'session.error'
  | 'session.stuck';

/**
 * Maps session status to signal value for predictive layer (exported for testing)
 */
export function sessionStatusToSignalValue(status: SovereignExecutionSession['status']): number {
  switch (status) {
    case 'finished':
      return 1;
    case 'running':
      return 0.7;
    case 'idle':
      return 0.5;
    case 'blocked':
      return -0.7;
    case 'error':
      return -1;
    default:
      return 0;
  }
}

/**
 * Maps observation phase to signal value (exported for testing)
 */
export function observationPhaseToSignalValue(
  phase: SovereignToolObservation['phase'],
): number {
  switch (phase) {
    case 'completed':
    case 'observed':
      return 1;
    case 'started':
      return 0.5;
    case 'selected':
      return 0.3;
    case 'failed':
      return -0.8;
    case 'blocked':
      return -1;
    default:
      return 0;
  }
}

/**
 * Emits session lifecycle signal to predictive layer
 */
export async function emitSovereignSessionSignal(
  session: SovereignExecutionSession,
  signalType: SovereignSessionSignalType,
): Promise<void> {
  try {
    const layer = await getPredictiveLayer();
    const value = sessionStatusToSignalValue(session.status);

    layer.emitSignal(
      signalType,
      value,
      {
        sessionId: session.id,
        status: session.status,
        blocker: session.blocker ?? undefined,
        currentStepId: session.currentStepId,
        timestamp: Date.now(),
      },
    );
  } catch {
    // Silently ignore predictive layer errors - intelligence is optional
  }
}

/**
 * Emits tool observation signal to predictive layer
 */
export async function emitSovereignToolSignal(
  observation: SovereignToolObservation,
): Promise<void> {
  try {
    const layer = await getPredictiveLayer();
    const value = observationPhaseToSignalValue(observation.phase);

    layer.emitSignal(
      `tool.${observation.phase}`,
      value,
      {
        toolName: observation.toolName,
        route: observation.route,
        target: observation.target ?? undefined,
        phase: observation.phase,
        blocker: observation.blocker ?? undefined,
        timestamp: observation.createdAt,
      },
    );
  } catch {
    // Silently ignore predictive layer errors - intelligence is optional
  }
}

/**
 * Emits blocker detection signal
 */
export async function emitSovereignBlockerSignal(
  session: SovereignExecutionSession,
  blocker: string,
  repeated: boolean,
): Promise<void> {
  try {
    const layer = await getPredictiveLayer();
    const value = repeated ? -1 : -0.5;

    layer.emitSignal(
      'blocker.detected',
      value,
      {
        sessionId: session.id,
        blocker,
        repeated,
        timestamp: Date.now(),
      },
    );
  } catch {
    // Silently ignore predictive layer errors
  }
}

// ============================================================================
// Learning Signal Generation
// ============================================================================

/**
 * Maps observation phase to learning outcome
 */
function observationPhaseToOutcome(phase: SovereignToolObservation['phase']): LearningOutcome | null {
  switch (phase) {
    case 'completed':
    case 'observed':
      return 'success';
    case 'failed':
      return 'failure';
    case 'blocked':
      return 'failure';
    default:
      return null;
  }
}

/**
 * Creates a container decision learning signal from tool observation
 */
export function createToolLearningSignal(
  session: SovereignExecutionSession,
  observation: SovereignToolObservation,
): ContainerDecisionLearningSignal | null {
  const outcome = observationPhaseToOutcome(observation.phase);
  if (!outcome) return null;

  const reason = observation.blocker
    ? `Tool ${observation.toolName} blocked: ${observation.blocker}`
    : observation.resultSummary
      ? `Tool ${observation.toolName} completed: ${observation.resultSummary}`
      : `Tool ${observation.toolName} ${observation.phase}`;

  const score = outcome === 'success' ? 1.0 : 0.0;
  const lamp = outcome === 'success' ? 'green' : 'red';
  const action = outcome === 'success' ? 'continue' : 'review';

  return createContainerDecisionLearningSignal(
    `session:${session.id}`,
    `tool:${observation.toolName}`,
    observation.toolName,
    action,
    lamp,
    score,
    outcome,
    reason,
    undefined,
    undefined,
  );
}

/**
 * Creates a learning signal for stuck detection
 */
export function createStuckLearningSignal(
  session: SovereignExecutionSession,
  reason: string,
): ContainerDecisionLearningSignal {
  return createContainerDecisionLearningSignal(
    `session:${session.id}`,
    'strategy:stuck-detection',
    'change_strategy',
    'ask-user',
    'yellow',
    0.0,
    'failure',
    `Session stuck: ${reason}`,
  );
}

/**
 * Creates a learning signal for successful strategy change
 */
export function createStrategyChangeLearningSignal(
  session: SovereignExecutionSession,
  fromStrategy: string,
  toStrategy: string,
): ContainerDecisionLearningSignal {
  return createContainerDecisionLearningSignal(
    `session:${session.id}`,
    `strategy:${fromStrategy}`,
    toStrategy,
    'learn',
    'green',
    1.0,
    'rewrite',
    `Strategy changed from ${fromStrategy} to ${toStrategy}`,
  );
}

// ============================================================================
// Learning Signal Application
// ============================================================================

/**
 * Applies all learning signals from session observation
 */
export function applySovereignToolLearning(
  session: SovereignExecutionSession,
  observation: SovereignToolObservation,
): void {
  const signal = createToolLearningSignal(session, observation);
  if (signal) {
    applyContainerDecisionOutcome(signal);
  }
}

/**
 * Applies stuck learning signal
 */
export function applySovereignStuckLearning(
  session: SovereignExecutionSession,
  reason: string,
): void {
  const signal = createStuckLearningSignal(session, reason);
  applyContainerDecisionOutcome(signal);
}

/**
 * Applies strategy change learning signal
 */
export function applySovereignStrategyChangeLearning(
  session: SovereignExecutionSession,
  fromStrategy: string,
  toStrategy: string,
): void {
  const signal = createStrategyChangeLearningSignal(session, fromStrategy, toStrategy);
  applyContainerDecisionOutcome(signal);
}

// ============================================================================
// Summary Generation
// ============================================================================

export interface SovereignSessionIntelligenceSummary {
  sessionId: string;
  predictive: {
    nodeCount: number;
    patternCount: number;
    avgConfidence: number;
  };
  learning: {
    totalSignals: number;
    successCount: number;
    failureCount: number;
    successRate: number;
  };
}

/**
 * Gets a summary of intelligence state for a session
 */
export async function getSovereignSessionIntelligenceSummary(
  session: SovereignExecutionSession,
): Promise<SovereignSessionIntelligenceSummary> {
  const { getContainerDecisionLearningStats } = await import('./containerDecisionLearning');
  const stats = getContainerDecisionLearningStats(`session:${session.id}`);

  let predictive = {
    nodeCount: 0,
    patternCount: 0,
    avgConfidence: 0,
  };

  try {
    const layer = await getPredictiveLayer();
    const snapshot = layer.getSnapshot();
    predictive = {
      nodeCount: snapshot.nodeCount,
      patternCount: snapshot.patternCount,
      avgConfidence: snapshot.avgConfidence,
    };
  } catch {
    // Predictive layer not available
  }

  return {
    sessionId: session.id,
    predictive,
    learning: {
      totalSignals: stats.total,
      successCount: stats.success,
      failureCount: stats.failure,
      successRate: stats.total > 0 ? (stats.success / stats.total) * 100 : 0,
    },
  };
}
