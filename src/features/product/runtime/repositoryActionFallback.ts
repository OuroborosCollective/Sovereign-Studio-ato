import { classifyOfflineCapabilityIntent } from './sovereignCapabilityRouter';

export type RepositoryActionFallbackIntent =
  | 'direct_patch'
  | 'code_execution'
  | 'draft_pr'
  | 'repair_workflow';

export interface RepositoryActionFallback {
  readonly intent: RepositoryActionFallbackIntent;
  readonly actionTitle: string;
}

/**
 * Degraded-only recovery for an online interpreter that returned no valid
 * action contract. Provider prose is never trusted or reused as action data.
 */
export function deriveRepositoryActionFallback(text: string): RepositoryActionFallback | null {
  const actionTitle = text.trim().replace(/\s+/g, ' ').slice(0, 180);
  if (!actionTitle) return null;

  switch (classifyOfflineCapabilityIntent(actionTitle)) {
    case 'direct_patch':
      return { intent: 'direct_patch', actionTitle };
    case 'code_generation':
      return { intent: 'code_execution', actionTitle };
    case 'draft_pr':
      return { intent: 'draft_pr', actionTitle };
    case 'repair_workflow':
      return { intent: 'repair_workflow', actionTitle };
    default:
      return null;
  }
}
