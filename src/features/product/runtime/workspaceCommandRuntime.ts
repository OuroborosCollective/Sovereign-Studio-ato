import {
  runtimeIntelligence,
  type RuntimeDecision,
} from '../../../runtime';
import type { ContainerDecisionRule } from './containerDecisionGrammar';

export type WorkspaceCommandTab =
  | 'builder'
  | 'repo'
  | 'files'
  | 'diff'
  | 'workflow'
  | 'repair'
  | 'remote'
  | 'memory'
  | 'telemetry'
  | 'monitor'
  | 'health'
  | 'runtime'
  | 'coverage'
  | 'findings';

export interface WorkspaceCommandDetail {
  type: 'next';
  targetTab: WorkspaceCommandTab;
  runtimeTraceId: string;
  runtimeContainerId: 'mobile-workbench';
  runtimeDecision: RuntimeDecision['decision']['action'];
  runtimeLamp: RuntimeDecision['decision']['lamp'];
}

export const WORKSPACE_COMMAND_TABS: readonly WorkspaceCommandTab[] = [
  'builder',
  'repo',
  'files',
  'diff',
  'workflow',
  'repair',
  'remote',
  'memory',
  'telemetry',
  'monitor',
  'health',
  'runtime',
  'coverage',
  'findings',
] as const;

const WORKSPACE_COMMAND_RULES: ContainerDecisionRule[] = [
  {
    id: 'mobile-workbench.workspace-primary-command',
    containerId: 'mobile-workbench',
    priority: 100,
    lamp: 'green',
    action: 'continue',
    signals: ['builder', 'repo', 'files', 'diff'],
    minScore: 1,
    learnTag: 'workspace-command.primary',
    nextAction: 'dispatch primary workspace navigation command',
  },
  {
    id: 'mobile-workbench.workspace-work-command',
    containerId: 'mobile-workbench',
    priority: 90,
    lamp: 'green',
    action: 'continue',
    signals: ['workflow', 'repair', 'remote', 'monitor'],
    minScore: 1,
    learnTag: 'workspace-command.work',
    nextAction: 'dispatch work workspace navigation command',
  },
  {
    id: 'mobile-workbench.workspace-ops-command',
    containerId: 'mobile-workbench',
    priority: 80,
    lamp: 'green',
    action: 'continue',
    signals: ['memory', 'telemetry', 'health', 'runtime', 'coverage', 'findings'],
    minScore: 1,
    learnTag: 'workspace-command.ops',
    nextAction: 'dispatch diagnostic workspace navigation command',
  },
];

export function isWorkspaceCommandTab(value: string): value is WorkspaceCommandTab {
  return WORKSPACE_COMMAND_TABS.includes(value as WorkspaceCommandTab);
}

export function decideWorkspaceCommand(targetTab: WorkspaceCommandTab): RuntimeDecision {
  return runtimeIntelligence.decide(
    'mobile-workbench',
    `workspace command target ${targetTab}`,
    WORKSPACE_COMMAND_RULES,
  );
}

export function createWorkspaceCommandDetail(targetTab: WorkspaceCommandTab): WorkspaceCommandDetail {
  const decision = decideWorkspaceCommand(targetTab);

  return {
    type: 'next',
    targetTab,
    runtimeTraceId: decision.context.traceId,
    runtimeContainerId: 'mobile-workbench',
    runtimeDecision: decision.decision.action,
    runtimeLamp: decision.decision.lamp,
  };
}
