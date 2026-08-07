/**
 * Risk Evidence Bundle Contract - Runtime validation for risk evidence
 * 
 * Schema definitions for:
 * - risk-evidence-bundle.v1: Aggregated risk evidence from predictive analysis
 * - bounded-action-plan.v1: Action plans with bounded scope and reversibility
 * 
 * @module predictive/contracts/riskEvidence
 */

// ============================================================================
// Schema Identifiers
// ============================================================================

export const RISK_EVIDENCE_BUNDLE_SCHEMA_ID = 'risk-evidence-bundle.v1';
export const BOUNDED_ACTION_PLAN_SCHEMA_ID = 'bounded-action-plan.v1';

// ============================================================================
// Validation Result Types
// ============================================================================

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
}

export interface ValidationError {
  field: string;
  code: string;
  message: string;
}

export interface ValidationWarning {
  field: string;
  message: string;
}

// ============================================================================
// Risk Evidence Bundle Contract
// ============================================================================

export interface RiskEvidenceBundleContract {
  /** Schema identifier */
  schemaId: string;
  /** Schema version */
  schemaVersion: string;
  /** Unique identifier for this bundle */
  id: string;
  /** Severity level [0, 1] */
  severity: number;
  /** Category of risk */
  category: string;
  /** Human-readable description */
  description: string;
  /** Evidence items that contributed to this risk */
  evidence: RiskEvidenceItem[];
  /** Predicted probability of failure [0, 1] */
  predictedProbability: number;
  /** Timestamp when bundle was created */
  timestamp: number;
  /** Trace context */
  traceId: string;
  /** Source revision */
  sourceRevision?: string;
  /** Runtime revision */
  runtimeRevision?: string;
  /** Causal tick */
  tick?: number;
  /** Causal sequence */
  sequence?: number;
}

export interface RiskEvidenceItem {
  /** Type of evidence */
  type: 'signal' | 'prediction' | 'error' | 'model' | 'scann' | 'wolfram';
  /** Reference to the evidence source */
  referenceId: string;
  /** Weight of this evidence [0, 1] */
  weight: number;
  /** Content of the evidence */
  content: Record<string, unknown>;
}

// ============================================================================
// Bounded Action Plan Contract
// ============================================================================

export interface BoundedActionPlanContract {
  /** Schema identifier */
  schemaId: string;
  /** Schema version */
  schemaVersion: string;
  /** Unique identifier for this plan */
  id: string;
  /** Human-readable name */
  name: string;
  /** Plan description */
  description: string;
  /** Actions to take */
  actions: BoundedAction[];
  /** Pre-conditions that must be met */
  preConditions: PreCondition[];
  /** Post-conditions that verify success */
  postConditions: PostCondition[];
  /** Whether this plan is reversible */
  reversible: boolean;
  /** Rollback plan if reversible */
  rollbackPlan?: BoundedActionPlanContract;
  /** Scope boundaries */
  scope: ActionScope;
  /** Risk bundle that triggered this plan */
  riskBundleId: string;
  /** Timestamp */
  timestamp: number;
  /** Trace context */
  traceId: string;
  /** Owner/approver */
  owner?: string;
  /** Source revision */
  sourceRevision?: string;
  /** Runtime revision */
  runtimeRevision?: string;
  /** Causal tick */
  tick?: number;
  /** Causal sequence */
  sequence?: number;
}

export interface BoundedAction {
  /** Action identifier */
  actionId: string;
  /** Action type */
  type: 'read' | 'write' | 'mutate' | 'deploy' | 'rollback';
  /** Target of the action */
  target: string;
  /** Parameters for the action */
  parameters: Record<string, unknown>;
  /** Maximum execution time in ms */
  maxExecutionTimeMs: number;
  /** Whether this action requires confirmation */
  requiresConfirmation: boolean;
}

