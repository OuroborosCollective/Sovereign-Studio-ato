export const NEURO_ARCHITECTURE_SCHEMA_VERSION =
  "sovereign.neuro-architecture-envelope.v1" as const;

export type EvidenceClass = "E0" | "E1" | "E2" | "E3" | "E4";

export type NeuroLane =
  | "sensory-intake"
  | "thalamic-routing"
  | "reflex-safety"
  | "deterministic-verification"
  | "cognitive-side-channel"
  | "evidence"
  | "persistence"
  | "cerebellar-correction"
  | "motor-authorization"
  | "homeostasis"
  | "quarantine";

export interface NeuroAliasBinding {
  readonly alias: string;
  readonly canonicalComponent: string;
  readonly evidenceClass: EvidenceClass;
  readonly softwareScope: "sovereign-studio-ato" | "areloria-wasd-side-channel";
  readonly scientificClaim: string;
  readonly limitations: readonly string[];
}

export interface NeuroEvidenceEnvelope {
  readonly schemaVersion: typeof NEURO_ARCHITECTURE_SCHEMA_VERSION;
  readonly systemId: string;
  readonly revisionSha: string;
  readonly policySha256: string;
  readonly eventId: string;
  readonly lane: NeuroLane;
  readonly tick: string;
  readonly sequence: string;
  readonly payloadSha256: string;
  readonly causalParentSha256: string;
  readonly previousEvidenceSha256: string;
  readonly producerIdentity: string;
  readonly canonical: boolean;
  readonly sideChannelReference?: string;
}

export interface ValidationResult {
  readonly ok: boolean;
  readonly errors: readonly string[];
}

const SHA40 = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const STABLE_ID = /^[a-z0-9][a-z0-9._:-]{1,159}$/;
const UINT = /^(0|[1-9][0-9]*)$/;

export const canonicalTruthLanes: ReadonlySet<NeuroLane> = new Set([
  "deterministic-verification",
  "evidence",
  "motor-authorization",
]);

export const nonCanonicalLanes: ReadonlySet<NeuroLane> = new Set([
  "cognitive-side-channel",
]);

const allowedTransitions: Readonly<Record<NeuroLane, ReadonlySet<NeuroLane>>> = {
  "sensory-intake": new Set(["thalamic-routing", "quarantine"]),
  "thalamic-routing": new Set([
    "reflex-safety",
    "deterministic-verification",
    "cognitive-side-channel",
    "quarantine",
  ]),
  "reflex-safety": new Set(["evidence", "motor-authorization", "quarantine"]),
  "deterministic-verification": new Set(["evidence", "motor-authorization", "quarantine"]),
  "cognitive-side-channel": new Set(["evidence"]),
  evidence: new Set(["persistence", "cerebellar-correction"]),
  persistence: new Set(["cerebellar-correction"]),
  "cerebellar-correction": new Set(["evidence", "quarantine"]),
  "motor-authorization": new Set(["evidence", "cerebellar-correction"]),
  homeostasis: new Set(["thalamic-routing", "quarantine"]),
  quarantine: new Set(["evidence"]),
};

export function verifyLaneTransition(source: NeuroLane, target: NeuroLane): boolean {
  return allowedTransitions[source].has(target);
}

export function validateNeuroAliasBinding(binding: NeuroAliasBinding): ValidationResult {
  const errors: string[] = [];
  if (!binding.alias.trim()) errors.push("EMPTY_ALIAS");
  if (!STABLE_ID.test(binding.canonicalComponent)) errors.push("INVALID_CANONICAL_COMPONENT");
  if (!binding.scientificClaim.trim()) errors.push("EMPTY_SCIENTIFIC_CLAIM");
  if (
    binding.softwareScope !== "sovereign-studio-ato" &&
    binding.softwareScope !== "areloria-wasd-side-channel"
  ) {
    errors.push("PROJECT_ISOLATION_VIOLATION");
  }
  return { ok: errors.length === 0, errors };
}

