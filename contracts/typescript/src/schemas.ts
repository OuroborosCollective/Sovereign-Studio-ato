/**
 * JSON Schema Generation
 * 
 * Generates JSON Schema from TypeScript types for MCP input/output schemas.
 * 
 * @module schemas
 */

// ============================================================================
// JSON Schema Types
// ============================================================================

export interface JsonSchema {
  $schema: string;
  $id: string;
  title: string;
  description?: string;
  type: "object";
  properties: Record<string, unknown>;
  required: string[];
  additionalProperties: boolean;
  definitions?: Record<string, unknown>;
}

export interface SchemaMetadata {
  schemaVersion: string;
  contractSetId: string;
  generatedAt: string;
  revision: string;
  sourceHash: string;
}

// ============================================================================
// Constants
// ============================================================================

const SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema";

function generateSchemaId(typeName: string): string {
  return `https://sovereign-studio.app/schemas/${typeName.toLowerCase()}.schema.json`;
}

// ============================================================================
// Schema Generation Functions
// ============================================================================

/**
 * Generates a JSON Schema for PermissionReceiptInput.
 */
export function generatePermissionReceiptInputSchema(
  _metadata: SchemaMetadata
): JsonSchema {
  return {
    $schema: SCHEMA_DIALECT,
    $id: generateSchemaId("PermissionReceiptInput"),
    title: "PermissionReceiptInput",
    description: "Input for requesting a permission receipt",
    type: "object",
    properties: {
      requestId: {
        type: "string",
        maxLength: 64,
        description: "Unique identifier for this permission request",
      },
      ownerId: {
        type: "string",
        maxLength: 64,
        description: "Owner/user requesting the permission",
      },
      repositoryContext: {
        type: "object",
        description: "Repository context (if applicable)",
        properties: {
          owner: { type: "string", maxLength: 64 },
          repo: { type: "string", maxLength: 64 },
          revision: { type: "string", maxLength: 64 },
        },
        required: ["owner", "repo"],
        additionalProperties: false,
      },
      capability: {
        type: "string",
        maxLength: 64,
        description: "Capability being requested",
      },
      scope: {
        type: "string",
        enum: ["repository", "workspace", "workflow", "system"],
        description: "Scope of the capability",
      },
      effect: {
        type: "string",
        enum: ["read", "mutate", "coordinate"],
        description: "Effect class of the operation",
      },
      requestedAt: {
        type: "integer",
        minimum: 1,
        description: "Timestamp when request was created (Unix ms)",
      },
      justification: {
        type: "string",
        maxLength: 256,
        description: "Human-readable justification for the request",
      },
      expectedOutcome: {
        type: "string",
        maxLength: 4096,
        description: "Expected outcome description",
      },
      workflowId: {
        type: "string",
        maxLength: 64,
        description: "Associated workflow ID (if part of a workflow)",
      },
      taskId: {
        type: "string",
        maxLength: 64,
        description: "Associated task ID (if part of a task)",
      },
      tags: {
        type: "array",
        items: { type: "string", maxLength: 64 },
        maxItems: 50,
        description: "Tags for categorization",
      },
      metadata: {
        type: "object",
        description: "Metadata for additional context",
        additionalProperties: true,
      },
    },
    required: [
      "requestId",
      "ownerId",
      "capability",
      "scope",
      "effect",
      "requestedAt",
      "justification",
      "expectedOutcome",
    ],
    additionalProperties: false,
  };
}

/**
 * Generates a JSON Schema for WorkflowTransitionPayload.
 */
export function generateWorkflowTransitionPayloadSchema(
  _metadata: SchemaMetadata
): JsonSchema {
  return {
    $schema: SCHEMA_DIALECT,
    $id: generateSchemaId("WorkflowTransitionPayload"),
    title: "WorkflowTransitionPayload",
    description: "Payload for workflow state transitions",
    type: "object",
    properties: {
      transitionId: {
        type: "string",
        maxLength: 64,
        description: "Unique identifier for this transition",
      },
      workflowId: {
        type: "string",
        maxLength: 64,
        description: "Workflow this transition belongs to",
      },
      fromState: {
        type: "string",
        maxLength: 64,
        description: "Current state before transition",
      },
      toState: {
        type: "string",
        maxLength: 64,
        description: "Target state after transition",
      },
      transitionedAt: {
        type: "integer",
        minimum: 1,
        description: "Timestamp of the transition (Unix ms)",
      },
      actorId: {
        type: "string",
        maxLength: 64,
        description: "Actor who triggered the transition",
      },
      reason: {
        type: "string",
        maxLength: 256,
        description: "Reason for the transition",
      },
      evidenceIds: {
        type: "array",
        items: { type: "string", maxLength: 64 },
        maxItems: 50,
        description: "Evidence IDs associated with this transition",
      },
      passedChecks: {
        type: "array",
        items: { type: "string", maxLength: 64 },
        maxItems: 50,
        description: "Check results that passed before this transition",
      },
      context: {
        type: "object",
        description: "Context data for the transition",
        additionalProperties: true,
      },
    },
    required: [
      "transitionId",
      "workflowId",
      "fromState",
      "toState",
      "transitionedAt",
      "actorId",
      "reason",
    ],
    additionalProperties: false,
  };
}

