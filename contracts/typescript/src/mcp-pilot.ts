import type { ContractCatalogOutput } from "./contracts.js";
import { mcpInputSchema, mcpOutputSchema } from "./projections.js";
import { dispatchContractCatalog, type CatalogDispatchResult } from "./runtime.js";

/**
 * Isolated MCP publication surface. It has no write capability, no credential
 * access and no independent registry authority.
 */
export const CONTRACT_CATALOG_MCP_TOOL = Object.freeze({
  name: "sovereign_contract_catalog",
  effectClass: "read" as const,
  inputSchema: mcpInputSchema,
  outputSchema: mcpOutputSchema,
  execute(input: unknown, sourceRevision: string, contractHash: string): CatalogDispatchResult {
    return dispatchContractCatalog(input, sourceRevision, contractHash);
  },
});

export type ContractCatalogStructuredContent = ContractCatalogOutput;