export function validateNeuroEvidenceEnvelope(
  envelope: NeuroEvidenceEnvelope,
): ValidationResult {
  const errors: string[] = [];
  if (envelope.schemaVersion !== NEURO_ARCHITECTURE_SCHEMA_VERSION) {
    errors.push("UNSUPPORTED_SCHEMA_VERSION");
  }
  if (!STABLE_ID.test(envelope.systemId)) errors.push("INVALID_SYSTEM_ID");
  if (!STABLE_ID.test(envelope.eventId)) errors.push("INVALID_EVENT_ID");
  if (!SHA40.test(envelope.revisionSha)) errors.push("INVALID_REVISION_SHA");
  if (!SHA256.test(envelope.policySha256)) errors.push("INVALID_POLICY_SHA256");
  if (!SHA256.test(envelope.payloadSha256)) errors.push("INVALID_PAYLOAD_SHA256");
  if (!SHA256.test(envelope.causalParentSha256)) errors.push("INVALID_CAUSAL_PARENT_SHA256");
  if (!SHA256.test(envelope.previousEvidenceSha256)) {
    errors.push("INVALID_PREVIOUS_EVIDENCE_SHA256");
  }
  if (!UINT.test(envelope.tick)) errors.push("INVALID_TICK");
  if (!UINT.test(envelope.sequence)) errors.push("INVALID_SEQUENCE");
  if (!envelope.producerIdentity.trim()) errors.push("EMPTY_PRODUCER_IDENTITY");
  if (nonCanonicalLanes.has(envelope.lane) && envelope.canonical) {
    errors.push("SIDE_CHANNEL_CANNOT_BE_CANONICAL");
  }
  if (envelope.lane === "motor-authorization" && !envelope.canonical) {
    errors.push("MOTOR_AUTHORIZATION_MUST_BE_CANONICAL");
  }
  return { ok: errors.length === 0, errors };
}

export const defaultNeuroAliasBindings: readonly NeuroAliasBinding[] = [
  {
    alias: "Thalamus",
    canonicalComponent: "neuro.thalamic-router",
    evidenceClass: "E1",
    softwareScope: "sovereign-studio-ato",
    scientificClaim:
      "Thalamic nuclei relay and regulate sensory, motor, limbic, arousal and cortical communication rather than acting as a single undifferentiated gateway.",
    limitations: ["Software routing is a functional analogy, not a biological replica."],
  },
  {
    alias: "Hypothalamus",
    canonicalComponent: "neuro.homeostasis-controller",
    evidenceClass: "E1",
    softwareScope: "sovereign-studio-ato",
    scientificClaim:
      "Hypothalamic nuclei coordinate autonomic, endocrine and homeostatic regulation through distributed connections.",
    limitations: ["Metrics and rate limiting model regulation only; they do not model endocrine biology."],
  },
  {
    alias: "Cerebellum",
    canonicalComponent: "neuro.execution-correction",
    evidenceClass: "E1",
    softwareScope: "sovereign-studio-ato",
    scientificClaim:
      "Cerebellar circuits compare intended movement with feedback and adjust timing, force and trajectory.",
    limitations: ["The software lane compares planned, executed and observed outcomes only."],
  },
  {
    alias: "Hippocampus",
    canonicalComponent: "neuro.evidence-consolidation",
    evidenceClass: "E1",
    softwareScope: "sovereign-studio-ato",
    scientificClaim:
      "Hippocampal and medial temporal systems contribute to memory registration, consolidation and retrieval through wider limbic and cortical connections.",
    limitations: ["Evidence persistence is not equivalent to human episodic memory."],
  },
  {
    alias: "Amygdala",
    canonicalComponent: "neuro.reversible-safety-reflex",
    evidenceClass: "E1",
    softwareScope: "sovereign-studio-ato",
    scientificClaim:
      "Amygdaloid nuclei participate in salience, stress-related, memory and behavioral regulation through cortical, hypothalamic, thalamic and striatal circuits.",
    limitations: ["The lane may trigger reversible protection only, never an irreversible effect."],
  },
];
