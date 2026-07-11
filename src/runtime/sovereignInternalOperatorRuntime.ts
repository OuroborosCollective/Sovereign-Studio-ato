import { defaultTraceIdProvider, globalTelemetry, type TraceIdProvider } from './RuntimeIntelligence';
import type { SovereignToolCapabilityRegistry } from '../features/product/runtime/sovereignToolCapabilityRuntime';

export type SovereignInternalOperatorRoute =
  | 'direct_patch'
  | 'internal_workspace'
  | 'agent_runtime'
  | 'internal_runtime_patch';

export type SovereignInternalOperatorStage =
  | 'repo_snapshot'
  | 'intent_plan'
  | 'patch_plan'
  | 'file_patch'
  | 'diff_guard'
  | 'test_selection'
  | 'draft_pr_gate';

export interface SovereignInternalOperatorSignal {
  readonly route: SovereignInternalOperatorRoute;
  readonly accepted: boolean;
  readonly weight?: number;
}

export interface SovereignInternalOperatorInput {
  readonly text: string;
  readonly capabilities: SovereignToolCapabilityRegistry;
  readonly candidatePath?: string;
  /** True only when a callable internal patch adapter is connected in the current runtime. */
  readonly internalRuntimePatchConfigured?: boolean;
  readonly signals?: readonly SovereignInternalOperatorSignal[];
  readonly traceIdProvider?: TraceIdProvider;
}

export interface SovereignInternalOperatorNode {
  readonly route: SovereignInternalOperatorRoute;
  readonly score: number;
  readonly available: boolean;
  readonly signals: readonly string[];
}

export interface SovereignInternalOperatorDecision {
  readonly state: 'allowed' | 'blocked';
  readonly route: SovereignInternalOperatorRoute | 'blocked';
  readonly reason: string;
  readonly nextAction: 'run_direct_patch' | 'start_workspace' | 'start_agent' | 'run_internal_operator' | 'show_blocker';
  readonly confidence: number;
  readonly stages: readonly SovereignInternalOperatorStage[];
  readonly traceId: string;
  readonly nodes: readonly SovereignInternalOperatorNode[];
  readonly learningDelta: number;
}

const DOC_TOKENS = ['readme', 'docs', 'dokumentation', 'changelog', 'titel'];
const CODE_TOKENS = ['baue', 'bauen', 'implementiere', 'runtime', 'workflow', 'backend', 'frontend', 'test'];

