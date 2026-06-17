import {
  buildSolutionPatternRuntimeSummary,
  validateSolutionPatternStore,
  type SolutionPatternStore,
} from './solutionPatternMemory';

export interface PatternMemoryContainerState {
  valid: boolean;
  activePatterns: number;
  rejectedItems: number;
  completedPatterns: number;
  reportedPatterns: number;
  totalHits: number;
  summary: string;
}

export function derivePatternMemoryContainerState(store: SolutionPatternStore): PatternMemoryContainerState {
  const validation = validateSolutionPatternStore(store);
  const active = store.patterns.filter((pattern) => pattern.status === 'active');
  return {
    valid: validation.valid,
    activePatterns: active.length,
    rejectedItems: store.rejections.length,
    completedPatterns: active.filter((pattern) => pattern.confidence === 'completed').length,
    reportedPatterns: active.filter((pattern) => pattern.confidence === 'reported').length,
    totalHits: active.reduce((sum, pattern) => sum + pattern.hits, 0),
    summary: validation.valid ? buildSolutionPatternRuntimeSummary(store) : validation.summary,
  };
}

export function canClearPatternMemory(store: SolutionPatternStore): boolean {
  return store.patterns.length > 0 || store.rejections.length > 0;
}
