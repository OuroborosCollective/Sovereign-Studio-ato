import { createHash } from "node:crypto";
import type { ContractCatalogOutput, PermissionReceiptInput, WorkflowTransitionPayload } from "./contracts.js";
import {
  type ContractSubject,
  validateContractCatalogInput,
  validateContractCatalogOutput,
  validatePermissionReceiptInput,
  validateWorkflowTransitionPayload,
} from "./projections.js";

export type StructuralValidation<T> =
  | { status: "STRUCTURALLY_VALID"; data: T; payloadHash: string }
  | { status: "STRUCTURALLY_INVALID"; errorCodes: string[] };

type UnknownValidation = { success?: unknown; data?: unknown; errors?: unknown };

function canonicalize(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) throw new TypeError("non-canonical number");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${canonicalize(object[key])}`).join(",")}}`;
  }
  throw new TypeError("non-JSON contract value");
}

export function canonicalPayloadHash(value: unknown): string {
  return createHash("sha256").update(canonicalize(value), "utf8").digest("hex");
}

function errorCodes(result: unknown): string[] {
  const errors = (result as UnknownValidation).errors;
  if (!Array.isArray(errors)) return ["INVALID_CONTRACT_PAYLOAD"];
  return errors.slice(0, 16).map((entry) => {
    if (!entry || typeof entry !== "object") return "INVALID_CONTRACT_PAYLOAD";
    const item = entry as Record<string, unknown>;
    return typeof item.path === "string" ? `INVALID_AT_${item.path.slice(0, 96)}` : "INVALID_CONTRACT_PAYLOAD";
  });
}

function structural<T>(result: unknown): StructuralValidation<T> {
  const validation = result as UnknownValidation;
  if (validation.success !== true || validation.data === undefined) {
    return { status: "STRUCTURALLY_INVALID", errorCodes: errorCodes(validation) };
  }
  const data = validation.data as T;
  try {
    return { status: "STRUCTURALLY_VALID", data, payloadHash: canonicalPayloadHash(data) };
  } catch {
    return { status: "STRUCTURALLY_INVALID", errorCodes: ["NON_CANONICAL_JSON_VALUE"] };
  }
}

export const validatePermissionCandidate = (input: unknown): StructuralValidation<PermissionReceiptInput> =>
  structural<PermissionReceiptInput>(validatePermissionReceiptInput(input));

export const validateTransitionCandidate = (input: unknown): StructuralValidation<WorkflowTransitionPayload> =>
  structural<WorkflowTransitionPayload>(validateWorkflowTransitionPayload(input));

export type CanonicalAuthorizationSnapshot<T> = Readonly<{ payload: Readonly<T>; payloadHash: string }>;

/** Capture a detached, deep-frozen JSON snapshot before a permission receipt is requested. */
export function canonicalAuthorizationSnapshot<T>(validation: StructuralValidation<T>): CanonicalAuthorizationSnapshot<T> {
  if (validation.status !== "STRUCTURALLY_VALID") throw new TypeError("cannot snapshot invalid payload");
  const snapshot = JSON.parse(canonicalize(validation.data)) as T;
  const freeze = (value: unknown): unknown => {
    if (value && typeof value === "object") {
      for (const child of Object.values(value as Record<string, unknown>)) freeze(child);
      Object.freeze(value);
    }
    return value;
  };
  return Object.freeze({ payload: freeze(snapshot) as Readonly<T>, payloadHash: validation.payloadHash });
}

export type CatalogDispatchResult =
  | { error: { code: "MCP_INPUT_INVALID" | "MCP_OUTPUT_INVALID"; details: string[] } }
  | { structuredContent: ContractCatalogOutput };

/**
 * Read-only pilot dispatcher. Input validation occurs before dispatch and output
 * validation occurs before structuredContent. It intentionally cannot authorize
 * a mutation or return VERIFIED.
 */
export function dispatchContractCatalog(input: unknown, sourceRevision: string, contractHash: string): CatalogDispatchResult {
  const candidate = validateContractCatalogInput(input);
  if (candidate.success !== true || candidate.data === undefined) {
    return { error: { code: "MCP_INPUT_INVALID", details: errorCodes(candidate).slice(0, 8) } };
  }
  const output = {
    schemaVersion: "1.0.0",
    requestId: candidate.data.requestId,
    status: "SUCCEEDED_UNVERIFIED",
    subject: candidate.data.subject as ContractSubject,
    contractSetId: "sovereign.typescript-contract-pilot",
    contractHash,
    sourceRevision,
  };
  const checked = validateContractCatalogOutput(output);
  if (checked.success !== true || checked.data === undefined) {
    return { error: { code: "MCP_OUTPUT_INVALID", details: errorCodes(checked).slice(0, 8) } };
  }
  return { structuredContent: checked.data };
}
