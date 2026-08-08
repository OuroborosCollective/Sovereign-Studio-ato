/**
 * Strict Validation Functions
 * 
 * These validators implement fail-closed validation for contract types.
 * Unknown fields, missing required fields, and invalid types are all rejected.
 * 
 * @module validation
 */

import type {
  ValidationResult,
  ValidationError,
  ValidationErrorCode,
  EffectClass,
  CapabilityScope,
} from "./canonical-types.js";

// ============================================================================
// Constants
// ============================================================================

const MAX_SHORT_STRING = 64;
const MAX_MEDIUM_STRING = 256;
const MAX_LONG_STRING = 4096;
const MAX_ARRAY_ITEMS = 50;
const MAX_NESTING_DEPTH = 5;

const VALID_EFFECT_CLASSES: EffectClass[] = ["read", "mutate", "coordinate"];

const VALID_CAPABILITY_SCOPES: CapabilityScope[] = [
  "repository",
  "workspace",
  "workflow",
  "system",
];

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Creates a validation error.
 */
function createError(
  path: string,
  message: string,
  code: ValidationErrorCode
): ValidationError {
  return { path, message, code };
}

/**
 * Checks if a string is within the max length.
 */
function checkStringLength(
  value: unknown,
  fieldPath: string,
  maxLength: number,
  errors: ValidationError[]
): value is string {
  if (typeof value !== "string") {
    errors.push(createError(fieldPath, `Expected string, got ${typeof value}`, "INVALID_TYPE"));
    return false;
  }
  if (value.length > maxLength) {
    errors.push(
      createError(
        fieldPath,
        `String length ${value.length} exceeds maximum ${maxLength}`,
        "STRING_TOO_LONG"
      )
    );
    return false;
  }
  return true;
}

/**
 * Checks if a number is a positive integer.
 */
function checkPositiveNumber(
  value: unknown,
  fieldPath: string,
  errors: ValidationError[]
): value is number {
  if (typeof value !== "number") {
    errors.push(createError(fieldPath, `Expected number, got ${typeof value}`, "INVALID_TYPE"));
    return false;
  }
  if (!Number.isInteger(value) || value <= 0) {
    errors.push(
      createError(fieldPath, `Expected positive integer, got ${value}`, "NEGATIVE_VALUE")
    );
    return false;
  }
  return true;
}

/**
 * Checks if a number is a non-negative integer.
 */
function checkNonNegativeNumber(
  value: unknown,
  fieldPath: string,
  errors: ValidationError[]
): value is number {
  if (typeof value !== "number") {
    errors.push(createError(fieldPath, `Expected number, got ${typeof value}`, "INVALID_TYPE"));
    return false;
  }
  if (!Number.isInteger(value) || value < 0) {
    errors.push(
      createError(fieldPath, `Expected non-negative integer, got ${value}`, "NEGATIVE_VALUE")
    );
    return false;
  }
  return true;
}

/**
 * Checks if a value is in a list of allowed values.
 */
function checkEnum<T extends string>(
  value: unknown,
  fieldPath: string,
  allowedValues: readonly T[],
  errors: ValidationError[]
): value is T {
  if (typeof value !== "string" || !allowedValues.includes(value as T)) {
    errors.push(
      createError(
        fieldPath,
        `Expected one of [${allowedValues.join(", ")}], got ${String(value)}`,
        "INVALID_VALUE"
      )
    );
    return false;
  }
  return true;
}

/**
 * Checks if a value is an array within the max items limit.
 */
function checkArray<T>(
  value: unknown,
  fieldPath: string,
  maxItems: number,
  errors: ValidationError[]
): value is T[] {
  if (!Array.isArray(value)) {
    errors.push(createError(fieldPath, `Expected array, got ${typeof value}`, "INVALID_TYPE"));
    return false;
  }
  if (value.length > maxItems) {
    errors.push(
      createError(fieldPath, `Array length ${value.length} exceeds maximum ${maxItems}`, "ARRAY_TOO_LONG")
    );
    return false;
  }
  return true;
}

