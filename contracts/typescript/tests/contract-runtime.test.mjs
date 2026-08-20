import assert from "node:assert/strict";
import test from "node:test";
import {
  CONTRACT_CATALOG_MCP_TOOL,
  canonicalAuthorizationSnapshot,
  canonicalPayloadHash,
  contractSchemas,
  dispatchContractCatalog,
  validatePermissionCandidate,
  validateTransitionCandidate,
} from "../dist/index.js";

const REVISION = "a".repeat(40);
const permission = () => ({
  schemaVersion: "1.0.0",
  requestId: "permission-001",
  ownerId: "owner-001",
  repositoryOwner: "OuroborosCollective",
  repositoryName: "Sovereign-Studio-ato",
  repositoryRevision: REVISION,
  capability: "github.write",
  scope: "repository",
  effect: "mutate",
  requestedAt: 1735689600000,
  justification: "Apply an attested isolated contract pilot.",
  expectedOutcome: "A PR is created and remains pending target readback.",
});

test("strict PermissionReceiptInput rejects unknown fields and post-validation coercion candidates", () => {
  const valid = validatePermissionCandidate(permission());
  assert.equal(valid.status, "STRUCTURALLY_VALID");
  const extra = validatePermissionCandidate({ ...permission(), injected: true });
  assert.equal(extra.status, "STRUCTURALLY_INVALID");
  const coerced = validatePermissionCandidate({ ...permission(), requestedAt: "1735689600000" });
  assert.equal(coerced.status, "STRUCTURALLY_INVALID");
  for (const nonCanonicalNumber of [NaN, Infinity, -0]) {
    assert.equal(validatePermissionCandidate({ ...permission(), requestedAt: nonCanonicalNumber }).status, "STRUCTURALLY_INVALID");
  }
  const prototypeCandidate = JSON.parse(`${JSON.stringify(permission()).slice(0, -1)},"__proto__":{"polluted":true}}`);
  assert.equal(validatePermissionCandidate(prototypeCandidate).status, "STRUCTURALLY_INVALID");
});

test("canonical serialization yields a stable hash and authorization snapshot is immutable", () => {
  const first = { b: [true, "x"], a: { y: 2, x: 1 } };
  const second = { a: { x: 1, y: 2 }, b: [true, "x"] };
  assert.equal(canonicalPayloadHash(first), canonicalPayloadHash(second));
  const validated = validatePermissionCandidate(permission());
  assert.equal(validated.status, "STRUCTURALLY_VALID");
  const snapshot = canonicalAuthorizationSnapshot(validated);
  assert.throws(() => { snapshot.payload.justification = "mutated"; }, TypeError);
  assert.equal(snapshot.payloadHash, canonicalPayloadHash(permission()));
});

test("strict WorkflowTransitionPayload rejects unknown states and fields", () => {
  const valid = validateTransitionCandidate({
    schemaVersion: "1.0.0", transitionId: "transition-001", workflowId: "workflow-001",
    fromState: "PENDING", toState: "AUTHORIZED", transitionedAt: 1735689600000,
    actorId: "owner-001", reason: "Permission receipt created.",
  });
  assert.equal(valid.status, "STRUCTURALLY_VALID");
  const invalid = validateTransitionCandidate({
    schemaVersion: "1.0.0", transitionId: "transition-001", workflowId: "workflow-001",
    fromState: "PENDING", toState: "VERIFIED", transitionedAt: 1735689600000,
    actorId: "owner-001", reason: "Invalid direct verification.", unknown: true,
  });
  assert.equal(invalid.status, "STRUCTURALLY_INVALID");
});

test("MCP pilot rejects invalid input before dispatch and never upgrades success to VERIFIED", () => {
  assert.equal(CONTRACT_CATALOG_MCP_TOOL.effectClass, "read");
  assert.strictEqual(CONTRACT_CATALOG_MCP_TOOL.inputSchema, contractSchemas.schemas[2]);
  assert.strictEqual(CONTRACT_CATALOG_MCP_TOOL.outputSchema, contractSchemas.schemas[3]);
  const rejected = dispatchContractCatalog({ schemaVersion: "1.0.0", requestId: "read-001", subject: "permission-receipt", extra: true }, REVISION, "b".repeat(64));
  assert.deepEqual(rejected, { error: { code: "MCP_INPUT_INVALID", details: rejected.error.details } });
  const accepted = dispatchContractCatalog({ schemaVersion: "1.0.0", requestId: "read-001", subject: "permission-receipt" }, REVISION, "b".repeat(64));
  assert.ok("structuredContent" in accepted);
  assert.equal(accepted.structuredContent.status, "SUCCEEDED_UNVERIFIED");
});

test("generated schemas are closed contract projections", () => {
  const serialized = JSON.stringify(contractSchemas);
  assert.match(serialized, /"additionalProperties":false/);
  assert.match(serialized, /PermissionReceiptInput/);
  assert.match(serialized, /WorkflowTransitionPayload/);
});
