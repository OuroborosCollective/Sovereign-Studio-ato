/**
 * Contract Hash Computation
 * 
 * Generates deterministic hashes for contract artifacts.
 * Hashes bind source path, blob SHA, repository revision, and toolchain versions.
 * 
 * @module contract-hash
 */

import { createHash } from "crypto";
import { readFileSync } from "fs";
import type { ContractHashResult } from "./canonical-types.js";

// ============================================================================
// Hash Input Builder
// ============================================================================

/**
 * Input for building a contract hash.
 */
export interface BuildContractHashInput {
  sourcePath: string;
  sourceBlobSha: string;
  repositoryRevision: string;
  schemaVersion: string;
  contractSetId: string;
  typescriptVersion: string;
  additionalMetadata?: Record<string, string>;
}

/**
 * Canonical string representation of a contract hash input.
 * Produces deterministic output for the same input.
 */
export function canonicalizeHashInput(input: BuildContractHashInput): string {
  const parts: string[] = [
    `sourcePath:${input.sourcePath}`,
    `sourceBlobSha:${input.sourceBlobSha}`,
    `repositoryRevision:${input.repositoryRevision}`,
    `schemaVersion:${input.schemaVersion}`,
    `contractSetId:${input.contractSetId}`,
    `typescriptVersion:${input.typescriptVersion}`,
  ];

  // Add additional metadata in sorted order
  if (input.additionalMetadata) {
    const sortedKeys = Object.keys(input.additionalMetadata).sort();
    for (const key of sortedKeys) {
      parts.push(`${key}:${input.additionalMetadata[key]}`);
    }
  }

  return parts.join("\n");
}

/**
 * Computes a SHA-256 hash of the canonical input representation.
 */
export function computeContractHash(input: BuildContractHashInput): string {
  const canonical = canonicalizeHashInput(input);
  return createHash("sha256").update(canonical).digest("hex");
}

/**
 * Computes a full contract hash result including metadata.
 */
export function buildContractHash(
  input: BuildContractHashInput
): ContractHashResult {
  return {
    hash: computeContractHash(input),
    algorithm: "sha256",
    input: {
      sourcePath: input.sourcePath,
      sourceBlobSha: input.sourceBlobSha,
      repositoryRevision: input.repositoryRevision,
      schemaVersion: input.schemaVersion,
      contractSetId: input.contractSetId,
      typescriptVersion: input.typescriptVersion,
      additionalMetadata: input.additionalMetadata,
    },
    computedAt: new Date().toISOString(),
  };
}

// ============================================================================
// Git Blob Hash Reader
// ============================================================================

/**
 * Reads the Git blob SHA for a file.
 * Returns the SHA-1 hash that Git uses internally.
 */
export function getGitBlobSha(filePath: string): string {
  try {
    // Use git rev-parse to get the blob SHA
    const { execSync } = require("child_process");
    const sha = execSync(`git hash-object "${filePath}"`, {
      encoding: "utf8",
      timeout: 5000,
    }).trim();
    return sha;
  } catch {
    // Fallback: compute a SHA-256 of the content for non-git files
    const content = readFileSync(filePath);
    return createHash("sha1").update(content).digest("hex");
  }
}

/**
 * Gets the current repository revision (HEAD).
 */
export function getRepositoryRevision(): string {
  try {
    const { execSync } = require("child_process");
    return execSync("git rev-parse HEAD", {
      encoding: "utf8",
      timeout: 5000,
    }).trim();
  } catch {
    return "unknown";
  }
}

/**
 * Gets the TypeScript version from node_modules.
 */
export function getTypeScriptVersion(): string {
  try {
    const tsPackage = require("typescript/package.json");
    return tsPackage.version;
  } catch {
    return "unknown";
  }
}

// ============================================================================
// Contract Hash Builder
// ============================================================================

/**
 * Configuration for building a contract hash.
 */
export interface ContractHashConfig {
  sourcePath: string;
  schemaVersion?: string;
  contractSetId?: string;
  additionalMetadata?: Record<string, string>;
}

/**
 * Builds a contract hash for a given source file.
 * Reads Git blob SHA and repository revision automatically.
 */
export function buildContractHashForFile(
  config: ContractHashConfig
): ContractHashResult {
  const schemaVersion = config.schemaVersion || "1.0.0";
  const contractSetId = config.contractSetId || "typescript-contract-pilot-v1";

  const input: BuildContractHashInput = {
    sourcePath: config.sourcePath,
    sourceBlobSha: getGitBlobSha(config.sourcePath),
    repositoryRevision: getRepositoryRevision(),
    schemaVersion,
    contractSetId,
    typescriptVersion: getTypeScriptVersion(),
    additionalMetadata: config.additionalMetadata,
  };

  return buildContractHash(input);
}

// ============================================================================
// Hash Verification
// ============================================================================

/**
 * Verifies that a computed hash matches expected.
 */
export function verifyContractHash(
  computed: ContractHashResult,
  expectedHash: string
): boolean {
  return computed.hash === expectedHash;
}

/**
 * Verifies that a hash input matches a computed hash.
 */
export function verifyHashInput(
  input: BuildContractHashInput,
  expectedHash: string
): boolean {
  const computed = computeContractHash(input);
  return computed === expectedHash;
}

// ============================================================================
// Schema Drift Detection
// ============================================================================

/**
 * Detects drift between expected and actual schema versions.
 */
export interface SchemaDriftReport {
  hasDrift: boolean;
  expectedVersion: string;
  actualVersion: string;
  driftDetails?: string;
}

/**
 * Checks for schema version drift.
 */
export function checkSchemaDrift(
  expectedVersion: string,
  actualVersion: string
): SchemaDriftReport {
  const hasDrift = expectedVersion !== actualVersion;
  return {
    hasDrift,
    expectedVersion,
    actualVersion,
    driftDetails: hasDrift
      ? `Schema version mismatch: expected ${expectedVersion}, got ${actualVersion}`
      : undefined,
  };
}
