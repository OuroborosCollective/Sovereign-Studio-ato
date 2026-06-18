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
}

export interface ContainerDecisionReport {
  valid: boolean;
  errors: string[];
  summary: string;
}

const LAMPS: ContainerDecisionLamp[] = ['green', 'yellow', 'red'];
const ACTIONS: ContainerDecisionAction[] = ['continue', 'ask-user', 'review', 'repair', 'learn'];

export function validateContainerDecisionRule(rule: ContainerDecisionRule): ContainerDecisionReport {
  const errors: string[] = [];
  if (!rule.id.trim()) errors.push('id required');
  if (!rule.containerId.trim()) errors.push('containerId required');
  if (!Number.isFinite(rule.priority)) errors.push('priority must be finite');
  if (!LAMPS.includes(rule.lamp)) errors.push('lamp invalid');
  if (!ACTIONS.includes(rule.action)) errors.push('action invalid');
  if (!Array.isArray(rule.signals) || rule.signals.length === 0) errors.push('signals required');
  if (!Number.isFinite(rule.minScore) || rule.minScore < 1) errors.push('minScore must be positive');
  if (!rule.learnTag.trim()) errors.push('learnTag required');
  if (!rule.nextAction.trim()) errors.push('nextAction required');
  return { valid: errors.length === 0, errors, summary: `${errors.length} decision rule error(s).` };
}

export function assertContainerDecisionRulesValid(rules: ContainerDecisionRule[]): void {
  const errors = rules.flatMap((rule) => validateContainerDecisionRule(rule).errors.map((error) => `${rule.id || 'unknown'}: ${error}`));
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

export function decideContainerAction(containerId: string, visibleText: string, rules: ContainerDecisionRule[]): ContainerDecision {
  assertContainerDecisionRulesValid(rules);
  const source = visibleText.toLowerCase();
  const candidates = rules
    .filter((rule) => rule.containerId === containerId)
    .map((rule) => {
      if (rule.blockers?.some((token) => has(source, token))) return null;
      const score = rule.signals.filter((token) => has(source, token)).length;
      return score >= rule.minScore ? { rule, score } : null;
    })
    .filter((item): item is { rule: ContainerDecisionRule; score: number } => Boolean(item))
    .sort((a, b) => b.rule.priority - a.rule.priority || b.score - a.score);
  const top = candidates[0];
  if (!top) {
    return { ruleId: 'fallback', containerId, lamp: 'yellow', action: 'review', learnTag: `${containerId}.pattern-missing`, nextAction: 'summarize state and add a rule', score: 0 };
  }
  return { ruleId: top.rule.id, containerId, lamp: top.rule.lamp, action: top.rule.action, learnTag: top.rule.learnTag, nextAction: top.rule.nextAction, score: top.score };
}
