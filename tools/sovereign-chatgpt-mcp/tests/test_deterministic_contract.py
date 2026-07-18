from __future__ import annotations

import pytest

from deterministic_vector_harness import build_python_results, load_document
from deterministic_contract import (
    KAPPA_SCALE,
    canonical_decimal_to_units,
    canonical_sha256,
    divide_fixed,
    multiply_fixed,
    replay_verify,
    state_sha256,
    transition_preview,
    trunc_div_toward_zero,
)


TRANSITIONS = {
    "RECEIVED": {"CLASSIFY": "SCOPING"},
    "SCOPING": {"PLAN": "PLANNED"},
}


def test_kappa_decimal_boundary_never_requires_float() -> None:
    assert KAPPA_SCALE == 1_000_000
    assert canonical_decimal_to_units("1.25") == 1_250_000
    assert canonical_decimal_to_units("-1.25") == -1_250_000
    assert canonical_decimal_to_units("0.0000009") == 0
    assert canonical_decimal_to_units("-0.0000009") == 0
    with pytest.raises(ValueError, match="canonical decimal"):
        canonical_decimal_to_units("01.25")


def test_signed_fixed_math_uses_truncation_toward_zero() -> None:
    assert trunc_div_toward_zero(-7, 3) == -2
    assert trunc_div_toward_zero(7, -3) == -2
    assert trunc_div_toward_zero(-7, -3) == 2
    assert multiply_fixed(-1_500_000, 500_000) == -750_000
    assert divide_fixed(-750_000, 500_000) == -1_500_000


def test_canonical_hash_rejects_float_state_and_normalizes_key_order() -> None:
    first = {"status": "RECEIVED", "version": 0, "payload": {"b": 2, "a": 1}}
    second = {"payload": {"a": 1, "b": 2}, "version": 0, "status": "RECEIVED"}
    assert canonical_sha256(first) == canonical_sha256(second)
    with pytest.raises(TypeError, match="contains a float"):
        canonical_sha256({"score": 0.5})


def test_transition_preview_is_pure_versioned_and_hash_chained() -> None:
    state = {"status": "RECEIVED", "version": 0, "mission": "inspect"}
    action = {
        "type": "CLASSIFY",
        "targetStatus": "SCOPING",
        "patch": {"intent": "read_only_analysis"},
    }
    first = transition_preview(
        state,
        action,
        TRANSITIONS,
        expected_version=0,
        expected_state_hash=canonical_sha256(state),
    )
    second = transition_preview(
        state,
        action,
        TRANSITIONS,
        expected_version=0,
        expected_state_hash=canonical_sha256(state),
    )

    assert first == second
    assert first["allowed"] is True
    assert first["nextState"]["status"] == "SCOPING"
    assert first["nextState"]["version"] == 1
    assert first["actionHash"]
    assert first["nextStateHash"]
    assert first["chainHash"]
    assert first["mutationPerformed"] is False
    assert state == {"status": "RECEIVED", "version": 0, "mission": "inspect"}

    chained_state = dict(first["nextState"], chainHash=first["chainHash"])
    second_step = transition_preview(
        chained_state,
        {"type": "PLAN", "patch": {"planId": "plan-1"}},
        TRANSITIONS,
        expected_version=1,
        expected_state_hash=first["nextStateHash"],
    )
    assert state_sha256(chained_state) == first["nextStateHash"]
    assert second_step["allowed"] is True
    assert second_step["previousChainHash"] == first["chainHash"]


def test_transition_blocks_conflict_unknown_action_and_protected_patch() -> None:
    state = {"status": "RECEIVED", "version": 2}
    conflict = transition_preview(
        state,
        {"type": "CLASSIFY"},
        TRANSITIONS,
        expected_version=1,
    )
    blocked = transition_preview(
        state,
        {"type": "UNKNOWN"},
        TRANSITIONS,
        expected_version=2,
    )

    assert conflict["status"] == "VERSION_CONFLICT"
    assert blocked["status"] == "TRANSITION_NOT_ALLOWED"
    with pytest.raises(ValueError, match="protected fields"):
        transition_preview(
            state,
            {"type": "CLASSIFY", "patch": {"version": 99}},
            TRANSITIONS,
        )


def test_replay_is_bounded_and_does_not_claim_cross_runtime_parity() -> None:
    initial = {"status": "RECEIVED", "version": 0}
    actions = [
        {"type": "CLASSIFY", "patch": {"intent": "repository_execution"}},
        {"type": "PLAN", "patch": {"planId": "plan-1"}},
    ]
    result = replay_verify(initial, actions, TRANSITIONS)
    repeated = replay_verify(initial, actions, TRANSITIONS)

    assert result == repeated
    assert result["status"] == "REPLAY_VERIFIED"
    assert result["finalState"]["status"] == "PLANNED"
    assert result["finalState"]["version"] == 2
    assert result["crossRuntimeParityProven"] is False
    assert result["mutationPerformed"] is False


def test_python_reference_matches_committed_cross_runtime_vectors() -> None:
    document = load_document()
    results = build_python_results(document)
    expected = document["expected"]

    assert results["decimalVectors"] == expected["decimalVectors"]
    assert results["arithmeticVectors"] == expected["arithmeticVectors"]
    assert results["canonicalVectors"] == expected["canonicalVectors"]
    assert results["rejectionVectors"] == expected["rejectionVectors"]
    assert results["stateVectors"] == expected["stateVectors"]

    transition = results["transitionVectors"][0]["result"]
    expected_transition = expected["transitionVectors"][0]
    assert transition["currentStateHash"] == expected_transition["currentStateHash"]
    assert transition["actionHash"] == expected_transition["actionHash"]
    assert transition["nextStateHash"] == expected_transition["nextStateHash"]
    assert transition["chainHash"] == expected_transition["chainHash"]
    assert transition["nextVersion"]["$integer"] == expected_transition["nextVersion"]

    replay = results["replayVectors"][0]["result"]
    expected_replay = expected["replayVectors"][0]
    assert replay["finalStateHash"] == expected_replay["finalStateHash"]
    assert replay["finalChainHash"] == expected_replay["finalChainHash"]
    steps = [
        {
            "index": step["index"]["$integer"],
            "actionHash": step["actionHash"],
            "stateHash": step["stateHash"],
            "chainHash": step["chainHash"],
        }
        for step in replay["steps"]
    ]
    assert steps == expected_replay["steps"]
