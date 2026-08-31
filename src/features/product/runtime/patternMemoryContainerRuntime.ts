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

  // ⚡ Bolt: Single-pass loop optimization replaces 4 multi-pass array operations (.filter() x 3 and .reduce())
  // to calculate active patterns, confidence breakdowns, and total hits without intermediate array allocations.
  let activePatterns = 0;
  let completedPatterns = 0;
  let reportedPatterns = 0;
  let totalHits = 0;

  for (const pattern of store.patterns) {
    if (pattern.status === 'active') {
      activePatterns += 1;
      if (pattern.confidence === 'completed') {
        completedPatterns += 1;
      } else if (pattern.confidence === 'reported') {
        reportedPatterns += 1;
      }
      totalHits += pattern.hits;
    }
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
