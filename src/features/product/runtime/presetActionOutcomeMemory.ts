import {
  learnSolutionPattern,
  type SolutionPatternLearnResult,
  type SolutionPatternLearningInput,
  type SolutionPatternRejection,
  type SolutionPatternStore,
} from './solutionPatternMemory';
import type { SovereignPresetActionId } from './sovereignPresetActionRuntime';

export type PresetActionOutcomeStatus = 'success' | 'partial' | 'blocked' | 'failed';

export interface PresetActionOutcomeSignal {
  readonly actionId: SovereignPresetActionId;
  readonly status: PresetActionOutcomeStatus;
  readonly repoFullName?: string | null;
  readonly branch?: string | null;
  readonly targetPaths?: readonly string[];
  readonly summary: string;
  readonly proof?: string;
  readonly blocker?: string;
  readonly route?: string;
  readonly now?: number;
}

export interface PresetActionOutcomeMemoryResult {
  readonly accepted: boolean;
  readonly learned: boolean;
  readonly rejected: boolean;
  readonly store: SolutionPatternStore;
  readonly learningInput?: SolutionPatternLearningInput;
  readonly learnResult?: SolutionPatternLearnResult;
  readonly summary: string;
}

const ACTION_LABEL: Record<SovereignPresetActionId, string> = {
  architecture_feature_suggestions: 'architecture feature suggestions',
  error_fix_plan: 'error fix plan',
  docs_architecture_sync: 'docs architecture sync',
  runtime_hardening: 'runtime hardening',
  tests_gate_repair: 'tests gate repair',
  open_pr_review: 'open pr review',
};

function sanitizeSignalText(value = ''): string {
  return value
    .replace(/gh[pousr]_[A-Za-z0-9_]+/g, '<redacted-github-token>')
    .replace(/sk-[A-Za-z0-9_-]+/g, '<redacted-key>')
    .replace(/password\s*[:=]\s*\S+/gi, 'password=<redacted>')
    .trim()
    .slice(0, 1200);
}

function firstTargetPath(signal: PresetActionOutcomeSignal): string {
  return signal.targetPaths?.find((path) => path.trim()) ?? `${signal.actionId}.preset`;
}

function targetPaths(signal: PresetActionOutcomeSignal): string[] {
  const paths = Array.from(new Set((signal.targetPaths ?? []).map((path) => path.trim()).filter(Boolean)));
  return paths.length ? paths.slice(0, 16) : [firstTargetPath(signal)];
}

export function buildPresetActionOutcomeLearningInput(signal: PresetActionOutcomeSignal): SolutionPatternLearningInput {
  const paths = targetPaths(signal);
  const completed = signal.status === 'success';
  const partial = signal.status === 'partial';
  const summary = sanitizeSignalText(signal.summary);
  const route = sanitizeSignalText(signal.route ?? 'preset-action');
  const blocker = sanitizeSignalText(signal.blocker ?? '');

  return {
    intakeNode: 'action-builder',
    processingNode: 'learning-memory',
    outputNodes: ['action-builder', 'learning-memory', signal.status === 'success' ? 'telemetry' : 'workflow-repair-plan'],
    problem: {
      findingId: `preset-${signal.actionId}-${signal.status}`,
      category: 'learning-memory',
      severity: signal.status === 'failed' ? 'high' : signal.status === 'blocked' ? 'medium' : 'low',
      filePath: firstTargetPath(signal),
      description: `${ACTION_LABEL[signal.actionId]} outcome: ${summary || signal.status}`,
      beforeSnippet: blocker || undefined,
      contextPaths: paths,
      contextSignals: [
        'preset-action',
        signal.actionId,
        signal.status,
        route,
        signal.repoFullName ?? '',
        signal.branch ?? '',
      ].filter(Boolean),
    },
    fix: {
      summary: completed
        ? `Preset action succeeded: ${summary}`
        : partial
          ? `Preset action produced a partial result: ${summary}`
          : `Preset action did not produce a successful reusable solution: ${summary || blocker || signal.status}`,
      afterSnippet: signal.proof ? sanitizeSignalText(signal.proof) : undefined,
      changedFiles: paths,
      steps: [
        `Run preset action: ${ACTION_LABEL[signal.actionId]}`,
        `Route: ${route}`,
        completed ? 'Record proof-backed success.' : partial ? 'Record partial advisory outcome.' : 'Reject as non-success outcome.',
      ],
      completed,
      proof: completed ? sanitizeSignalText(signal.proof || summary || 'Runtime reported preset success.') : undefined,
    },
    confidence: completed ? 'completed' : partial ? 'reported' : 'reported',
    tags: ['preset-action', signal.actionId, signal.status, route],
    now: signal.now,
  };
}

export function recordPresetActionOutcome(
  store: SolutionPatternStore,
  signal: PresetActionOutcomeSignal,
): PresetActionOutcomeMemoryResult {
  const learningInput = buildPresetActionOutcomeLearningInput(signal);

  if (signal.status === 'blocked' || signal.status === 'failed') {
    const now = signal.now ?? Date.now();
    const rejection: SolutionPatternRejection = {
      id: `reject-preset-${signal.actionId}-${signal.status}-${now}`,
      reason: `Preset action ${signal.status}: ${sanitizeSignalText(signal.blocker || signal.summary || signal.actionId)}`,
      errors: [],
      warnings: ['Outcome was not a proof-backed success and must not increment successfulUses.'],
      intakeNode: learningInput.intakeNode,
      filePath: learningInput.problem.filePath,
      at: now,
    };
    return {
      accepted: false,
      learned: false,
      rejected: true,
      store: {
        ...store,
        rejections: [rejection, ...store.rejections].slice(0, 120),
        updatedAt: now,
      },
      learningInput,
      summary: `Solution pattern rejected: ${rejection.reason}`,
    };
  }

  const result = learnSolutionPattern(store, learningInput);
  return {
    accepted: result.accepted,
    learned: result.accepted,
    rejected: !result.accepted,
    store: result.store,
    learningInput,
    learnResult: result,
    summary: result.summary,
  };
}

export function buildPresetActionMemoryHint(store: SolutionPatternStore, actionId: SovereignPresetActionId): string {
  const matches = store.patterns
    .filter((pattern) => pattern.status === 'active' && pattern.tags.includes(actionId))
    .sort((a, b) => b.successfulUses - a.successfulUses || b.hits - a.hits)
    .slice(0, 3);

  if (!matches.length) return 'Noch kein bewiesenes Preset-Lernsignal.';
  return matches.map((pattern) => `${pattern.solutionSummary} (${pattern.successfulUses} Erfolg/e)`).join('\n');
}