export interface PreCondition {
  /** Condition type */
  type: 'exists' | 'equals' | 'greaterThan' | 'lessThan' | 'matches' | 'custom';
  /** Field to check */
  field: string;
  /** Expected value */
  expectedValue?: unknown;
  /** Custom validator code */
  validatorCode?: string;
}

export interface PostCondition {
  /** Condition type */
  type: 'exists' | 'equals' | 'greaterThan' | 'lessThan' | 'matches' | 'readback';
  /** Field to check */
  field: string;
  /** Expected value */
  expectedValue?: unknown;
  /** Readback query if type is readback */
  readbackQuery?: string;
  /** Timeout for verification */
  verificationTimeoutMs?: number;
}

export interface ActionScope {
  /** Allowed resource types */
  allowedResourceTypes: string[];
  /** Denied resource types */
  deniedResourceTypes: string[];
  /** Maximum affected resources */
  maxAffectedResources: number;
  /** Maximum cost/duration */
  maxCost: number;
  /** Geographic/environmental constraints */
  constraints: Record<string, unknown>;
}

// ============================================================================
// Validation
// ============================================================================

/**
 * Validate a risk evidence bundle contract.
 */
export function validateRiskEvidenceBundle(
  obj: unknown,
  options: { strict?: boolean } = {}
): ValidationResult {
  const { strict = true } = options;
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];

  if (typeof obj !== 'object' || obj === null) {
    return {
      valid: false,
      errors: [{
        field: 'root',
        code: 'INVALID_TYPE',
        message: 'RiskEvidenceBundle must be a non-null object',
      }],
      warnings: [],
    };
  }

  const b = obj as Record<string, unknown>;

  // Schema validation
  if (b.schemaId !== RISK_EVIDENCE_BUNDLE_SCHEMA_ID) {
    errors.push({
      field: 'schemaId',
      code: 'INVALID_SCHEMA',
      message: `Expected "${RISK_EVIDENCE_BUNDLE_SCHEMA_ID}"`,
    });
  }

  if (typeof b.schemaVersion !== 'string' || !b.schemaVersion.startsWith('v')) {
    errors.push({
      field: 'schemaVersion',
      code: 'INVALID_VERSION',
      message: 'schemaVersion must start with "v"',
    });
  }

  // Required fields
  for (const field of ['id', 'category', 'description', 'traceId']) {
    if (typeof b[field] !== 'string' || (b[field] as string).length === 0) {
      errors.push({
        field,
        code: 'MISSING_OR_EMPTY',
        message: `${field} must be a non-empty string`,
      });
    }
  }

  // Severity
  if (typeof b.severity !== 'number' || b.severity < 0 || b.severity > 1) {
    errors.push({
      field: 'severity',
      code: 'OUT_OF_RANGE',
      message: 'severity must be between 0 and 1',
    });
  }

  // Predicted probability
  if (typeof b.predictedProbability !== 'number' || b.predictedProbability < 0 || b.predictedProbability > 1) {
    errors.push({
      field: 'predictedProbability',
      code: 'OUT_OF_RANGE',
      message: 'predictedProbability must be between 0 and 1',
    });
  }

  // Timestamp
  if (typeof b.timestamp !== 'number' || b.timestamp < 0) {
    errors.push({
      field: 'timestamp',
      code: 'INVALID_TYPE',
      message: 'timestamp must be a non-negative number',
    });
  }

  // Evidence array
  if (!Array.isArray(b.evidence)) {
    errors.push({
      field: 'evidence',
      code: 'INVALID_TYPE',
      message: 'evidence must be an array',
    });
  } else {
    for (let i = 0; i < b.evidence.length; i++) {
      const item = b.evidence[i] as Record<string, unknown>;
      if (typeof item !== 'object' || item === null) {
        errors.push({
          field: `evidence[${i}]`,
          code: 'INVALID_TYPE',
          message: `evidence[${i}] must be an object`,
        });
      } else {
        if (!['signal', 'prediction', 'error', 'model', 'scann', 'wolfram'].includes(item.type as string)) {
          errors.push({
            field: `evidence[${i}].type`,
            code: 'INVALID_VALUE',
            message: `evidence[${i}].type must be one of: signal, prediction, error, model, scann, wolfram`,
          });
        }
        if (typeof item.referenceId !== 'string') {
          errors.push({
            field: `evidence[${i}].referenceId`,
            code: 'MISSING_OR_EMPTY',
            message: `evidence[${i}].referenceId must be a string`,
          });
        }
        if (typeof item.weight !== 'number' || item.weight < 0 || item.weight > 1) {
          errors.push({
            field: `evidence[${i}].weight`,
            code: 'OUT_OF_RANGE',
            message: `evidence[${i}].weight must be between 0 and 1`,
          });
        }
        if (typeof item.content !== 'object') {
          errors.push({
            field: `evidence[${i}].content`,
            code: 'INVALID_TYPE',
            message: `evidence[${i}].content must be an object`,
          });
        }
      }
    }
  }

  // Strict mode
  if (strict) {
    const knownFields = new Set([
      'schemaId', 'schemaVersion', 'id', 'severity', 'category',
      'description', 'evidence', 'predictedProbability', 'timestamp',
      'traceId', 'sourceRevision', 'runtimeRevision', 'tick', 'sequence',
    ]);
    for (const key of Object.keys(b)) {
      if (!knownFields.has(key)) {
        errors.push({
          field: key,
          code: 'UNKNOWN_FIELD',
          message: `Unknown field "${key}" in strict mode`,
        });
      }
    }
  }

  return { valid: errors.length === 0, errors, warnings };
}