function hasAny(text: string, tokens: readonly string[]): boolean {
  return tokens.some((token) => text.includes(token));
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

function learn(route: SovereignInternalOperatorRoute, signals: readonly SovereignInternalOperatorSignal[]): number {
  const hits = signals.filter((signal) => signal.route === route);
  if (!hits.length) return 0;
  let sum = 0;
  let weightSum = 0;
  for (const hit of hits) {
    const weight = clamp(hit.weight ?? 0.5, 0, 1);
    weightSum += weight;
    sum += hit.accepted ? weight : -weight;
  }
  return weightSum === 0 ? 0 : clamp((sum / weightSum) * 0.12, -0.12, 0.12);
}

function stages(route: SovereignInternalOperatorRoute, complex: boolean): readonly SovereignInternalOperatorStage[] {
  if (route === 'direct_patch') return ['repo_snapshot', 'intent_plan', 'file_patch', 'diff_guard', 'draft_pr_gate'];
  const result: SovereignInternalOperatorStage[] = ['repo_snapshot', 'intent_plan', 'patch_plan', 'file_patch', 'diff_guard'];
  if (complex) result.push('test_selection');
  result.push('draft_pr_gate');
  return result;
}

function nextAction(route: SovereignInternalOperatorRoute): SovereignInternalOperatorDecision['nextAction'] {
  if (route === 'direct_patch') return 'run_direct_patch';
  if (route === 'internal_workspace') return 'start_workspace';
  if (route === 'agent_runtime') return 'start_agent';
  return 'run_internal_operator';
}

function reason(route: SovereignInternalOperatorRoute): string {
  if (route === 'direct_patch') return 'Interner Operator nutzt Direct Patch für kleine prüfbare Dateiänderungen.';
  if (route === 'internal_workspace') return 'Interner Operator nutzt den eigenen Workspace vor externen Brücken.';
  if (route === 'agent_runtime') return 'Sovereign Agent wird nur als optionale Brücke genutzt.';
  return 'Interner Sovereign Operator übernimmt Plan, Patch, Diff-Guard und Draft-PR-Gate ohne Sovereign Agent-Pflicht.';
}

export function decideSovereignInternalOperator(input: SovereignInternalOperatorInput): SovereignInternalOperatorDecision {
  const traceId = (input.traceIdProvider ?? defaultTraceIdProvider)();
  const lower = input.text.toLowerCase();
  const simpleDocs = hasAny(lower, DOC_TOKENS) && !hasAny(lower, CODE_TOKENS);
  const complex = hasAny(lower, CODE_TOKENS);
  const signals = input.signals ?? [];

  const nodes: SovereignInternalOperatorNode[] = [
    {
      route: 'direct_patch',
      score: simpleDocs ? 0.92 : input.candidatePath ? 0.62 : 0.35,
      available: input.capabilities.directPatch.canStart && input.capabilities.draftPr.canStart,
      signals: simpleDocs ? ['small-doc-change'] : input.candidatePath ? ['candidate-path'] : [],
    },
    {
      route: 'internal_workspace',
      score: complex ? 0.9 : 0.56,
      available: input.capabilities.workspace.canStart && input.capabilities.draftPr.canStart,
      signals: complex ? ['complex-work', 'own-workspace'] : ['own-workspace'],
    },
    {
      route: 'agent_runtime',
      score: complex ? 0.74 : 0.48,
      available: input.capabilities.agent.canStart && input.capabilities.draftPr.canStart,
      signals: input.capabilities.agent.canStart ? ['optional-bridge'] : [],
    },
    {
      route: 'internal_runtime_patch',
      score: complex ? 0.78 : 0.58,
      available: input.capabilities.directPatch.canStart && input.capabilities.draftPr.canStart,
      signals: ['sovereign-owned-runtime'],
    },
  ];

  if (!input.capabilities.repo.canStart || !input.capabilities.githubWrite.canStart || !input.capabilities.draftPr.canStart) {
    return {
      state: 'blocked',
      route: 'blocked',
      reason: !input.capabilities.repo.canStart
        ? input.capabilities.repo.reason
        : !input.capabilities.githubWrite.canStart
          ? input.capabilities.githubWrite.reason
          : input.capabilities.draftPr.reason,
      nextAction: 'show_blocker',
      confidence: 0,
      stages: [],
      traceId,
      nodes,
      learningDelta: 0,
    };
  }

  const selected = nodes
    .filter((node) => node.available)
    .sort((a, b) => (b.score + learn(b.route, signals)) - (a.score + learn(a.route, signals)))[0];

  if (!selected) {
    return {
      state: 'blocked',
      route: 'blocked',
      reason: 'Keine sichere interne Operator-Route verfügbar.',
      nextAction: 'show_blocker',
      confidence: 0,
      stages: [],
      traceId,
      nodes,
      learningDelta: 0,
    };
  }

  const learningDelta = learn(selected.route, signals);
  const decision: SovereignInternalOperatorDecision = {
    state: 'allowed',
    route: selected.route,
    reason: reason(selected.route),
    nextAction: nextAction(selected.route),
    confidence: clamp(selected.score + learningDelta, 0, 1),
    stages: stages(selected.route, complex),
    traceId,
    nodes,
    learningDelta,
  };

  globalTelemetry.track({
    name: 'sovereign_internal_operator_selected',
    properties: {
      route: decision.route,
      confidence: decision.confidence,
      stages: decision.stages.length,
    },
    timestamp: Date.now(),
    traceId,
  });

  return decision;
}