/**
 * Generates a JSON Schema for ReadOnlyMCPInput.
 */
export function generateReadOnlyMCPInputSchema(
  _metadata: SchemaMetadata
): JsonSchema {
  return {
    $schema: SCHEMA_DIALECT,
    $id: generateSchemaId("ReadOnlyMCPInput"),
    title: "ReadOnlyMCPInput",
    description: "Input schema for a read-only MCP tool",
    type: "object",
    properties: {
      requestId: {
        type: "string",
        maxLength: 64,
        description: "Request ID for tracking",
      },
      ownerId: {
        type: "string",
        maxLength: 64,
        description: "Target owner",
      },
      repository: {
        type: "object",
        description: "Target repository (if applicable)",
        properties: {
          owner: { type: "string", maxLength: 64 },
          repo: { type: "string", maxLength: 64 },
        },
        required: ["owner", "repo"],
        additionalProperties: false,
      },
      revision: {
        type: "string",
        maxLength: 64,
        description: "Revision to operate on (if applicable)",
      },
      query: {
        type: "object",
        description: "Query parameters for the read operation",
        properties: {
          path: { type: "string", maxLength: 256 },
          pattern: { type: "string", maxLength: 256 },
          limit: { type: "integer", minimum: 1 },
          offset: { type: "integer", minimum: 0 },
        },
        additionalProperties: false,
      },
      metadata: {
        type: "object",
        description: "Metadata for the request",
        additionalProperties: true,
      },
    },
    required: ["requestId", "ownerId"],
    additionalProperties: false,
  };
}

/**
 * Generates a JSON Schema for ReadOnlyMCPOutput.
 */
export function generateReadOnlyMCPOutputSchema(
  _metadata: SchemaMetadata
): JsonSchema {
  return {
    $schema: SCHEMA_DIALECT,
    $id: generateSchemaId("ReadOnlyMCPOutput"),
    title: "ReadOnlyMCPOutput",
    description: "Output schema for a read-only MCP tool",
    type: "object",
    properties: {
      requestId: {
        type: "string",
        maxLength: 64,
        description: "Original request ID",
      },
      success: {
        type: "boolean",
        description: "Success status",
      },
      data: {
        description: "Result data (if successful)",
      },
      error: {
        type: "string",
        maxLength: 256,
        description: "Error message (if failed)",
      },
      timestamp: {
        type: "integer",
        minimum: 1,
        description: "Timestamp of the response",
      },
      metadata: {
        type: "object",
        description: "Metadata about the operation",
        properties: {
          itemsCount: { type: "integer", minimum: 0 },
          executionTimeMs: { type: "integer", minimum: 0 },
          sourceRevision: { type: "string", maxLength: 64 },
        },
        additionalProperties: false,
      },
    },
    required: ["requestId", "success", "timestamp"],
    additionalProperties: false,
  };
}

// ============================================================================
// Schema Registry
// ============================================================================

export type SchemaName =
  | "PermissionReceiptInput"
  | "WorkflowTransitionPayload"
  | "ReadOnlyMCPInput"
  | "ReadOnlyMCPOutput";

/**
 * Generates all schemas with metadata.
 */
export function generateAllSchemas(
  metadata: SchemaMetadata
): Record<SchemaName, JsonSchema> {
  return {
    PermissionReceiptInput: generatePermissionReceiptInputSchema(metadata),
    WorkflowTransitionPayload: generateWorkflowTransitionPayloadSchema(metadata),
    ReadOnlyMCPInput: generateReadOnlyMCPInputSchema(metadata),
    ReadOnlyMCPOutput: generateReadOnlyMCPOutputSchema(metadata),
  };
}

/**
 * Generates schema metadata from environment.
 */
export function generateSchemaMetadata(
  revision: string,
  sourceHash: string
): SchemaMetadata {
  return {
    schemaVersion: "1.0.0",
    contractSetId: "typescript-contract-pilot-v1",
    generatedAt: new Date().toISOString(),
    revision,
    sourceHash,
  };
}

// ============================================================================
// MCP Schema Export
// ============================================================================

/**
 * Converts a JSON Schema to MCP inputSchema format.
 */
export function toMCPInputSchema(schema: JsonSchema): Record<string, unknown> {
  return {
    type: schema.type,
    properties: schema.properties,
    required: schema.required,
    additionalProperties: schema.additionalProperties,
  };
}

/**
 * Generates MCP tool schemas for a given contract.
 */
export function generateMCPToolSchemas(
  schemaName: SchemaName,
  metadata: SchemaMetadata
): { inputSchema: Record<string, unknown>; outputSchema: Record<string, unknown> } {
  const schemas = generateAllSchemas(metadata);
  const inputSchema = schemas[schemaName];

  return {
    inputSchema: toMCPInputSchema(inputSchema),
    outputSchema: toMCPInputSchema(generateReadOnlyMCPOutputSchema(metadata)),
  };
}
