/**
 * TypeScript Contract Pilot - Main Export
 * 
 * Compile-time TypeScript contract generation for MCP and receipt boundaries.
 * 
 * @module index
 */

// Re-export all types
export type {
  PermissionReceiptInput,
  WorkflowTransitionPayload,
  ReadOnlyMCPInput,
  ReadOnlyMCPOutput,
  StrictPermissionReceiptInput,
  StrictWorkflowTransitionPayload,
  StrictReadOnlyMCPInput,
  StrictReadOnlyMCPOutput,
  ValidationResult,
  ValidationError,
  ValidationErrorCode,
  TruthClass,
  EffectClass,
  CapabilityScope,
  ToolContractMetadata,
  ContractHashInput,
  ContractHashResult,
} from "./canonical-types.js";

// Re-export constants
export {
  CONTRACT_SCHEMA_VERSION,
  CONTRACT_SET_ID,
} from "./canonical-types.js";

// Re-export validators
export {
  validatePermissionReceiptInput,
  validateWorkflowTransitionPayload,
  validateReadOnlyMCPInput,
  validateReadOnlyMCPOutput,
  validators,
  type ValidatorName,
} from "./validation.js";

// Re-export schemas
export {
  generatePermissionReceiptInputSchema,
  generateWorkflowTransitionPayloadSchema,
  generateReadOnlyMCPInputSchema,
  generateReadOnlyMCPOutputSchema,
  generateAllSchemas,
  generateSchemaMetadata,
  toMCPInputSchema,
  generateMCPToolSchemas,
  type JsonSchema,
  type SchemaMetadata,
  type SchemaName,
} from "./schemas.js";

// Re-export hash utilities
export {
  buildContractHash,
  buildContractHashForFile,
  verifyContractHash,
  verifyHashInput,
  checkSchemaDrift,
  type BuildContractHashInput,
  type ContractHashConfig,
  type SchemaDriftReport,
} from "./contract-hash.js";

// Re-export hash computation utilities
export { computeInputHashSync } from "./validation.js";
