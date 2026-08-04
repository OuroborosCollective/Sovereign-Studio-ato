import { describe, expect, it } from "vitest";
import {
  NEURO_ARCHITECTURE_SCHEMA_VERSION,
  defaultNeuroAliasBindings,
  validateNeuroAliasBinding,
  validateNeuroEvidenceEnvelope,
  verifyLaneTransition,
  type NeuroEvidenceEnvelope,
} from "./neuroArchitectureContract";

const SHA40 = "a".repeat(40);
const SHA256 = "b".repeat(64);

function envelope(
  overrides: Partial<NeuroEvidenceEnvelope> = {},
): NeuroEvidenceEnvelope {
  return {
    schemaVersion: NEURO_ARCHITECTURE_SCHEMA_VERSION,
    systemId: "sovereign-studio-ato",
    revisionSha: SHA40,
    policySha256: SHA256,
    eventId: "event-0001",
    lane: "deterministic-verification",
    tick: "1000",
    sequence: "1",
    payloadSha256: SHA256,
    causalParentSha256: SHA256,
    previousEvidenceSha256: SHA256,
    producerIdentity: "neuro-contract-test",
    canonical: true,
    ...overrides,
  };
}

describe("neuroArchitectureContract", () => {
  it("keeps all default biological names as validated aliases", () => {
    for (const binding of defaultNeuroAliasBindings) {
      expect(validateNeuroAliasBinding(binding)).toEqual({ ok: true, errors: [] });
      expect(binding.evidenceClass).toBe("E1");
      expect(binding.softwareScope).toBe("sovereign-studio-ato");
    }
  });

  it("permits only explicitly defined lane transitions", () => {
    expect(verifyLaneTransition("sensory-intake", "thalamic-routing")).toBe(true);
    expect(verifyLaneTransition("cognitive-side-channel", "motor-authorization")).toBe(false);
    expect(verifyLaneTransition("deterministic-verification", "motor-authorization")).toBe(true);
  });

  it("rejects a canonical cognitive side-channel output", () => {
    expect(
      validateNeuroEvidenceEnvelope(
        envelope({ lane: "cognitive-side-channel", canonical: true }),
      ),
    ).toEqual({ ok: false, errors: ["SIDE_CHANNEL_CANNOT_BE_CANONICAL"] });
  });

  it("requires motor authorization to be canonical", () => {
    expect(
      validateNeuroEvidenceEnvelope(
        envelope({ lane: "motor-authorization", canonical: false }),
      ),
    ).toEqual({ ok: false, errors: ["MOTOR_AUTHORIZATION_MUST_BE_CANONICAL"] });
  });

  it("fails closed on revision, hash and integer contract drift", () => {
    const result = validateNeuroEvidenceEnvelope(
      envelope({
        revisionSha: "main",
        payloadSha256: "not-a-hash",
        tick: "1.5",
        sequence: "-1",
      }),
    );

    expect(result.ok).toBe(false);
    expect(result.errors).toEqual([
      "INVALID_REVISION_SHA",
      "INVALID_PAYLOAD_SHA256",
      "INVALID_TICK",
      "INVALID_SEQUENCE",
    ]);
  });
});
