/**
 * Schema Generation Tests
 * 
 * Tests for JSON Schema generation and MCP schema conversion.
 */

import { describe, it, expect } from "vitest";
import {
  generatePermissionReceiptInputSchema,
  generateWorkflowTransitionPayloadSchema,
  generateReadOnlyMCPInputSchema,
  generateReadOnlyMCPOutputSchema,
  generateAllSchemas,
  toMCPInputSchema,
  type SchemaMetadata,
} from "../schemas.js";

const mockMetadata: SchemaMetadata = {
  schemaVersion: "1.0.0",
  contractSetId: "typescript-contract-pilot-v1",
  generatedAt: "2026-08-07T00:00:00.000Z",
  revision: "abc123def456",
  sourceHash: "hash123",
};

describe("PermissionReceiptInput Schema", () => {
  it("generates valid schema", () => {
    const schema = generatePermissionReceiptInputSchema(mockMetadata);
    
    expect(schema.$schema).toBe("https://json-schema.org/draft/2020-12/schema");
    expect(schema.type).toBe("object");
    expect(schema.additionalProperties).toBe(false);
    expect(schema.required).toContain("requestId");
    expect(schema.required).toContain("ownerId");
    expect(schema.required).toContain("capability");
    expect(schema.properties.requestId.maxLength).toBe(64);
  });

  it("has correct enum constraints", () => {
    const schema = generatePermissionReceiptInputSchema(mockMetadata);
    
    expect(schema.properties.scope.enum).toEqual(["repository", "workspace", "workflow", "system"]);
    expect(schema.properties.effect.enum).toEqual(["read", "mutate", "coordinate"]);
  });

  it("limits array length", () => {
    const schema = generatePermissionReceiptInputSchema(mockMetadata);
    
    expect(schema.properties.tags.maxItems).toBe(50);
  });

  it("limits string lengths", () => {
    const schema = generatePermissionReceiptInputSchema(mockMetadata);
    
    expect(schema.properties.justification.maxLength).toBe(256);
    expect(schema.properties.expectedOutcome.maxLength).toBe(4096);
  });
});

describe("WorkflowTransitionPayload Schema", () => {
  it("generates valid schema", () => {
    const schema = generateWorkflowTransitionPayloadSchema(mockMetadata);
    
    expect(schema.type).toBe("object");
    expect(schema.additionalProperties).toBe(false);
    expect(schema.required).toContain("transitionId");
    expect(schema.required).toContain("workflowId");
    expect(schema.required).toContain("fromState");
    expect(schema.required).toContain("toState");
  });

  it("has optional array fields", () => {
    const schema = generateWorkflowTransitionPayloadSchema(mockMetadata);
    
    expect(schema.properties.evidenceIds.type).toBe("array");
    expect(schema.properties.passedChecks.type).toBe("array");
    expect(schema.properties.evidenceIds.maxItems).toBe(50);
  });
});

describe("ReadOnlyMCPInput Schema", () => {
  it("generates valid schema", () => {
    const schema = generateReadOnlyMCPInputSchema(mockMetadata);
    
    expect(schema.type).toBe("object");
    expect(schema.required).toContain("requestId");
    expect(schema.required).toContain("ownerId");
  });

  it("has nested query object", () => {
    const schema = generateReadOnlyMCPInputSchema(mockMetadata);
    
    expect(schema.properties.query.type).toBe("object");
    expect(schema.properties.query.properties.path.maxLength).toBe(256);
    expect(schema.properties.query.properties.limit.minimum).toBe(1);
    expect(schema.properties.query.properties.offset.minimum).toBe(0);
  });
});

describe("ReadOnlyMCPOutput Schema", () => {
  it("generates valid schema", () => {
    const schema = generateReadOnlyMCPOutputSchema(mockMetadata);
    
    expect(schema.type).toBe("object");
    expect(schema.required).toContain("requestId");
    expect(schema.required).toContain("success");
    expect(schema.required).toContain("timestamp");
  });

  it("allows flexible data field", () => {
    const schema = generateReadOnlyMCPOutputSchema(mockMetadata);
    
    // data field has no type constraint - allows any value
    expect(schema.properties.data).toBeDefined();
  });

  it("has nested metadata constraints", () => {
    const schema = generateReadOnlyMCPOutputSchema(mockMetadata);
    
    expect(schema.properties.metadata.properties.itemsCount.minimum).toBe(0);
    expect(schema.properties.metadata.properties.executionTimeMs.minimum).toBe(0);
  });
});

describe("generateAllSchemas", () => {
  it("generates all schemas", () => {
    const schemas = generateAllSchemas(mockMetadata);
    
    expect(schemas.PermissionReceiptInput).toBeDefined();
    expect(schemas.WorkflowTransitionPayload).toBeDefined();
    expect(schemas.ReadOnlyMCPInput).toBeDefined();
    expect(schemas.ReadOnlyMCPOutput).toBeDefined();
  });
});

describe("toMCPInputSchema", () => {
  it("converts JSON Schema to MCP format", () => {
    const schema = generateReadOnlyMCPInputSchema(mockMetadata);
    const mcpSchema = toMCPInputSchema(schema);
    
    expect(mcpSchema.type).toBe("object");
    expect(mcpSchema.properties).toBeDefined();
    expect(mcpSchema.required).toBeDefined();
    expect(mcpSchema.additionalProperties).toBe(false);
  });
});
