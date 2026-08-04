from __future__ import annotations

import pytest

from agent_runtime.neuro_architecture_contract import (
    EvidenceEnvelope,
    Lane,
    NeuroAliasBinding,
    EvidenceClass,
    validate_causal_chain,
    verify_lane_transition,
)

SHA40 = "a" * 40
SHA256 = "b" * 64


def make_envelope(
    *,
    event_id: str = "event-0001",
    lane: Lane = Lane.DETERMINISTIC_VERIFICATION,
    tick: int = 1000,
    sequence: int = 1,
    previous_evidence_sha256: str = SHA256,
    canonical: bool = True,
) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        schema_version="sovereign.neuro-architecture-envelope.v1",
        system_id="sovereign-studio-ato",
        revision_sha=SHA40,
        policy_sha256=SHA256,
        event_id=event_id,
        lane=lane,
        tick=tick,
        sequence=sequence,
        payload_sha256=SHA256,
        causal_parent_sha256=SHA256,
        previous_evidence_sha256=previous_evidence_sha256,
        producer_identity="neuro-contract-test",
        canonical=canonical,
    )


def test_alias_binding_keeps_biology_metaphorical_and_project_scoped() -> None:
    binding = NeuroAliasBinding(
        alias="Thalamus",
        canonical_component="neuro.thalamic-router",
        evidence_class=EvidenceClass.PLAUSIBLE_ANALOGY,
        software_scope="sovereign-studio-ato",
        scientific_claim="Thalamic nuclei relay and regulate distributed signals.",
        limitations=("Not a biological replica.",),
    )

    assert binding.evidence_class is EvidenceClass.PLAUSIBLE_ANALOGY
    assert binding.software_scope == "sovereign-studio-ato"


def test_side_channel_cannot_be_canonical() -> None:
    with pytest.raises(ValueError, match="cannot be canonical"):
        make_envelope(lane=Lane.COGNITIVE_SIDE_CHANNEL, canonical=True)


def test_motor_authorization_must_be_canonical() -> None:
    with pytest.raises(ValueError, match="must be canonical"):
        make_envelope(lane=Lane.MOTOR_AUTHORIZATION, canonical=False)


def test_lane_transition_contract_blocks_side_channel_authorization() -> None:
    assert verify_lane_transition(Lane.SENSORY_INTAKE, Lane.THALAMIC_ROUTING)
    assert verify_lane_transition(Lane.DETERMINISTIC_VERIFICATION, Lane.MOTOR_AUTHORIZATION)
    assert not verify_lane_transition(Lane.COGNITIVE_SIDE_CHANNEL, Lane.MOTOR_AUTHORIZATION)


def test_evidence_hash_is_reproducible() -> None:
    first = make_envelope()
    second = make_envelope()

    assert first.evidence_sha256() == second.evidence_sha256()
    assert len(first.evidence_sha256()) == 64


def test_causal_chain_accepts_ordered_hash_linkage() -> None:
    first = make_envelope(sequence=1)
    second = make_envelope(
        event_id="event-0002",
        tick=1001,
        sequence=2,
        previous_evidence_sha256=first.evidence_sha256(),
    )

    assert validate_causal_chain([first, second]) == (True, "VERIFIED")


def test_causal_chain_rejects_sequence_gap() -> None:
    first = make_envelope(sequence=1)
    second = make_envelope(
        event_id="event-0002",
        tick=1001,
        sequence=3,
        previous_evidence_sha256=first.evidence_sha256(),
    )

    assert validate_causal_chain([first, second]) == (False, "SEQUENCE_GAP")
