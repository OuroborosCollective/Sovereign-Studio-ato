export type ContainerDecisionLamp = 'green' | 'yellow' | 'red';
export type ContainerDecisionAction = 'continue' | 'ask-user' | 'review' | 'repair' | 'learn';

export interface ContainerDecisionRule {
  id: string;
  containerId: string;
  priority: number;
  lamp: ContainerDecisionLamp;
  action: ContainerDecisionAction;
  signals: string[];
  blockers?: string[];
  minScore: number;
  learnTag: string;
  nextAction: string;
}

export interface ContainerDecision {
  ruleId: string;
  containerId: string;
  lamp: ContainerDecisionLamp;
  action: ContainerDecisionAction;
  learnTag: string;
  nextAction: string;
  score: number;
  priority: number;
  matchedSignals: string[];
  confidence: number;
}

export interface ContainerDecisionReport {
  valid: boolean;
  errors: string[];
  summary: string;
}

const LAMPS: ContainerDecisionLamp[] = ['green', 'yellow', 'red'];
const ACTIONS: ContainerDecisionAction[] = ['continue', 'ask-user', 'review', 'repair', 'learn'];

export const KNOWN_CONTAINER_IDS: readonly string[] = [
  'repo-snapshot',
  'builder',
  'generated-files',
  'diff-preview',
  'workflow',
  'remote-memory',
  'pattern-memory',
  'telemetry',
  'health',
  'runtime-coverage',
  'findings',
  'sequential-runtime',
  'mobile-workbench',
  'mobile-coach',
  'code-creation',
];

export function validateContainerDecisionRule(rule: ContainerDecisionRule, knownContainerIds = KNOWN_CONTAINER_IDS): ContainerDecisionReport {
  const errors: string[] = [];
  if (!rule.id.trim()) errors.push('id required');
  if (!rule.containerId.trim()) errors.push('containerId required');
  else if (!knownContainerIds.includes(rule.containerId)) errors.push(`containerId "${rule.containerId}" unknown. Known: ${knownContainerIds.join(', ')}`);
  if (!Number.isFinite(rule.priority)) errors.push('priority must be finite');
  if (!LAMPS.includes(rule.lamp)) errors.push('lamp invalid');
  if (!ACTIONS.includes(rule.action)) errors.push('action invalid');
  if (!Array.isArray(rule.signals) || rule.signals.length === 0) errors.push('signals required');
  if (!Number.isFinite(rule.minScore) || rule.minScore < 1) errors.push('minScore must be positive');
  if (Array.isArray(rule.signals) && rule.signals.length > 0 && rule.minScore > rule.signals.length) {
    errors.push(`minScore ${rule.minScore} cannot exceed signal count ${rule.signals.length} unless explicitly allowed`);
  }
  if (!rule.learnTag.trim()) errors.push('learnTag required');
  if (!rule.nextAction.trim()) errors.push('nextAction required');
  if (Array.isArray(rule.signals) && Array.isArray(rule.blockers)) {
    const overlap = rule.signals.filter((s) => rule.blockers!.includes(s));
    if (overlap.length) errors.push(`signals and blockers cannot overlap: ${overlap.join(', ')}`);
  }
  return { valid: errors.length === 0, errors, summary: `${errors.length} decision rule error(s).` };
}

export function assertContainerDecisionRulesValid(rules: ContainerDecisionRule[], knownContainerIds = KNOWN_CONTAINER_IDS): void {
  const errors = rules.flatMap((rule) => validateContainerDecisionRule(rule, knownContainerIds).errors.map((error) => `${rule.id || 'unknown'}: ${error}`));
  const ids = new Set<string>();
  for (const rule of rules) {
    if (ids.has(rule.id)) errors.push(`duplicate id: ${rule.id}`);
    ids.add(rule.id);
  }
  if (errors.length) throw new Error(`Container decision rules invalid: ${errors.join(' | ')}`);
}

function has(source: string, token: string): boolean {
  return source.includes(token.toLowerCase());
}

function computeConfidence(score: number, signalCount: number): number {
  if (signalCount === 0) return 0;
  return Math.round((score / signalCount) * 100) / 100;
}

export function decideContainerAction(containerId: string, visibleText: string, rules: ContainerDecisionRule[]): ContainerDecision {
  assertContainerDecisionRulesValid(rules);
  const source = visibleText.toLowerCase();
  const candidates = rules
    .filter((rule) => rule.containerId === containerId)
    .map((rule) => {
      if (rule.blockers?.some((token) => has(source, token))) return null;
      const matchedSignals = rule.signals.filter((token) => has(source, token));
      const score = matchedSignals.length;
      return score >= rule.minScore ? { rule, score, matchedSignals } : null;
    })
    .filter((item): item is { rule: ContainerDecisionRule; score: number; matchedSignals: string[] } => Boolean(item))
    .sort((a, b) => b.rule.priority - a.rule.priority || b.score - a.score);
  const top = candidates[0];
  if (!top) {
    return {
      ruleId: 'fallback',
      containerId,
      lamp: 'yellow',
      action: 'review',
      learnTag: `${containerId}.pattern-missing`,
      nextAction: 'summarize state and add a rule',
      score: 0,
      priority: 0,
      matchedSignals: [],
      confidence: 0,
    };
  }
  return {
    ruleId: top.rule.id,
    containerId,
    lamp: top.rule.lamp,
    action: top.rule.action,
    learnTag: top.rule.learnTag,
    nextAction: top.rule.nextAction,
    score: top.score,
    priority: top.rule.priority,
    matchedSignals: top.matchedSignals,
    confidence: computeConfidence(top.score, top.rule.signals.length),
  };
}