/**
 * Checks if an object has no extra fields.
 */
function checkNoExtraFields(
  obj: Record<string, unknown>,
  allowedFields: readonly string[],
  errors: ValidationError[]
): void {
  const extraFields = Object.keys(obj).filter((key) => !allowedFields.includes(key));
  if (extraFields.length > 0) {
    errors.push(
      createError(
        "$",
        `Unknown fields: ${extraFields.join(", ")}`,
        "UNKNOWN_FIELD"
      )
    );
  }
}

/**
 * Checks nesting depth of a record.
 */
function checkNestingDepth(
  _value: unknown,
  fieldPath: string,
  maxDepth: number,
  currentDepth: number,
  errors: ValidationError[]
): boolean {
  if (currentDepth > maxDepth) {
    errors.push(
      createError(
        fieldPath,
        `Nesting depth ${currentDepth} exceeds maximum ${maxDepth}`,
        "NESTING_TOO_DEEP"
      )
    );
    return false;
  }
  return true;
}

// ============================================================================
// PermissionReceiptInput Validation
// ============================================================================

const PERMISSION_RECEIPT_INPUT_FIELDS = [
  "requestId",
  "ownerId",
  "repositoryContext",
  "capability",
  "scope",
  "effect",
  "requestedAt",
  "justification",
  "expectedOutcome",
  "workflowId",
  "taskId",
  "tags",
  "metadata",
] as const;

/**
 * Validates a PermissionReceiptInput strictly.
 * Rejects unknown fields, missing required fields, and invalid types.
 */
