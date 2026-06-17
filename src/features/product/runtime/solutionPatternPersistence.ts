import {
  createSolutionPatternStore,
  validateSolutionPatternStore,
  type SolutionPatternStore,
  type SolutionPatternValidationReport,
} from './solutionPatternMemory';

export const SOLUTION_PATTERN_STORAGE_KEY = 'sovereign_solution_pattern_store_v1' as const;

export interface SolutionPatternPersistenceResult {
  ok: boolean;
  store: SolutionPatternStore;
  validation: SolutionPatternValidationReport;
  summary: string;
}

function validReport(summary: string): SolutionPatternValidationReport {
  return { valid: true, errors: [], warnings: [], summary };
}

function invalidReport(summary: string): SolutionPatternValidationReport {
  return { valid: false, errors: [summary], warnings: [], summary };
}

export function saveSolutionPatternStore(storage: Pick<Storage, 'setItem'>, store: SolutionPatternStore): SolutionPatternPersistenceResult {
  const validation = validateSolutionPatternStore(store);
  if (!validation.valid) return { ok: false, store, validation, summary: `Aha memory not saved: ${validation.summary}` };

  try {
    storage.setItem(SOLUTION_PATTERN_STORAGE_KEY, JSON.stringify(store));
    return { ok: true, store, validation, summary: `Aha memory saved with ${store.patterns.length} pattern(s).` };
  } catch (error) {
    return {
      ok: false,
      store,
      validation: invalidReport(error instanceof Error ? error.message : 'Aha memory save failed.'),
      summary: 'Aha memory save failed.',
    };
  }
}

export function loadSolutionPatternStore(storage: Pick<Storage, 'getItem'>, now = Date.now()): SolutionPatternPersistenceResult {
  try {
    const raw = storage.getItem(SOLUTION_PATTERN_STORAGE_KEY);
    if (!raw) {
      const store = createSolutionPatternStore(now);
      return { ok: true, store, validation: validReport('No local Aha memory stored yet.'), summary: 'No local Aha memory stored yet.' };
    }

    const parsed = JSON.parse(raw) as SolutionPatternStore;
    const validation = validateSolutionPatternStore(parsed);
    if (!validation.valid) {
      const store = createSolutionPatternStore(now);
      return { ok: false, store, validation, summary: `Stored Aha memory ignored: ${validation.summary}` };
    }

    return { ok: true, store: parsed, validation, summary: `Aha memory loaded with ${parsed.patterns.length} pattern(s).` };
  } catch (error) {
    const store = createSolutionPatternStore(now);
    return {
      ok: false,
      store,
      validation: invalidReport(error instanceof Error ? error.message : 'Aha memory load failed.'),
      summary: 'Aha memory load failed.',
    };
  }
}

export function clearSolutionPatternStore(storage: Pick<Storage, 'removeItem'>, now = Date.now()): SolutionPatternPersistenceResult {
  try {
    storage.removeItem(SOLUTION_PATTERN_STORAGE_KEY);
    const store = createSolutionPatternStore(now);
    return { ok: true, store, validation: validReport('Local Aha memory cleared.'), summary: 'Local Aha memory cleared.' };
  } catch (error) {
    const store = createSolutionPatternStore(now);
    return {
      ok: false,
      store,
      validation: invalidReport(error instanceof Error ? error.message : 'Aha memory clear failed.'),
      summary: 'Aha memory clear failed.',
    };
  }
}
