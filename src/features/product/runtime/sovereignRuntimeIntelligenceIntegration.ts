/**
 * Sovereign Runtime Intelligence Integration
 *
 * Hooks SovereignExecutionSession into Runtime Intelligence:
 * - PredictiveLayer signals for session/tool lifecycle
 * - DecisionLearning for outcome tracking
 * - Blocker pattern recognition
 *
 * Rule: This integration does not create truth. It observes runtime truth
 * and feeds it to intelligence systems.
 *
 * @module sovereignRuntimeIntelligenceIntegration
 */

import type { SovereignExecutionSession } from './sovereignExecutionSessionRuntime';
import type { SovereignToolObservation } from './sovereignToolObservationRuntime';
import type { ContainerDecisionLearningStats } from './containerDecisionLearning';
import type { PredictiveLayerSnapshot } from '../../../predictive/types';

// Lazy imports to avoid circular dependencies and keep intelligence optional
let bridgeModule: typeof import('./sovereignSessionIntelligenceBridge') | null = null;
let decisionLearningModule: typeof import('./containerDecisionLearning') | null = null;
let predictiveModule: typeof import('../../../predictive/predictiveLayer') | null = null;

function getBridge() {
  if (!bridgeModule) {
    bridgeModule = require('./sovereignSessionIntelligenceBridge');
  }
  return bridgeModule;
}

function getDecisionLearning() {
  if (!decisionLearningModule) {
    decisionLearningModule = require('./containerDecisionLearning');
  }
  return decisionLearningModule;
}

async function getPredictiveLayer() {
  if (!predictiveModule) {
    predictiveModule = await import('../../../predictive/predictiveLayer');
  }
  return predictiveModule;
}

// ============================================================================
// Integration Hooks
// ============================================================================

/**
 * Called after session is created. Emits session lifecycle signal.
 */
export async function onSessionCreated(session: SovereignExecutionSession): Promise<void> {
  try {
    const bridge = getBridge();
    await bridge.emitSovereignSessionSignal(session, 'session.created');
  } catch {
    // Intelligence is optional - silently ignore errors
  }
}

/**
 * Called after session is started. Emits session lifecycle signal.
 */
export async function onSessionStarted(session: SovereignExecutionSession): Promise<void> {
  try {
    const bridge = getBridge();
    await bridge.emitSovereignSessionSignal(session, 'session.started');
  } catch {
    // Intelligence is optional
  }
}

/**
 * Called after tool observation. Emits tool signal and records learning outcome.
 */
export async function onToolObservation(
  session: SovereignExecutionSession,
  observation: SovereignToolObservation,
): Promise<void> {
  try {
    const bridge = getBridge();

    // Emit signal to predictive layer
    await bridge.emitSovereignToolSignal(observation);

    // Record learning outcome (only for terminal phases)
    if (observation.phase === 'completed' || observation.phase === 'failed' || observation.phase === 'blocked') {
      bridge.applySovereignToolLearning(session, observation);
    }
  } catch {
    // Intelligence is optional
  }
}

/**
 * Called when session becomes blocked.
 */
export async function onSessionBlocked(session: SovereignExecutionSession): Promise<void> {
  try {
    const bridge = getBridge();
    await bridge.emitSovereignSessionSignal(session, 'session.blocked');
  } catch {
    // Intelligence is optional
  }
}

/**
 * Called when session finishes successfully.
 */
export async function onSessionFinished(session: SovereignExecutionSession): Promise<void> {
  try {
    const bridge = getBridge();
    await bridge.emitSovereignSessionSignal(session, 'session.finished');
  } catch {
    // Intelligence is optional
  }
}

/**
 * Called when session encounters an error.
 */
export async function onSessionError(session: SovereignExecutionSession): Promise<void> {
  try {
    const bridge = getBridge();
    await bridge.emitSovereignSessionSignal(session, 'session.error');
  } catch {
    // Intelligence is optional
  }
}

/**
 * Called when stuck detection triggers.
 */
export async function onSessionStuck(session: SovereignExecutionSession, reason: string): Promise<void> {
  try {
    const bridge = getBridge();
    await bridge.emitSovereignSessionSignal(session, 'session.stuck');
    bridge.applySovereignStuckLearning(session, reason);
  } catch {
    // Intelligence is optional
  }
}

/**
 * Called when strategy changes (e.g., from sovereign-agent to direct-patch).
 */
export async function onStrategyChange(
  session: SovereignExecutionSession,
  fromStrategy: string,
  toStrategy: string,
): Promise<void> {
  try {
    const bridge = getBridge();
    bridge.applySovereignStrategyChangeLearning(session, fromStrategy, toStrategy);
  } catch {
    // Intelligence is optional
  }
}

// ============================================================================
// Intelligence Stats
// ============================================================================

