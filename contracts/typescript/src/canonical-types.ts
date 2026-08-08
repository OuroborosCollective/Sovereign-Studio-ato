/**
 * Canonical TypeScript Contract Types
 * 
 * These are the source-of-truth type definitions for the TypeScript Contract Pilot.
 * All generated artifacts (validators, schemas, hashes) derive from these types.
 * 
 * @module canonical-types
 * @version 1.0.0
 */

// ============================================================================
// Schema Version & Metadata
// ============================================================================

/**
 * Schema version for this contract set.
 * Incremented when any type in this file changes.
 */
export const CONTRACT_SCHEMA_VERSION = "1.0.0" as const;

/**
 * Contract set identifier.
 */
export const CONTRACT_SET_ID = "typescript-contract-pilot-v1" as const;

// ============================================================================
// Primitive Constraints
// ============================================================================

/** Maximum length for short string fields (e.g., names, IDs) */
export const MAX_SHORT_STRING = 64;

/** Maximum length for medium string fields (e.g., descriptions) */
export const MAX_MEDIUM_STRING = 256;

/** Maximum length for long string fields (e.g., content, messages) */
export const MAX_LONG_STRING = 4096;

/** Maximum number of items in array fields */
export const MAX_ARRAY_ITEMS = 50;

/** Maximum depth for nested objects */
export const MAX_NESTING_DEPTH = 5;

/** Valid truth class values */
export type TruthClass = 
  | "IMPLEMENTED_IN_REPOSITORY"
  | "TESTED_AT_REVISION"
  | "CI_VERIFIED"
  | "ARTIFACT_VERIFIED"
  | "DEPLOYED_UNVERIFIED"
  | "RUNTIME_VERIFIED"
  | "BLOCKED"
  | "CONTRADICTED"
  | "PLANNED";

/** Valid effect classes for tools */
export type EffectClass = "read" | "mutate" | "coordinate";

/** Valid capability scopes */
export type CapabilityScope = 
  | "repository"
  | "workspace"
  | "workflow"
  | "system";

/** Validation result types */
export type ValidationResult = 
  | { valid: true; hash: string }
  | { valid: false; errors: ValidationError[] };

/** Individual validation error */
export interface ValidationError {
  path: string;
  message: string;
  code: ValidationErrorCode;
}

/** Validation error codes */
export type ValidationErrorCode =
  | "MISSING_REQUIRED"
  | "INVALID_TYPE"
  | "INVALID_VALUE"
  | "STRING_TOO_LONG"
  | "STRING_TOO_SHORT"
  | "ARRAY_TOO_LONG"
  | "ARRAY_TOO_SHORT"
  | "NESTING_TOO_DEEP"
  | "UNKNOWN_FIELD"
  | "NEGATIVE_VALUE"
  | "VALUE_OUT_OF_RANGE";

// ============================================================================
// Permission Receipt Input
// ============================================================================

/**
 * Input for requesting a permission receipt.
 * Used before any mutating or coordinate operation.
 */
export interface PermissionReceiptInput {
  /** Unique identifier for this permission request */
  requestId: string;
  
  /** Owner/user requesting the permission */
  ownerId: string;
  
  /** Repository context (if applicable) */
  repositoryContext?: {
    owner: string;
    repo: string;
    revision?: string;
  };
  
  /** Capability being requested */
  capability: string;
  
  /** Scope of the capability */
  scope: CapabilityScope;
  
  /** Effect class of the operation */
  effect: EffectClass;
  
  /** Timestamp when request was created (Unix ms) */
  requestedAt: number;
  
  /** Human-readable justification for the request */
  justification: string;
  
  /** Expected outcome description */
  expectedOutcome: string;
  
  /** Associated workflow ID (if part of a workflow) */
  workflowId?: string;
  
  /** Associated task ID (if part of a task) */
  taskId?: string;
  
  /** Tags for categorization */
  tags?: string[];
  
  /** Metadata for additional context */
  metadata?: Record<string, unknown>;
}

/** PermissionReceiptInput with stricter constraints for validation */
export interface StrictPermissionReceiptInput {
  requestId: string;          // Required, max 64 chars
  ownerId: string;            // Required, max 64 chars
  repositoryContext?: {       // Optional, but if present all fields required
    owner: string;           // max 64 chars
    repo: string;            // max 64 chars
    revision?: string;       // max 64 chars if present
  };
  capability: string;        // Required, max 64 chars
  scope: CapabilityScope;    // Required
  effect: EffectClass;        // Required
  requestedAt: number;        // Required, must be positive
  justification: string;      // Required, max 256 chars
  expectedOutcome: string;   // Required, max 4096 chars
  workflowId?: string;       // Optional, max 64 chars
  taskId?: string;            // Optional, max 64 chars
  tags?: string[];           // Optional, max 50 items, each max 64 chars
  metadata?: Record<string, unknown>; // Optional, max depth 5
}

// ============================================================================
// Workflow Transition Payload
// ============================================================================

/**
 * Payload for workflow state transitions.
 * Used to track and validate workflow state changes.
 */
export interface WorkflowTransitionPayload {
  /** Unique identifier for this transition */
  transitionId: string;
  
  /** Workflow this transition belongs to */
  workflowId: string;
  
