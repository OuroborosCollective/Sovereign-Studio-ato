import typia from "typia";
import type {
  ContractCatalogInput,
  ContractCatalogOutput,
  PermissionReceiptInput,
  WorkflowTransitionPayload,
} from "./contracts.js";

/** Strict equality validators reject unknown properties and never coerce. */
export const validatePermissionReceiptInput = typia.createValidateEquals<PermissionReceiptInput>();
export const validateWorkflowTransitionPayload = typia.createValidateEquals<WorkflowTransitionPayload>();
export const validateContractCatalogInput = typia.createValidateEquals<ContractCatalogInput>();
export const validateContractCatalogOutput = typia.createValidateEquals<ContractCatalogOutput>();

/** Generated from the same TypeScript types at transformer build time. */
export const contractSchemas = typia.json.schemas<[
  PermissionReceiptInput,
  WorkflowTransitionPayload,
  ContractCatalogInput,
  ContractCatalogOutput
]>();

export type ContractSubject = "permission-receipt" | "workflow-transition";

export const mcpInputSchema = contractSchemas.schemas[2];
export const mcpOutputSchema = contractSchemas.schemas[3];
