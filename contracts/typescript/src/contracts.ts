import { tags } from "typia";

export const CONTRACT_SET_ID = "sovereign.typescript-contract-pilot" as const;
export const CONTRACT_SCHEMA_VERSION = "1.0.0" as const;

export type ShortText = string & tags.MinLength<1> & tags.MaxLength<64>;
export type MediumText = string & tags.MinLength<1> & tags.MaxLength<256>;
export type LongText = string & tags.MinLength<1> & tags.MaxLength<4096>;
export type Revision = string & tags.Pattern<"^[a-f0-9]{40}$">;
export type PositiveEpochMillis = number & tags.Type<"uint64">;

/**
 * Canonical input for requesting a permission receipt. Structural validity is
 * deliberately distinct from authorization and target-system readback.
 */
export interface PermissionReceiptInput {
  schemaVersion: typeof CONTRACT_SCHEMA_VERSION;
  requestId: ShortText;
  ownerId: ShortText;
  repositoryOwner: ShortText;
  repositoryName: ShortText;
  repositoryRevision: Revision;
  capability: "github.write" | "workflow.transition";
  scope: "repository" | "workflow";
  effect: "mutate" | "coordinate";
  requestedAt: PositiveEpochMillis;
  justification: MediumText;
  expectedOutcome: LongText;
  workflowId?: ShortText;
}

/** Canonical workflow state transition submitted before permission binding. */
export interface WorkflowTransitionPayload {
  schemaVersion: typeof CONTRACT_SCHEMA_VERSION;
  transitionId: ShortText;
  workflowId: ShortText;
  fromState: "PENDING" | "AUTHORIZED" | "EXECUTING" | "SUCCEEDED_UNVERIFIED" | "FAILED";
  toState: "AUTHORIZED" | "EXECUTING" | "SUCCEEDED_UNVERIFIED" | "VERIFIED" | "FAILED";
  transitionedAt: PositiveEpochMillis;
  actorId: ShortText;
  reason: MediumText;
  evidenceId?: ShortText;
}

/** Input for the isolated, side-effect-free contract catalog MCP pilot tool. */
export interface ContractCatalogInput {
  schemaVersion: typeof CONTRACT_SCHEMA_VERSION;
  requestId: ShortText;
  subject: "permission-receipt" | "workflow-transition";
}

/**
 * The pilot deliberately returns only SUCCEEDED_UNVERIFIED. A schema-valid
 * output is not authority or proof of a target-system state.
 */
export interface ContractCatalogOutput {
  schemaVersion: typeof CONTRACT_SCHEMA_VERSION;
  requestId: ShortText;
  status: "SUCCEEDED_UNVERIFIED";
  subject: "permission-receipt" | "workflow-transition";
  contractSetId: typeof CONTRACT_SET_ID;
  contractHash: string & tags.Pattern<"^[a-f0-9]{64}$">;
  sourceRevision: Revision;
}
