from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,159}$")


class EvidenceClass(str, Enum):
    METAPHOR = "E0"
    PLAUSIBLE_ANALOGY = "E1"
    BROAD_FUNCTIONAL_EVIDENCE = "E2"
    ANATOMICAL_CONNECTION_EVIDENCE = "E3"
    REPRODUCIBLE_FORMAL_PROPERTY = "E4"


class Lane(str, Enum):
    SENSORY_INTAKE = "sensory-intake"
    THALAMIC_ROUTING = "thalamic-routing"
    REFLEX_SAFETY = "reflex-safety"
    DETERMINISTIC_VERIFICATION = "deterministic-verification"
    COGNITIVE_SIDE_CHANNEL = "cognitive-side-channel"
    EVIDENCE = "evidence"
    PERSISTENCE = "persistence"
    CEREBELLAR_CORRECTION = "cerebellar-correction"
    MOTOR_AUTHORIZATION = "motor-authorization"
    HOMEOSTASIS = "homeostasis"
    QUARANTINE = "quarantine"


CANONICAL_TRUTH_LANES = frozenset({
    Lane.DETERMINISTIC_VERIFICATION,
    Lane.EVIDENCE,
    Lane.MOTOR_AUTHORIZATION,
})

NON_CANONICAL_LANES = frozenset({Lane.COGNITIVE_SIDE_CHANNEL})


@dataclass(frozen=True, slots=True)
class NeuroAliasBinding:
    alias: str
    canonical_component: str
    evidence_class: EvidenceClass
    software_scope: str
    scientific_claim: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.alias.strip():
            raise ValueError("alias must not be empty")
        if not _ID.fullmatch(self.canonical_component):
            raise ValueError("canonical_component must be a stable lowercase identifier")
        if self.software_scope not in {"sovereign-studio-ato", "arelorian-wasd-side-channel"}:
            raise ValueError("software_scope violates project isolation")
        if not self.scientific_claim.strip():
            raise ValueError("scientific_claim must not be empty")


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    schema_version: str
    system_id: str
    revision_sha: str
    policy_sha256: str
    event_id: str
    lane: Lane
    tick: int
    sequence: int
    payload_sha256: str
    causal_parent_sha256: str
    previous_evidence_sha256: str
    producer_identity: str
    canonical: bool
    side_channel_reference: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != "sovereign.neuro-architecture-envelope.v1":
            raise ValueError("unsupported schema_version")
        if not _ID.fullmatch(self.system_id):
            raise ValueError("invalid system_id")
        if not _SHA40.fullmatch(self.revision_sha):
            raise ValueError("invalid revision_sha")
        for value, name in (
            (self.policy_sha256, "policy_sha256"),
            (self.payload_sha256, "payload_sha256"),
            (self.causal_parent_sha256, "causal_parent_sha256"),
            (self.previous_evidence_sha256, "previous_evidence_sha256"),
        ):
            if not _SHA256.fullmatch(value):
                raise ValueError(f"invalid {name}")
        if not _ID.fullmatch(self.event_id):
            raise ValueError("invalid event_id")
        if self.tick < 0 or self.sequence < 0:
            raise ValueError("tick and sequence must be non-negative integers")
        if not self.producer_identity.strip():
            raise ValueError("producer_identity must not be empty")
        if self.lane in NON_CANONICAL_LANES and self.canonical:
            raise ValueError("cognitive side-channel output cannot be canonical")
        if self.lane == Lane.MOTOR_AUTHORIZATION and not self.canonical:
            raise ValueError("motor authorization must be canonical")

    def canonical_record(self) -> Mapping[str, Any]:
        return {
            "canonical": self.canonical,
            "causalParentSha256": self.causal_parent_sha256,
            "eventId": self.event_id,
            "lane": self.lane.value,
            "payloadSha256": self.payload_sha256,
            "policySha256": self.policy_sha256,
            "previousEvidenceSha256": self.previous_evidence_sha256,
            "producerIdentity": self.producer_identity,
            "revisionSha": self.revision_sha,
            "schemaVersion": self.schema_version,
            "sequence": self.sequence,
            "sideChannelReference": self.side_channel_reference,
            "systemId": self.system_id,
            "tick": self.tick,
        }

    def evidence_sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_record(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def verify_lane_transition(source: Lane, target: Lane) -> bool:
    allowed: Mapping[Lane, frozenset[Lane]] = {
        Lane.SENSORY_INTAKE: frozenset({Lane.THALAMIC_ROUTING, Lane.QUARANTINE}),
        Lane.THALAMIC_ROUTING: frozenset({
            Lane.REFLEX_SAFETY,
            Lane.DETERMINISTIC_VERIFICATION,
            Lane.COGNITIVE_SIDE_CHANNEL,
            Lane.QUARANTINE,
        }),
        Lane.REFLEX_SAFETY: frozenset({Lane.EVIDENCE, Lane.MOTOR_AUTHORIZATION, Lane.QUARANTINE}),
        Lane.DETERMINISTIC_VERIFICATION: frozenset({Lane.EVIDENCE, Lane.MOTOR_AUTHORIZATION, Lane.QUARANTINE}),
        Lane.COGNITIVE_SIDE_CHANNEL: frozenset({Lane.EVIDENCE}),
        Lane.EVIDENCE: frozenset({Lane.PERSISTENCE, Lane.CEREBELLAR_CORRECTION}),
        Lane.PERSISTENCE: frozenset({Lane.CEREBELLAR_CORRECTION}),
        Lane.CEREBELLAR_CORRECTION: frozenset({Lane.EVIDENCE, Lane.QUARANTINE}),
        Lane.MOTOR_AUTHORIZATION: frozenset({Lane.EVIDENCE, Lane.CEREBELLAR_CORRECTION}),
        Lane.HOMEOSTASIS: frozenset({Lane.THALAMIC_ROUTING, Lane.QUARANTINE}),
        Lane.QUARANTINE: frozenset({Lane.EVIDENCE}),
    }
    return target in allowed[source]


def validate_causal_chain(envelopes: Sequence[EvidenceEnvelope]) -> tuple[bool, str]:
    if not envelopes:
        return False, "EMPTY_CHAIN"
    previous_hash = envelopes[0].previous_evidence_sha256
    previous_sequence = envelopes[0].sequence - 1
    previous_tick = envelopes[0].tick
    for envelope in envelopes:
        if envelope.previous_evidence_sha256 != previous_hash:
            return False, "PREVIOUS_HASH_MISMATCH"
        if envelope.sequence != previous_sequence + 1:
            return False, "SEQUENCE_GAP"
        if envelope.tick < previous_tick:
            return False, "TICK_REGRESSION"
        previous_hash = envelope.evidence_sha256()
        previous_sequence = envelope.sequence
        previous_tick = envelope.tick
    return True, "VERIFIED"
