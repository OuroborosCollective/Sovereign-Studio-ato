import type { ContainerDecisionRule } from './containerDecisionGrammar';
import { KNOWN_CONTAINER_IDS } from './containerDecisionGrammar';

export const CONTAINER_DECISION_IDS = KNOWN_CONTAINER_IDS;

export type ContainerDecisionId = typeof CONTAINER_DECISION_IDS[number];

export function createBaselineContainerDecisionRules(ids: readonly string[] = CONTAINER_DECISION_IDS): ContainerDecisionRule[] {
  return ids.flatMap((containerId) => [
    {
      id: `${containerId}:ready`,
      containerId,
      priority: 50,
      lamp: 'green' as const,
      action: 'continue' as const,
      signals: [`${containerId} ready`, `${containerId} ok`, `${containerId} green`],
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
      signals: [`${containerId} review`, `${containerId} needs attention`, `${containerId} warning`],
      minScore: 1,
      learnTag: `${containerId}.review`,
      nextAction: 'show concise review guidance',
    },
    {
      id: `${containerId}:repair`,
      containerId,
      priority: 30,
      lamp: 'red' as const,
      action: 'repair' as const,
      signals: [`${containerId} red`, `${containerId} failed`, `${containerId} error`],
      minScore: 1,
      learnTag: `${containerId}.repair`,
      nextAction: 'prepare repair plan and show repair guidance',
    },
  ] satisfies ContainerDecisionRule[]);
}