  /** Current state before transition */
  fromState: string;
  
  /** Target state after transition */
  toState: string;
  
  /** Timestamp of the transition (Unix ms) */
  transitionedAt: number;
  
  /** Actor who triggered the transition */
  actorId: string;
  
  /** Reason for the transition */
  reason: string;
  
  /** Evidence IDs associated with this transition */
  evidenceIds?: string[];
  
  /** Check results that passed before this transition */
  passedChecks?: string[];
  
  /** Context data for the transition */
  context?: Record<string, unknown>;
}

/** Strict version of WorkflowTransitionPayload */
export interface StrictWorkflowTransitionPayload {
  transitionId: string;       // Required, max 64 chars
  workflowId: string;          // Required, max 64 chars
  fromState: string;          // Required, max 64 chars
  toState: string;            // Required, max 64 chars
  transitionedAt: number;     // Required, must be positive
  actorId: string;            // Required, max 64 chars
  reason: string;             // Required, max 256 chars
  evidenceIds?: string[];     // Optional, max 50 items
  passedChecks?: string[];    // Optional, max 50 items
  context?: Record<string, unknown>; // Optional, max depth 5
}

// ============================================================================
// Read-Only MCP Tool Contract
// ============================================================================

/**
 * Input schema for a read-only MCP tool.
 * This represents the canonical input type for read operations.
 */
export interface ReadOnlyMCPInput {
  /** Request ID for tracking */
  requestId: string;
  
  /** Target owner */
  ownerId: string;
  
  /** Target repository (if applicable) */
  repository?: {
    owner: string;
    repo: string;
  };
  
  /** Revision to operate on (if applicable) */
  revision?: string;
  
  /** Query parameters for the read operation */
  query?: {
    path?: string;
    pattern?: string;
    limit?: number;
    offset?: number;
  };
  
  /** Metadata for the request */
  metadata?: Record<string, unknown>;
}

/** Strict version of ReadOnlyMCPInput */
export interface StrictReadOnlyMCPInput {
  requestId: string;          // Required, max 64 chars
  ownerId: string;            // Required, max 64 chars
  repository?: {              // Optional
    owner: string;           // max 64 chars
    repo: string;           // max 64 chars
  };
  revision?: string;          // Optional, max 64 chars
  query?: {                   // Optional
    path?: string;          // max 256 chars
    pattern?: string;       // max 256 chars
    limit?: number;        // positive integer
    offset?: number;       // non-negative integer
  };
  metadata?: Record<string, unknown>; // Optional, max depth 5
}

/**
 * Output schema for a read-only MCP tool.
 * This represents the canonical output type for read operations.
 */
export interface ReadOnlyMCPOutput {
  /** Original request ID */
  requestId: string;
  
  /** Success status */
  success: boolean;
  
  /** Result data (if successful) */
  data?: unknown;
  
  /** Error message (if failed) */
  error?: string;
  
  /** Timestamp of the response */
  timestamp: number;
  
  /** Metadata about the operation */
  metadata?: {
    itemsCount?: number;
    executionTimeMs?: number;
    sourceRevision?: string;
  };
}

/** Strict version of ReadOnlyMCPOutput */
export interface StrictReadOnlyMCPOutput {
  requestId: string;          // Required, max 64 chars
  success: boolean;           // Required
  data?: unknown;              // Optional
  error?: string;             // Optional, max 256 chars
  timestamp: number;           // Required, positive
  metadata?: {                // Optional
    itemsCount?: number;      // non-negative
    executionTimeMs?: number; // non-negative
    sourceRevision?: string;  // max 64 chars
  };
}

// ============================================================================
// Tool Contract Metadata
// ============================================================================

/**
 * Metadata for a tool contract.
 */
export interface ToolContractMetadata {
  /** Tool name */
  name: string;
  
  /** Tool version */
  version: string;
  
  /** Schema version */
  schemaVersion: string;
  
  /** Contract set ID */
  contractSetId: string;
  
  /** When this contract was created (ISO date) */
  createdAt: string;
  
  /** Git revision this contract is bound to */
  revision: string;
  
  /** Hash of the source type file */
  sourceHash: string;
  
  /** Tool capabilities */
  capabilities: string[];
  
  /** Effect class */
  effect: EffectClass;
  
  /** Whether this tool is read-only */
  readOnly: boolean;
}

// ============================================================================
// Contract Hash Input
// ============================================================================

/**
 * Input for computing a contract hash.
 */
export interface ContractHashInput {
  /** Source file path */
  sourcePath: string;
  
  /** Source file blob SHA */
  sourceBlobSha: string;
  
  /** Repository revision */
  repositoryRevision: string;
  
  /** Contract schema version */
  schemaVersion: string;
  
  /** Contract set ID */
  contractSetId: string;
  
  /** TypeScript version */
  typescriptVersion: string;
  
  /** Additional metadata */
  additionalMetadata?: Record<string, string>;
}

/**
 * Result of computing a contract hash.
 */
export interface ContractHashResult {
  /** The computed hash */
  hash: string;
  
  /** Algorithm used */
  algorithm: "sha256";
  
  /** Input used for the hash */
  input: ContractHashInput;
  
  /** When the hash was computed (ISO date) */
  computedAt: string;
}
