import type { ContainerDecisionRule } from './containerDecisionGrammar';

export const CONTAINER_DECISION_IDS = [
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
] as const;

export type ContainerDecisionId = typeof CONTAINER_DECISION_IDS[number];

export function createBaselineContainerDecisionRules(ids: readonly string[] = CONTAINER_DECISION_IDS): ContainerDecisionRule[] {
  return ids.flatMap((containerId) => [
    {
      id: `${containerId}:ready`,
      containerId,
      priority: 50,
      lamp: 'green' as const,
      action: 'continue' as const,
      signals: [`${containerId} ready`, `${containerId} ok`],
      minScore: 1,
      learnTag: `${containerId}.ready`,
      nextAction: 'continue guided flow',
    },
    {
      id: `${containerId}:review`,
      containerId,
      priority: 40,
      lamp: 'yellow' as const,
      action: 'review' as const,
      signals: [`${containerId} review`, `${containerId} needs attention`],
      minScore: 1,
      learnTag: `${containerId}.review`,
      nextAction: 'show concise review guidance',
    },
  ] satisfies ContainerDecisionRule[]);
}
