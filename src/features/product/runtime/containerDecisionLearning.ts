export type LearningOutcome = 'accepted' | 'rejected' | 'rewrite' | 'repair' | 'success' | 'failure';

export interface ContainerDecisionLearningSignal {
  containerId: string;
  ruleId: string;
  learnTag: string;
  action: string;
  lamp: string;
  score: number;
  outcome: LearningOutcome;
  reason: string;
  timestamp: number;
  relatedTelemetryId?: string;
  relatedPatternId?: string;
}

export interface ContainerDecisionLearningReport {
  valid: boolean;
  errors: string[];
  summary: string;
}

const VALID_OUTCOMES: LearningOutcome[] = ['accepted', 'rejected', 'rewrite', 'repair', 'success', 'failure'];
const VALID_LAMPS = ['green', 'yellow', 'red'];
const VALID_ACTIONS = ['continue', 'ask-user', 'review', 'repair', 'learn'];

const SECRET_PATTERNS = [
  /token/i,
  /secret/i,
  /password/i,
  /api[_-]?key/i,
  /bearer/i,
  /ghp_[a-zA-Z0-9]{36}/,
  /gho_[a-zA-Z0-9]{36}/,
  /github[_-]?token/i,
  /private[_-]?key/i,
  /access[_-]?token/i,
];

function containsSecret(text: string): boolean {
  return SECRET_PATTERNS.some((pattern) => pattern.test(text));
}

export function validateContainerDecisionLearningSignal(signal: ContainerDecisionLearningSignal): ContainerDecisionLearningReport {
  const errors: string[] = [];
  if (!signal.containerId.trim()) errors.push('containerId required');
  if (!signal.ruleId.trim()) errors.push('ruleId required');
  if (!signal.learnTag.trim()) errors.push('learnTag required');
  if (!signal.action.trim()) errors.push('action required');
  if (!VALID_LAMPS.includes(signal.lamp)) errors.push(`lamp "${signal.lamp}" invalid. Valid: ${VALID_LAMPS.join(', ')}`);
  if (!VALID_ACTIONS.includes(signal.action)) errors.push(`action "${signal.action}" invalid. Valid: ${VALID_ACTIONS.join(', ')}`);
  if (!Number.isFinite(signal.score) || signal.score < 0) errors.push('score must be non-negative finite number');
  if (!VALID_OUTCOMES.includes(signal.outcome)) errors.push(`outcome "${signal.outcome}" invalid. Valid: ${VALID_OUTCOMES.join(', ')}`);
  if (!signal.reason.trim()) errors.push('reason required');
  if (containsSecret(signal.reason)) errors.push('reason must not contain secrets, tokens, or credentials');
  if (!Number.isFinite(signal.timestamp) || signal.timestamp <= 0) errors.push('timestamp must be positive finite number');
  if (signal.timestamp > Date.now() + 60000) errors.push('timestamp cannot be more than 1 minute in the future');
  return { valid: errors.length === 0, errors, summary: `${errors.length} learning signal error(s).` };
}

export interface ContainerDecisionLearningStats {
  accepted: number;
  rejected: number;
  success: number;
  failure: number;
  rewrite: number;
  repair: number;
  total: number;
}

export interface ContainerDecisionLearningHistory {
  signals: ContainerDecisionLearningSignal[];
  stats: ContainerDecisionLearningStats;
}

let learningHistory: ContainerDecisionLearningSignal[] = [];

export function createContainerDecisionLearningSignal(
  containerId: string,
  ruleId: string,
  learnTag: string,
  action: string,
  lamp: string,
  score: number,
  outcome: LearningOutcome,
  reason: string,
  relatedTelemetryId?: string,
  relatedPatternId?: string,
): ContainerDecisionLearningSignal {
  const signal: ContainerDecisionLearningSignal = {
    containerId,
    ruleId,
    learnTag,
    action,
    lamp,
    score,
    outcome,
    reason,
    timestamp: Date.now(),
    relatedTelemetryId,
    relatedPatternId,
  };
  const validation = validateContainerDecisionLearningSignal(signal);
  if (!validation.valid) {
    throw new Error(`Invalid learning signal: ${validation.errors.join(' | ')}`);
  }
  return signal;
}

export function applyContainerDecisionOutcome(signal: ContainerDecisionLearningSignal): void {
  const validation = validateContainerDecisionLearningSignal(signal);
  if (!validation.valid) {
    throw new Error(`Cannot apply invalid learning signal: ${validation.errors.join(' | ')}`);
  }
  learningHistory.push(signal);
  if (learningHistory.length > 500) {
    learningHistory = learningHistory.slice(-500);
  }
}

export function getContainerDecisionLearningHistory(): ContainerDecisionLearningSignal[] {
  return [...learningHistory];
}

export function summarizeContainerDecisionLearning(containerId?: string): string {
  const filtered = containerId ? learningHistory.filter((s) => s.containerId === containerId) : [...learningHistory];
  if (filtered.length === 0) {
    return containerId ? `No learning signals recorded for container: ${containerId}` : 'No learning signals recorded yet.';
  }
  const stats = filtered.reduce(
    (acc, signal) => {
      acc[signal.outcome]++;
      acc.total++;
      return acc;
    },
    { accepted: 0, rejected: 0, success: 0, failure: 0, rewrite: 0, repair: 0, total: 0 } as ContainerDecisionLearningStats,
  );
  const successRate = stats.total > 0 ? Math.round((stats.success / stats.total) * 100) : 0;
  const topTags = [...new Set(filtered.map((s) => s.learnTag))].slice(0, 5);
  const containerInfo = containerId ? `for container "${containerId}"` : 'across all containers';
  return `Learning summary ${containerInfo}: ${stats.total} signal(s) processed. Success rate: ${successRate}%. Tags: ${topTags.join(', ') || 'none'}.`;
}

export function resetContainerDecisionLearningHistory(): void {
  learningHistory = [];
}

export function getContainerDecisionLearningStats(containerId?: string): ContainerDecisionLearningStats {
  const filtered = containerId ? learningHistory.filter((s) => s.containerId === containerId) : [...learningHistory];
  return filtered.reduce(
    (acc, signal) => {
      acc[signal.outcome]++;
      acc.total++;
      return acc;
    },
    { accepted: 0, rejected: 0, success: 0, failure: 0, rewrite: 0, repair: 0, total: 0 } as ContainerDecisionLearningStats,
  );
}