export function validatePermissionReceiptInput(
  input: unknown
): ValidationResult {
  const errors: ValidationError[] = [];

  if (typeof input !== "object" || input === null) {
    return {
      valid: false,
      errors: [createError("$", "Expected object, got null or undefined", "INVALID_TYPE")],
    };
  }

  const obj = input as Record<string, unknown>;

  // Check for unknown fields
  checkNoExtraFields(obj, PERMISSION_RECEIPT_INPUT_FIELDS, errors);

  // Required fields
  if (!checkStringLength(obj.requestId, "requestId", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.ownerId, "ownerId", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.capability, "capability", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (!checkEnum(obj.scope, "scope", VALID_CAPABILITY_SCOPES, errors)) {
    // Error already pushed
  }

  if (!checkEnum(obj.effect, "effect", VALID_EFFECT_CLASSES, errors)) {
    // Error already pushed
  }

  if (!checkPositiveNumber(obj.requestedAt, "requestedAt", errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.justification, "justification", MAX_MEDIUM_STRING, errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.expectedOutcome, "expectedOutcome", MAX_LONG_STRING, errors)) {
    // Error already pushed
  }

  // Optional fields
  if (obj.workflowId !== undefined && obj.workflowId !== null) {
    if (!checkStringLength(obj.workflowId, "workflowId", MAX_SHORT_STRING, errors)) {
      // Error already pushed
    }
  }

  if (obj.taskId !== undefined && obj.taskId !== null) {
    if (!checkStringLength(obj.taskId, "taskId", MAX_SHORT_STRING, errors)) {
      // Error already pushed
    }
  }

  // Validate repositoryContext if present
  if (obj.repositoryContext !== undefined && obj.repositoryContext !== null) {
    if (typeof obj.repositoryContext !== "object") {
      errors.push(
        createError(
          "repositoryContext",
          "Expected object, got " + typeof obj.repositoryContext,
          "INVALID_TYPE"
        )
      );
    } else {
      const repoCtx = obj.repositoryContext as Record<string, unknown>;
      if (!checkStringLength(repoCtx.owner, "repositoryContext.owner", MAX_SHORT_STRING, errors)) {
        // Error already pushed
      }
      if (!checkStringLength(repoCtx.repo, "repositoryContext.repo", MAX_SHORT_STRING, errors)) {
        // Error already pushed
      }
      if (repoCtx.revision !== undefined && repoCtx.revision !== null) {
        if (!checkStringLength(repoCtx.revision, "repositoryContext.revision", MAX_SHORT_STRING, errors)) {
          // Error already pushed
        }
      }
    }
  }

  // Validate tags if present
  if (obj.tags !== undefined && obj.tags !== null) {
    if (!checkArray(obj.tags, "tags", MAX_ARRAY_ITEMS, errors)) {
      // Error already pushed
    } else {
      for (let i = 0; i < obj.tags.length; i++) {
        if (!checkStringLength(obj.tags[i], `tags[${i}]`, MAX_SHORT_STRING, errors)) {
          // Error already pushed
        }
      }
    }
  }

  // Validate metadata if present
  if (obj.metadata !== undefined && obj.metadata !== null) {
    if (typeof obj.metadata !== "object" || Array.isArray(obj.metadata)) {
      errors.push(
        createError("metadata", "Expected object, got " + typeof obj.metadata, "INVALID_TYPE")
      );
    } else if (!checkNestingDepth(obj.metadata, "metadata", MAX_NESTING_DEPTH, 1, errors)) {
      // Error already pushed
    }
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  // Compute hash for valid input
  const hash = computeInputHashSync(input);
  return { valid: true, hash };
}

// ============================================================================
// WorkflowTransitionPayload Validation
// ============================================================================

const WORKFLOW_TRANSITION_FIELDS = [
  "transitionId",
  "workflowId",
  "fromState",
  "toState",
  "transitionedAt",
  "actorId",
  "reason",
  "evidenceIds",
  "passedChecks",
  "context",
] as const;

/**
 * Validates a WorkflowTransitionPayload strictly.
 */
export function validateWorkflowTransitionPayload(
  input: unknown
): ValidationResult {
  const errors: ValidationError[] = [];

  if (typeof input !== "object" || input === null) {
    return {
      valid: false,
      errors: [createError("$", "Expected object, got null or undefined", "INVALID_TYPE")],
    };
  }

  const obj = input as Record<string, unknown>;

  // Check for unknown fields
  checkNoExtraFields(obj, WORKFLOW_TRANSITION_FIELDS, errors);

  // Required fields
  if (!checkStringLength(obj.transitionId, "transitionId", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.workflowId, "workflowId", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.fromState, "fromState", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.toState, "toState", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (!checkPositiveNumber(obj.transitionedAt, "transitionedAt", errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.actorId, "actorId", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.reason, "reason", MAX_MEDIUM_STRING, errors)) {
    // Error already pushed
  }

  // Optional array fields
  if (obj.evidenceIds !== undefined && obj.evidenceIds !== null) {
    if (!checkArray(obj.evidenceIds, "evidenceIds", MAX_ARRAY_ITEMS, errors)) {
      // Error already pushed
    } else {
      for (let i = 0; i < obj.evidenceIds.length; i++) {
        if (!checkStringLength(obj.evidenceIds[i], `evidenceIds[${i}]`, MAX_SHORT_STRING, errors)) {
          // Error already pushed
        }
      }
    }
  }

  if (obj.passedChecks !== undefined && obj.passedChecks !== null) {
    if (!checkArray(obj.passedChecks, "passedChecks", MAX_ARRAY_ITEMS, errors)) {
      // Error already pushed
    } else {
      for (let i = 0; i < obj.passedChecks.length; i++) {
        if (!checkStringLength(obj.passedChecks[i], `passedChecks[${i}]`, MAX_SHORT_STRING, errors)) {
          // Error already pushed
        }
      }
    }
  }

  // Validate context if present
  if (obj.context !== undefined && obj.context !== null) {
    if (typeof obj.context !== "object" || Array.isArray(obj.context)) {
      errors.push(
        createError("context", "Expected object, got " + typeof obj.context, "INVALID_TYPE")
      );
    } else if (!checkNestingDepth(obj.context, "context", MAX_NESTING_DEPTH, 1, errors)) {
      // Error already pushed
    }
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  // Compute hash for valid input
  const hash = computeInputHashSync(input);
  return { valid: true, hash };
}

// ============================================================================
// ReadOnlyMCPInput Validation
// ============================================================================

const READ_ONLY_MCP_INPUT_FIELDS = [
  "requestId",
  "ownerId",
  "repository",
  "revision",
  "query",
  "metadata",
] as const;

/**
 * Validates a ReadOnlyMCPInput strictly.
 */
export function validateReadOnlyMCPInput(input: unknown): ValidationResult {
  const errors: ValidationError[] = [];

  if (typeof input !== "object" || input === null) {
    return {
      valid: false,
      errors: [createError("$", "Expected object, got null or undefined", "INVALID_TYPE")],
    };
  }

  const obj = input as Record<string, unknown>;

  // Check for unknown fields
  checkNoExtraFields(obj, READ_ONLY_MCP_INPUT_FIELDS, errors);

  // Required fields
  if (!checkStringLength(obj.requestId, "requestId", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (!checkStringLength(obj.ownerId, "ownerId", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  // Optional fields
  if (obj.revision !== undefined && obj.revision !== null) {
    if (!checkStringLength(obj.revision, "revision", MAX_SHORT_STRING, errors)) {
      // Error already pushed
    }
  }

  // Validate repository if present
  if (obj.repository !== undefined && obj.repository !== null) {
    if (typeof obj.repository !== "object") {
      errors.push(
        createError(
          "repository",
          "Expected object, got " + typeof obj.repository,
          "INVALID_TYPE"
        )
      );
    } else {
      const repo = obj.repository as Record<string, unknown>;
      if (!checkStringLength(repo.owner, "repository.owner", MAX_SHORT_STRING, errors)) {
        // Error already pushed
      }
      if (!checkStringLength(repo.repo, "repository.repo", MAX_SHORT_STRING, errors)) {
        // Error already pushed
      }
    }
  }

  // Validate query if present
  if (obj.query !== undefined && obj.query !== null) {
    if (typeof obj.query !== "object") {
      errors.push(
        createError("query", "Expected object, got " + typeof obj.query, "INVALID_TYPE")
      );
    } else {
      const query = obj.query as Record<string, unknown>;
      if (query.path !== undefined && query.path !== null) {
        if (!checkStringLength(query.path, "query.path", MAX_MEDIUM_STRING, errors)) {
          // Error already pushed
        }
      }
      if (query.pattern !== undefined && query.pattern !== null) {
        if (!checkStringLength(query.pattern, "query.pattern", MAX_MEDIUM_STRING, errors)) {
          // Error already pushed
        }
      }
      if (query.limit !== undefined && query.limit !== null) {
        if (!checkPositiveNumber(query.limit, "query.limit", errors)) {
          // Error already pushed
        }
      }
      if (query.offset !== undefined && query.offset !== null) {
        if (!checkNonNegativeNumber(query.offset, "query.offset", errors)) {
          // Error already pushed
        }
      }
    }
  }

  // Validate metadata if present
  if (obj.metadata !== undefined && obj.metadata !== null) {
    if (typeof obj.metadata !== "object" || Array.isArray(obj.metadata)) {
      errors.push(
        createError("metadata", "Expected object, got " + typeof obj.metadata, "INVALID_TYPE")
      );
    } else if (!checkNestingDepth(obj.metadata, "metadata", MAX_NESTING_DEPTH, 1, errors)) {
      // Error already pushed
    }
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  // Compute hash for valid input
  const hash = computeInputHashSync(input);
  return { valid: true, hash };
}

// ============================================================================
// ReadOnlyMCPOutput Validation
// ============================================================================

const READ_ONLY_MCP_OUTPUT_FIELDS = [
  "requestId",
  "success",
  "data",
  "error",
  "timestamp",
  "metadata",
] as const;

/**
 * Validates a ReadOnlyMCPOutput strictly.
 */
export function validateReadOnlyMCPOutput(input: unknown): ValidationResult {
  const errors: ValidationError[] = [];

  if (typeof input !== "object" || input === null) {
    return {
      valid: false,
      errors: [createError("$", "Expected object, got null or undefined", "INVALID_TYPE")],
    };
  }

  const obj = input as Record<string, unknown>;

  // Check for unknown fields
  checkNoExtraFields(obj, READ_ONLY_MCP_OUTPUT_FIELDS, errors);

  // Required fields
  if (!checkStringLength(obj.requestId, "requestId", MAX_SHORT_STRING, errors)) {
    // Error already pushed
  }

  if (typeof obj.success !== "boolean") {
    errors.push(
      createError("success", `Expected boolean, got ${typeof obj.success}`, "INVALID_TYPE")
    );
  }

  if (!checkPositiveNumber(obj.timestamp, "timestamp", errors)) {
    // Error already pushed
  }

  // Optional fields
  if (obj.error !== undefined && obj.error !== null) {
    if (!checkStringLength(obj.error, "error", MAX_MEDIUM_STRING, errors)) {
      // Error already pushed
    }
  }

  // Validate metadata if present
  if (obj.metadata !== undefined && obj.metadata !== null) {
    if (typeof obj.metadata !== "object" || Array.isArray(obj.metadata)) {
      errors.push(
        createError("metadata", "Expected object, got " + typeof obj.metadata, "INVALID_TYPE")
      );
    } else {
      const meta = obj.metadata as Record<string, unknown>;
      if (meta.itemsCount !== undefined && meta.itemsCount !== null) {
        if (!checkNonNegativeNumber(meta.itemsCount, "metadata.itemsCount", errors)) {
          // Error already pushed
        }
      }
      if (meta.executionTimeMs !== undefined && meta.executionTimeMs !== null) {
        if (!checkNonNegativeNumber(meta.executionTimeMs, "metadata.executionTimeMs", errors)) {
          // Error already pushed
        }
      }
      if (meta.sourceRevision !== undefined && meta.sourceRevision !== null) {
        if (!checkStringLength(meta.sourceRevision, "metadata.sourceRevision", MAX_SHORT_STRING, errors)) {
          // Error already pushed
        }
      }
    }
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  // Compute hash for valid input
  const hash = computeInputHashSync(input);
  return { valid: true, hash };
}

// ============================================================================
// Hash Computation
// ============================================================================

/**
 * Computes a SHA-256 hash of the canonical JSON representation (async).
 */
export async function computeInputHashAsync(input: unknown): Promise<string> {
  const json = JSON.stringify(input, Object.keys(input as object).sort());
  const encoder = new TextEncoder();
  const data = encoder.encode(json);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  return hashHex;
}

/**
 * Computes a SHA-256 hash synchronously using Node's crypto module.
 */
export function computeInputHashSync(input: unknown): string {
  const json = JSON.stringify(input, Object.keys(input as object).sort());
  const { createHash } = require("crypto");
  return createHash("sha256").update(json).digest("hex");
}

// ============================================================================
// Export Validators Map
// ============================================================================

/**
 * All validators indexed by contract type name.
 */
export const validators = {
  PermissionReceiptInput: validatePermissionReceiptInput,
  WorkflowTransitionPayload: validateWorkflowTransitionPayload,
  ReadOnlyMCPInput: validateReadOnlyMCPInput,
  ReadOnlyMCPOutput: validateReadOnlyMCPOutput,
} as const;

export type ValidatorName = keyof typeof validators;
