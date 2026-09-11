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
  let activePatterns = 0;
  let completedPatterns = 0;
  let reportedPatterns = 0;
  let totalHits = 0;

  for (const pattern of store.patterns) {
    if (pattern.status !== 'active') continue;
    activePatterns += 1;
    if (pattern.confidence === 'completed') completedPatterns += 1;
    else if (pattern.confidence === 'reported') reportedPatterns += 1;
    totalHits += pattern.hits;
  }

  return {
    valid: validation.valid,
    activePatterns,
    rejectedItems: store.rejections.length,
    completedPatterns,
    reportedPatterns,
    totalHits,
    summary: validation.valid ? buildSolutionPatternRuntimeSummary(store) : validation.summary,
  };
}

export function canClearPatternMemory(store: SolutionPatternStore): boolean {
  return store.patterns.length > 0 || store.rejections.length > 0;
}