export interface SovereignIntelligenceStats {
  predictive: {
    active: boolean;
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
 * Gets current intelligence statistics.
 */
export async function getSovereignIntelligenceStats(): Promise<SovereignIntelligenceStats> {
  let predictive = {
    active: false,
    nodeCount: 0,
    patternCount: 0,
    avgConfidence: 0,
  };

  let learning = {
    totalSignals: 0,
    successCount: 0,
    failureCount: 0,
    successRate: 0,
  };

  try {
    // Get predictive layer stats
    const predModule = await getPredictiveLayer();
    const layer = predModule.getDefaultPredictiveLayer();
    const snapshot = layer.getSnapshot();
    predictive = {
      active: snapshot.active,
      nodeCount: snapshot.nodeCount,
      patternCount: snapshot.patternCount,
      avgConfidence: snapshot.avgConfidence,
    };
  } catch {
    // Predictive layer not available
  }

  try {
    // Get decision learning stats
    const dl = getDecisionLearning();
    const stats = dl.getContainerDecisionLearningStats() as ContainerDecisionLearningStats;
    learning = {
      totalSignals: stats.total,
      successCount: stats.success,
      failureCount: stats.failure,
      successRate: stats.total > 0 ? (stats.success / stats.total) * 100 : 0,
    };
  } catch {
    // Decision learning not available
  }

  return { predictive, learning };
}

/**
 * Formats intelligence stats as a compact string for display.
 */
export function formatIntelligenceStatsCompact(stats: SovereignIntelligenceStats): string {
  const parts: string[] = [];

  if (stats.predictive.active) {
    parts.push(`${stats.predictive.nodeCount} Nodes`);
    parts.push(`${stats.predictive.patternCount} Patterns`);
    parts.push(`${(stats.predictive.avgConfidence * 100).toFixed(0)}% Conf`);
  }

  if (stats.learning.totalSignals > 0) {
    parts.push(`${stats.learning.totalSignals} Signals`);
    parts.push(`${stats.learning.successRate.toFixed(0)}% Success`);
  }

  return parts.length > 0 ? `🧠 ${parts.join(' | ')}` : '';
}

// ============================================================================
// Blocker Pattern Recognition
// ============================================================================

export interface SovereignBlockerPattern {
  readonly blockerText: string;
  readonly occurrenceCount: number;
  readonly lastSeen: number;
  readonly suggestedResolution?: string;
}

/**
 * Analyzes recent observations for blocker patterns.
 */
export function detectBlockerPatterns(
  observations: readonly SovereignToolObservation[],
  recentCount = 10,
): SovereignBlockerPattern[] {
  const recent = observations.slice(-recentCount).filter((o) => o.blocker);
  const patternMap = new Map<string, { count: number; lastSeen: number }>();

  for (const obs of recent) {
    if (obs.blocker) {
      const existing = patternMap.get(obs.blocker);
      if (existing) {
        existing.count++;
        existing.lastSeen = Math.max(existing.lastSeen, obs.createdAt);
      } else {
        patternMap.set(obs.blocker, { count: 1, lastSeen: obs.createdAt });
      }
    }
  }

  return Array.from(patternMap.entries())
    .map(([blockerText, data]) => ({
      blockerText,
      occurrenceCount: data.count,
      lastSeen: data.lastSeen,
    }))
    .sort((a, b) => b.occurrenceCount - a.occurrenceCount);
}

// ============================================================================
// Session Health Indicator
// ============================================================================

export type SovereignSessionHealth = 'healthy' | 'warning' | 'critical';

export interface SovereignSessionHealthReport {
  readonly health: SovereignSessionHealth;
  readonly reason: string;
  readonly recommendations: readonly string[];
}

/**
 * Analyzes session state and returns health report.
 */
export function getSessionHealth(session: SovereignExecutionSession): SovereignSessionHealthReport {
  const recommendations: string[] = [];
  let health: SovereignSessionHealth = 'healthy';
  let reason = 'Session läuft normal.';

  if (session.status === 'blocked') {
    health = 'warning';
    reason = session.blocker ?? 'Session ist blockiert.';
    recommendations.push('Strategie überprüfen');
    recommendations.push('Fehlende Voraussetzungen identifizieren');
  }

  if (session.status === 'error') {
    health = 'critical';
    reason = session.error ?? 'Session hat einen Fehler.';
    recommendations.push('Fehler analysieren');
    recommendations.push('Alternative Strategie wählen');
  }

  // Check for repeated blockers
  const blockerPatterns = detectBlockerPatterns(session.observations);
  const repeatedBlockers = blockerPatterns.filter((p) => p.occurrenceCount > 2);
  if (repeatedBlockers.length > 0 && health !== 'critical') {
    health = 'warning';
    reason = `Wiederholter Blocker: ${repeatedBlockers[0].blockerText}`;
    recommendations.push('Strategie wechseln');
    recommendations.push('Ähnliche Sessions analysieren');
  }

  return { health, reason, recommendations };
}
