/**
 * Risk Evidence Bundle Contract Tests
 */

import {
  validateRiskEvidenceBundle,
  validateBoundedActionPlan,
  generateRiskEvidenceBundleSchemaHash,
  generateBoundedActionPlanSchemaHash,
} from './riskEvidence';

describe('RiskEvidenceBundle Contract', () => {
  const validBundle = {
    schemaId: 'risk-evidence-bundle.v1',
    schemaVersion: 'v1',
    id: 'bundle-001',
    severity: 0.75,
    category: 'degradation',
    description: 'Memory pressure detected',
    evidence: [
      {
        type: 'signal',
        referenceId: 'sig-001',
        weight: 0.8,
        content: { metric: 'memory_usage', value: 0.92 },
      },
    ],
    predictedProbability: 0.65,
    timestamp: 1234567890,
    traceId: 'trace-abc',
  };

  describe('validateRiskEvidenceBundle', () => {
    it('accepts valid risk evidence bundle', () => {
      const result = validateRiskEvidenceBundle(validBundle);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('rejects non-object input', () => {
      const result = validateRiskEvidenceBundle(null);
      expect(result.valid).toBe(false);
    });

    it('rejects wrong schemaId', () => {
      const result = validateRiskEvidenceBundle({ ...validBundle, schemaId: 'wrong' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'schemaId')).toBe(true);
    });

    it('rejects severity out of range', () => {
      const result = validateRiskEvidenceBundle({ ...validBundle, severity: 1.5 });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'severity')).toBe(true);
    });

    it('rejects predictedProbability out of range', () => {
      const result = validateRiskEvidenceBundle({ ...validBundle, predictedProbability: -0.1 });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'predictedProbability')).toBe(true);
    });

    it('rejects invalid evidence type', () => {
      const result = validateRiskEvidenceBundle({
        ...validBundle,
        evidence: [{ type: 'invalid', referenceId: 'x', weight: 0.5, content: {} }],
      });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field.includes('evidence'))).toBe(true);
    });

    it('rejects evidence with weight out of range', () => {
      const result = validateRiskEvidenceBundle({
        ...validBundle,
        evidence: [{ type: 'signal', referenceId: 'x', weight: 2, content: {} }],
      });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field.includes('weight'))).toBe(true);
    });

    it('rejects unknown fields in strict mode', () => {
      const result = validateRiskEvidenceBundle({ ...validBundle, unknown: 'field' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'UNKNOWN_FIELD')).toBe(true);
    });

    it('accepts unknown fields in non-strict mode', () => {
      const result = validateRiskEvidenceBundle({ ...validBundle, unknown: 'field' }, { strict: false });
      expect(result.valid).toBe(true);
    });

    it('accepts optional causal fields', () => {
      const result = validateRiskEvidenceBundle({
        ...validBundle,
        tick: 100,
        sequence: 5,
        sourceRevision: 'abc123',
        runtimeRevision: 'def456',
      });
      expect(result.valid).toBe(true);
    });
  });
});

describe('BoundedActionPlan Contract', () => {
  const validPlan = {
    schemaId: 'bounded-action-plan.v1',
    schemaVersion: 'v1',
    id: 'plan-001',
    name: 'Reduce memory pressure',
    description: 'Scale down non-critical services',
    actions: [
      {
        actionId: 'action-001',
        type: 'write',
        target: 'service/worker',
        parameters: { replicas: 2 },
        maxExecutionTimeMs: 30000,
        requiresConfirmation: true,
      },
    ],
    preConditions: [
      { type: 'greaterThan', field: 'metrics.available_memory', expectedValue: 500 },
    ],
    postConditions: [
      { type: 'lessThan', field: 'metrics.memory_usage', expectedValue: 0.8 },
    ],
    reversible: true,
    scope: {
      allowedResourceTypes: ['service', 'deployment'],
      deniedResourceTypes: ['database', 'secret'],
      maxAffectedResources: 5,
      maxCost: 100,
      constraints: { environment: 'staging' },
    },
    riskBundleId: 'bundle-001',
    timestamp: 1234567890,
    traceId: 'trace-abc',
  };

  describe('validateBoundedActionPlan', () => {
    it('accepts valid action plan', () => {
      const result = validateBoundedActionPlan(validPlan);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('rejects non-object input', () => {
      const result = validateBoundedActionPlan(null);
      expect(result.valid).toBe(false);
    });

    it('rejects wrong schemaId', () => {
      const result = validateBoundedActionPlan({ ...validPlan, schemaId: 'wrong' });
      expect(result.valid).toBe(false);
    });

    it('rejects invalid action type', () => {
      const result = validateBoundedActionPlan({
        ...validPlan,
        actions: [{ ...validPlan.actions[0], type: 'delete' }],
      });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field.includes('type'))).toBe(true);
    });

    it('rejects non-positive maxExecutionTimeMs', () => {
      const result = validateBoundedActionPlan({
        ...validPlan,
        actions: [{ ...validPlan.actions[0], maxExecutionTimeMs: -1 }],
      });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field.includes('maxExecutionTimeMs'))).toBe(true);
    });

    it('rejects missing rollback plan on reversible plan', () => {
      const { rollbackPlan, ...planWithoutRollback } = validPlan;
      const result = validateBoundedActionPlan(planWithoutRollback);
      expect(result.valid).toBe(true);
      expect(result.warnings.some(w => w.field === 'rollbackPlan')).toBe(true);
    });

    it('rejects invalid scope', () => {
      const result = validateBoundedActionPlan({
        ...validPlan,
        scope: { ...validPlan.scope, maxAffectedResources: -1 },
      });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field.includes('scope'))).toBe(true);
    });

    it('rejects unknown fields in strict mode', () => {
      const result = validateBoundedActionPlan({ ...validPlan, unknown: 'field' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'UNKNOWN_FIELD')).toBe(true);
    });
  });
});

describe('Schema Hash Generation', () => {
  it('generates consistent hashes', () => {
    const hash1 = generateRiskEvidenceBundleSchemaHash();
    const hash2 = generateRiskEvidenceBundleSchemaHash();
    expect(hash1).toBe(hash2);
    expect(hash1).toMatch(/^s[0-9a-f]{8}$/);
  });

  it('generates different hashes for different schemas', () => {
    const hash1 = generateRiskEvidenceBundleSchemaHash();
    const hash2 = generateBoundedActionPlanSchemaHash();
    expect(hash1).not.toBe(hash2);
  });
});
