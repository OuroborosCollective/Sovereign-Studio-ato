export type SovereignPatchType = 'replace' | 'insert' | 'delete' | 'create';
export type SovereignSeverity = 'critical' | 'high' | 'medium' | 'low';
export type SovereignComplexity = 'trivial' | 'low' | 'medium' | 'high' | 'extreme';

export interface SovereignPatch {
  file: string;
  type: SovereignPatchType;
  description: string;
  code: string;
}

export interface SovereignBrainResult {
  perception: {
    domain: string;
    intent: string;
    architecture: string;
    confidence: number;
  };
  analysis: {
    severity: SovereignSeverity;
    issues: Array<{
      type: string;
      location: string;
      description: string;
      impact: string;
    }>;
    rootCause: string;
    systemicRisk: string;
  };
  plan: {
    strategy: string;
    phases: Array<{
      phase: number;
      name: string;
      actions: string[];
      rationale: string;
    }>;
    estimatedComplexity: SovereignComplexity;
  };
  execution: {
    patches: SovereignPatch[];
    integrationNotes: string;
    testStrategy: string;
  };
  learning: {
    patterns: string[];
    rules: string[];
    architectureUpgrade: string;
  };
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function nonEmpty(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function validSeverity(value: unknown): value is SovereignSeverity {
  return value === 'critical' || value === 'high' || value === 'medium' || value === 'low';
}

function validComplexity(value: unknown): value is SovereignComplexity {
  return value === 'trivial' || value === 'low' || value === 'medium' || value === 'high' || value === 'extreme';
}

function validPatchType(value: unknown): value is SovereignPatchType {
  return value === 'replace' || value === 'insert' || value === 'delete' || value === 'create';
}

export function parseSovereignBrainJson(raw: string): unknown {
  return JSON.parse(raw.replace(/```json|```/g, '').trim());
}

export function assertSovereignBrainResult(value: unknown): asserts value is SovereignBrainResult {
  if (!isObject(value)) throw new Error('Sovereign brain result must be an object.');
  const perception = value.perception;
  const analysis = value.analysis;
  const plan = value.plan;
  const execution = value.execution;
  const learning = value.learning;

  if (!isObject(perception) || !nonEmpty(perception.domain) || !nonEmpty(perception.intent) || !nonEmpty(perception.architecture)) {
    throw new Error('Invalid perception layer.');
  }
  if (typeof perception.confidence !== 'number' || perception.confidence < 0 || perception.confidence > 1) {
    throw new Error('Invalid perception confidence.');
  }
  if (!isObject(analysis) || !validSeverity(analysis.severity) || !Array.isArray(analysis.issues) || !nonEmpty(analysis.rootCause) || !nonEmpty(analysis.systemicRisk)) {
    throw new Error('Invalid analysis layer.');
  }
  if (!isObject(plan) || !nonEmpty(plan.strategy) || !Array.isArray(plan.phases) || !validComplexity(plan.estimatedComplexity)) {
    throw new Error('Invalid plan layer.');
  }
  if (!isObject(execution) || !Array.isArray(execution.patches) || !nonEmpty(execution.integrationNotes) || !nonEmpty(execution.testStrategy)) {
    throw new Error('Invalid execution layer.');
  }
  for (const patch of execution.patches) {
    if (!isObject(patch) || !nonEmpty(patch.file) || !validPatchType(patch.type) || !nonEmpty(patch.description) || !nonEmpty(patch.code)) {
      throw new Error('Invalid execution patch.');
    }
  }
  if (!isObject(learning) || !Array.isArray(learning.patterns) || !Array.isArray(learning.rules) || !nonEmpty(learning.architectureUpgrade)) {
    throw new Error('Invalid learning layer.');
  }
}

export function toImplementationFiles(result: SovereignBrainResult) {
  assertSovereignBrainResult(result);
  return result.execution.patches.map((patch) => ({ path: patch.file, content: patch.code, reason: patch.description }));
}
