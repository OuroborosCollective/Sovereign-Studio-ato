/**
 * Validation Tests
 * 
 * Tests for strict validation functions.
 * Validates fail-closed behavior for unknown fields, missing required fields, and invalid types.
 */

import { describe, it, expect } from "vitest";
import {
  validatePermissionReceiptInput,
  validateWorkflowTransitionPayload,
  validateReadOnlyMCPInput,
  validateReadOnlyMCPOutput,
} from "../validation.js";

describe("PermissionReceiptInput Validation", () => {
  const validInput = {
    requestId: "req-123",
    ownerId: "user-456",
    capability: "github:read",
    scope: "repository",
    effect: "read",
    requestedAt: 1700000000000,
    justification: "Need to read repository contents",
    expectedOutcome: "Successfully read repository files",
  };

  it("accepts valid input", () => {
    const result = validatePermissionReceiptInput(validInput);
    expect(result.valid).toBe(true);
    if (result.valid) {
      expect(result.hash).toBeDefined();
      expect(result.hash.length).toBe(64); // SHA-256 hex
    }
  });

  it("rejects unknown fields", () => {
    const input = { ...validInput, unknownField: "should fail" };
    const result = validatePermissionReceiptInput(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "UNKNOWN_FIELD")).toBe(true);
    }
  });

  it("rejects missing required fields", () => {
    const input = { requestId: "req-123" };
    const result = validatePermissionReceiptInput(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      // Missing required fields produce INVALID_TYPE errors
      expect(result.errors.some((e) => e.code === "INVALID_TYPE")).toBe(true);
    }
  });

  it("rejects invalid scope", () => {
    const input = { ...validInput, scope: "invalid" };
    const result = validatePermissionReceiptInput(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "INVALID_VALUE")).toBe(true);
    }
  });

  it("rejects invalid effect", () => {
    const input = { ...validInput, effect: "delete" };
    const result = validatePermissionReceiptInput(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "INVALID_VALUE")).toBe(true);
    }
  });

  it("rejects negative timestamp", () => {
    const input = { ...validInput, requestedAt: -1 };
    const result = validatePermissionReceiptInput(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "NEGATIVE_VALUE")).toBe(true);
    }
  });

  it("rejects string too long", () => {
    const input = { ...validInput, requestId: "x".repeat(65) };
    const result = validatePermissionReceiptInput(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "STRING_TOO_LONG")).toBe(true);
    }
  });

  it("rejects array too long", () => {
    const input = { ...validInput, tags: Array(51).fill("tag") };
    const result = validatePermissionReceiptInput(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "ARRAY_TOO_LONG")).toBe(true);
    }
  });

  it("accepts valid optional fields", () => {
    const input = {
      ...validInput,
      repositoryContext: {
        owner: "myorg",
        repo: "myrepo",
        revision: "abc123",
      },
      workflowId: "wf-789",
      taskId: "task-101",
      tags: ["tag1", "tag2"],
      metadata: { key: "value" },
    };
    const result = validatePermissionReceiptInput(input);
    expect(result.valid).toBe(true);
  });

  it("rejects null input", () => {
    const result = validatePermissionReceiptInput(null);
    expect(result.valid).toBe(false);
  });

  it("rejects non-object input", () => {
    const result = validatePermissionReceiptInput("string");
    expect(result.valid).toBe(false);
  });
});

describe("WorkflowTransitionPayload Validation", () => {
  const validPayload = {
    transitionId: "trans-123",
    workflowId: "wf-456",
    fromState: "draft",
    toState: "review",
    transitionedAt: 1700000000000,
    actorId: "user-789",
    reason: "All checks passed",
  };

  it("accepts valid payload", () => {
    const result = validateWorkflowTransitionPayload(validPayload);
    expect(result.valid).toBe(true);
    if (result.valid) {
      expect(result.hash).toBeDefined();
    }
  });

  it("rejects unknown fields", () => {
    const input = { ...validPayload, extra: "field" };
    const result = validateWorkflowTransitionPayload(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "UNKNOWN_FIELD")).toBe(true);
    }
  });

  it("rejects missing required fields", () => {
    const input = { transitionId: "trans-123" };
    const result = validateWorkflowTransitionPayload(input);
    expect(result.valid).toBe(false);
  });

  it("accepts optional array fields", () => {
    const input = {
      ...validPayload,
      evidenceIds: ["ev-1", "ev-2"],
      passedChecks: ["check-1", "check-2"],
    };
    const result = validateWorkflowTransitionPayload(input);
    expect(result.valid).toBe(true);
  });

  it("rejects array items too long", () => {
    const input = {
      ...validPayload,
      evidenceIds: [Array(65).fill("x").join("")],
    };
    const result = validateWorkflowTransitionPayload(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "STRING_TOO_LONG")).toBe(true);
    }
  });
});

describe("ReadOnlyMCPInput Validation", () => {
  const validInput = {
    requestId: "req-123",
    ownerId: "user-456",
  };

  it("accepts valid input", () => {
    const result = validateReadOnlyMCPInput(validInput);
    expect(result.valid).toBe(true);
    if (result.valid) {
      expect(result.hash).toBeDefined();
    }
  });

  it("accepts optional repository field", () => {
    const input = {
      ...validInput,
      repository: { owner: "myorg", repo: "myrepo" },
    };
    const result = validateReadOnlyMCPInput(input);
    expect(result.valid).toBe(true);
  });

  it("accepts optional query field", () => {
    const input = {
      ...validInput,
      query: { path: "/src", limit: 10, offset: 0 },
    };
    const result = validateReadOnlyMCPInput(input);
    expect(result.valid).toBe(true);
  });

  it("rejects negative limit", () => {
    const input = {
      ...validInput,
      query: { limit: -1 },
    };
    const result = validateReadOnlyMCPInput(input);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "NEGATIVE_VALUE")).toBe(true);
    }
  });

  it("rejects negative offset", () => {
    const input = {
      ...validInput,
      query: { offset: -1 },
    };
    const result = validateReadOnlyMCPInput(input);
    expect(result.valid).toBe(false);
  });
});

describe("ReadOnlyMCPOutput Validation", () => {
  const validOutput = {
    requestId: "req-123",
    success: true,
    timestamp: 1700000000000,
  };

  it("accepts valid output", () => {
    const result = validateReadOnlyMCPOutput(validOutput);
    expect(result.valid).toBe(true);
    if (result.valid) {
      expect(result.hash).toBeDefined();
    }
  });

  it("accepts success=false with error", () => {
    const output = {
      ...validOutput,
      success: false,
      error: "Something went wrong",
    };
    const result = validateReadOnlyMCPOutput(output);
    expect(result.valid).toBe(true);
  });

  it("accepts metadata", () => {
    const output = {
      ...validOutput,
      metadata: {
        itemsCount: 42,
        executionTimeMs: 150,
        sourceRevision: "abc123",
      },
    };
    const result = validateReadOnlyMCPOutput(output);
    expect(result.valid).toBe(true);
  });

  it("rejects missing success field type", () => {
    const output = { ...validOutput, success: "yes" };
    const result = validateReadOnlyMCPOutput(output);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "INVALID_TYPE")).toBe(true);
    }
  });

  it("rejects error field too long", () => {
    const output = {
      ...validOutput,
      success: false,
      error: "x".repeat(257),
    };
    const result = validateReadOnlyMCPOutput(output);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errors.some((e) => e.code === "STRING_TOO_LONG")).toBe(true);
    }
  });
});