/**
 * Validate a bounded action plan contract.
 */
export function validateBoundedActionPlan(
  obj: unknown,
  options: { strict?: boolean } = {}
): ValidationResult {
  const { strict = true } = options;
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];

  if (typeof obj !== 'object' || obj === null) {
    return {
      valid: false,
      errors: [{
        field: 'root',
        code: 'INVALID_TYPE',
        message: 'BoundedActionPlan must be a non-null object',
      }],
      warnings: [],
    };
  }

  const p = obj as Record<string, unknown>;

  // Schema validation
  if (p.schemaId !== BOUNDED_ACTION_PLAN_SCHEMA_ID) {
    errors.push({
      field: 'schemaId',
      code: 'INVALID_SCHEMA',
      message: `Expected "${BOUNDED_ACTION_PLAN_SCHEMA_ID}"`,
    });
  }

  if (typeof p.schemaVersion !== 'string' || !p.schemaVersion.startsWith('v')) {
    errors.push({
      field: 'schemaVersion',
      code: 'INVALID_VERSION',
      message: 'schemaVersion must start with "v"',
    });
  }

  // Required fields
  for (const field of ['id', 'name', 'description', 'traceId', 'riskBundleId']) {
    if (typeof p[field] !== 'string' || (p[field] as string).length === 0) {
      errors.push({
        field,
        code: 'MISSING_OR_EMPTY',
        message: `${field} must be a non-empty string`,
      });
    }
  }

  // Reversible boolean
  if (typeof p.reversible !== 'boolean') {
    errors.push({
      field: 'reversible',
      code: 'INVALID_TYPE',
      message: 'reversible must be a boolean',
    });
  }

  // Actions array
  if (!Array.isArray(p.actions)) {
    errors.push({
      field: 'actions',
      code: 'INVALID_TYPE',
      message: 'actions must be an array',
    });
  } else {
    for (let i = 0; i < p.actions.length; i++) {
      const action = p.actions[i] as Record<string, unknown>;
      if (typeof action !== 'object' || action === null) {
        errors.push({
          field: `actions[${i}]`,
          code: 'INVALID_TYPE',
          message: `actions[${i}] must be an object`,
        });
      } else {
        if (typeof action.actionId !== 'string') {
          errors.push({ field: `actions[${i}].actionId`, code: 'MISSING_OR_EMPTY', message: 'actionId required' });
        }
        if (!['read', 'write', 'mutate', 'deploy', 'rollback'].includes(action.type as string)) {
          errors.push({ field: `actions[${i}].type`, code: 'INVALID_VALUE', message: 'Invalid action type' });
        }
        if (typeof action.target !== 'string') {
          errors.push({ field: `actions[${i}].target`, code: 'MISSING_OR_EMPTY', message: 'target required' });
        }
        if (typeof action.maxExecutionTimeMs !== 'number' || action.maxExecutionTimeMs <= 0) {
          errors.push({ field: `actions[${i}].maxExecutionTimeMs`, code: 'OUT_OF_RANGE', message: 'maxExecutionTimeMs must be positive' });
        }
        if (typeof action.requiresConfirmation !== 'boolean') {
          errors.push({ field: `actions[${i}].requiresConfirmation`, code: 'INVALID_TYPE', message: 'requiresConfirmation must be boolean' });
        }
      }
    }
  }

  // Pre/Post conditions
  for (const field of ['preConditions', 'postConditions']) {
    if (!Array.isArray(p[field])) {
      errors.push({ field, code: 'INVALID_TYPE', message: `${field} must be an array` });
    }
  }

  // Scope
  if (typeof p.scope !== 'object' || p.scope === null) {
    errors.push({ field: 'scope', code: 'INVALID_TYPE', message: 'scope must be an object' });
  } else {
    const scope = p.scope as Record<string, unknown>;
    if (!Array.isArray(scope.allowedResourceTypes)) {
      errors.push({ field: 'scope.allowedResourceTypes', code: 'INVALID_TYPE', message: 'Must be an array' });
    }
    if (typeof scope.maxAffectedResources !== 'number' || scope.maxAffectedResources <= 0) {
      errors.push({ field: 'scope.maxAffectedResources', code: 'OUT_OF_RANGE', message: 'Must be positive' });
    }
    if (typeof scope.maxCost !== 'number' || scope.maxCost < 0) {
      errors.push({ field: 'scope.maxCost', code: 'OUT_OF_RANGE', message: 'Must be non-negative' });
    }
  }

  // Warning for missing rollback plan on reversible
  if (p.reversible === true && !p.rollbackPlan) {
    warnings.push({
      field: 'rollbackPlan',
      message: 'Reversible plan should include a rollbackPlan',
    });
  }

  // Strict mode
  if (strict) {
    const knownFields = new Set([
      'schemaId', 'schemaVersion', 'id', 'name', 'description', 'actions',
      'preConditions', 'postConditions', 'reversible', 'rollbackPlan',
      'scope', 'riskBundleId', 'timestamp', 'traceId', 'owner',
      'sourceRevision', 'runtimeRevision', 'tick', 'sequence',
    ]);
    for (const key of Object.keys(p)) {
      if (!knownFields.has(key)) {
        errors.push({
          field: key,
          code: 'UNKNOWN_FIELD',
          message: `Unknown field "${key}" in strict mode`,
        });
      }
    }
  }

  return { valid: errors.length === 0, errors, warnings };
}

// ============================================================================
// Schema Hash Generation
// ============================================================================

function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return `s${Math.abs(hash).toString(16).padStart(8, '0')}`;
}

export function generateRiskEvidenceBundleSchemaHash(): string {
  return simpleHash(JSON.stringify({
    schemaId: RISK_EVIDENCE_BUNDLE_SCHEMA_ID,
    version: 'v1',
    fields: ['id', 'severity', 'category', 'description', 'evidence', 'predictedProbability', 'timestamp', 'traceId'],
  }));
}

export function generateBoundedActionPlanSchemaHash(): string {
  return simpleHash(JSON.stringify({
    schemaId: BOUNDED_ACTION_PLAN_SCHEMA_ID,
    version: 'v1',
    fields: ['id', 'name', 'description', 'actions', 'preConditions', 'postConditions', 'reversible', 'scope'],
  }));
}
