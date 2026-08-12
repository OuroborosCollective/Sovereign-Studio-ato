"""Cross-language configuration provenance parity - end-to-end golden vector.

Issue #1169 acceptance criterion: "gleicher Input erzeugt bytegleichen
Public-Receipt-Hash". The existing parity tests in
``test_configuration_provenance.py`` lock the primitive serializers
(``canonical_json`` / ``hash_value``) against TS reference values. This module
guards the **assembled** contract: it loads a single shared golden fixture
(``fixtures/config_provenance_parity.v1.json``), runs the full
``resolve_config_sources -> materialize_receipt`` pipeline against it, and
asserts that the Python implementation produces the byte-identical
``resolved_hash`` and ``receipt_hash`` frozen in that fixture.

The same fixture is consumed by the TypeScript test
``configProvenanceParity.test.ts``, so any serialization divergence on either
side breaks both gates. The fixture is the single source of truth; both
language tests read the same inputs and the same expected hashes from it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.configuration import (  # noqa: E402
    ConfigSourceContract,
    ResolveOptions,
    bind_config_fingerprint,
    materialize_receipt,
    materialize_and_bind,
    advance_decision,
    resolve_config_sources,
    verify_config_readback,
)
from agent_runtime.configuration.receipt import ConfigReadbackObservation  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "config_provenance_parity.v1.json"

# The golden resolved_hash / receipt_hash are hard regression guards. The
# float-parity fix (#1339) is already on main and this rescue applies the
# Unicode/raw-UTF-8 parity fix from #1344, so no expected failure remains.


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text("utf-8"))


def _build_sources(fixture: dict) -> list[ConfigSourceContract]:
    return [
        ConfigSourceContract(
            id=s["id"],
            kind=s["kind"],
            revision=s["revision"],
            content_hash=s["content_hash"],
            schema_hash=s["schema_hash"],
            priority=s["priority"],
            values=s["values"],
        )
        for s in fixture["sources"]
    ]


def test_resolved_hash_matches_golden_vector() -> None:
    fixture = _load_fixture()
    schema_fields = fixture["options"]["schemaFields"]
    contract = resolve_config_sources(
        _build_sources(fixture),
        ResolveOptions(schema_fields=schema_fields),
    )
    assert contract.status == fixture["expected"]["status"]
    assert contract.resolved_hash == fixture["expected"]["resolved_hash"]


def test_receipt_hash_matches_golden_vector() -> None:
    fixture = _load_fixture()
    schema_fields = fixture["options"]["schemaFields"]
    contract = resolve_config_sources(
        _build_sources(fixture),
        ResolveOptions(schema_fields=schema_fields),
    )
    receipt = materialize_receipt(
        contract,
        {
            "revision": fixture["options"]["revision"],
            "image_digest": fixture["options"]["imageDigest"],
        },
    )
    assert receipt.receipt_hash == fixture["expected"]["receipt_hash"]


def test_resolved_values_match_golden_vector() -> None:
    fixture = _load_fixture()
    schema_fields = fixture["options"]["schemaFields"]
    contract = resolve_config_sources(
        _build_sources(fixture),
        ResolveOptions(schema_fields=schema_fields),
    )
    assert contract.resolved == fixture["expected"]["resolved"]


def test_fixture_self_documents_verified_parity() -> None:
    """Guard against a stale fixture: the embedded parity proof must hold."""
    fixture = _load_fixture()
    proof = fixture["parity_verified"]
    assert proof["identical"] is True
    assert proof["python_resolved_hash"] == proof["typescript_resolved_hash"]
    assert proof["python_receipt_hash"] == proof["typescript_receipt_hash"]
    assert proof["python_resolved_hash"] == fixture["expected"]["resolved_hash"]
    assert proof["python_receipt_hash"] == fixture["expected"]["receipt_hash"]


# --- Live runtime binding readback gate (#1169 acceptance criterion #6) -----
#
# These tests exercise the wiring of ``verify_config_readback`` into the live
# runtime binding path (``bind_config_fingerprint``, ``advance_decision``,
# ``materialize_and_bind``). They mirror the TypeScript matrix in
# ``configProvenanceParity.test.ts`` so that TS/Python diverge on readback
# fail-closed behavior, neither side can silently advance a contradicted
# binding. The shared golden fixture supplies deterministic inputs.


def _resolved_contract():
    fixture = _load_fixture()
    return resolve_config_sources(
        _build_sources(fixture),
        ResolveOptions(schema_fields=fixture["options"]["schemaFields"]),
    )


def _resolved_receipt():
    fixture = _load_fixture()
    contract = resolve_config_sources(
        _build_sources(fixture),
        ResolveOptions(schema_fields=fixture["options"]["schemaFields"]),
    )
    return materialize_receipt(
        contract,
        {
            "revision": fixture["options"]["revision"],
            "image_digest": fixture["options"]["imageDigest"],
        },
    )


def _observation_from(receipt):
    return ConfigReadbackObservation(
        revision=receipt.revision,
        image_digest=receipt.image_digest,
        schema_hash=receipt.schema_hash,
        resolved_hash=receipt.resolved_hash,
        receipt_hash=receipt.receipt_hash,
    )


def _contradicting_observation_from(receipt):
    return ConfigReadbackObservation(
        revision=receipt.revision,
        image_digest=receipt.image_digest,
        schema_hash=receipt.schema_hash,
        resolved_hash="0" * 64,
        receipt_hash=receipt.receipt_hash,
    )


def test_bind_fingerprint_without_readback_is_backward_compatible() -> None:
    receipt = _resolved_receipt()
    binding = bind_config_fingerprint(receipt)
    assert binding.fingerprint_hash
    assert binding.resolved_hash == receipt.resolved_hash


def test_bind_fingerprint_accepts_matching_readback() -> None:
    receipt = _resolved_receipt()
    observation = _observation_from(receipt)
    audit = verify_config_readback(receipt, observation)
    assert audit.accepted is True
    binding = bind_config_fingerprint(receipt, {"readback": observation})
    assert binding.fingerprint_hash


def test_bind_fingerprint_fails_closed_on_contradicting_readback() -> None:
    receipt = _resolved_receipt()
    observation = _contradicting_observation_from(receipt)
    try:
        bind_config_fingerprint(receipt, {"readback": observation})
    except ValueError as exc:
        assert "config readback rejected" in str(exc)
        return
    raise AssertionError("expected ValueError for contradicting readback")


def test_materialize_and_bind_threads_readback_gate_accepted() -> None:
    fixture = _load_fixture()
    contract = _resolved_contract()
    probe = materialize_receipt(
        contract,
        {
            "revision": fixture["options"]["revision"],
            "image_digest": fixture["options"]["imageDigest"],
        },
    )
    observation = _observation_from(probe)
    receipt, binding = materialize_and_bind(
        contract,
        {
            "revision": fixture["options"]["revision"],
            "image_digest": fixture["options"]["imageDigest"],
            "readback": observation,
        },
    )
    assert binding.fingerprint_hash
    assert receipt.receipt_hash == probe.receipt_hash


def test_materialize_and_bind_fails_closed_on_contradicting_readback() -> None:
    fixture = _load_fixture()
    contract = _resolved_contract()
    probe = materialize_receipt(
        contract,
        {
            "revision": fixture["options"]["revision"],
            "image_digest": fixture["options"]["imageDigest"],
        },
    )
    observation = _contradicting_observation_from(probe)
    try:
        materialize_and_bind(
            contract,
            {
                "revision": fixture["options"]["revision"],
                "image_digest": fixture["options"]["imageDigest"],
                "readback": observation,
            },
        )
    except ValueError as exc:
        assert "config readback rejected" in str(exc)
        return
    raise AssertionError("expected ValueError for contradicting readback")


def test_advance_decision_authorizes_when_readback_matches() -> None:
    contract = _resolved_contract()
    receipt = _resolved_receipt()
    observation = _observation_from(receipt)
    decision = advance_decision(contract, receipt, {"readback": observation})
    assert decision.safe is True
    assert decision.reason == "RESOLVED"


def test_advance_decision_fails_closed_on_contradicting_readback() -> None:
    contract = _resolved_contract()
    receipt = _resolved_receipt()
    observation = _contradicting_observation_from(receipt)
    decision = advance_decision(contract, receipt, {"readback": observation})
    assert decision.safe is False
    assert decision.reason == "config_readback_contradicts_receipt"


def test_advance_decision_fails_closed_when_readback_without_receipt() -> None:
    contract = _resolved_contract()
    observation = ConfigReadbackObservation(
        revision="sha-receipt-revision-33333333333333333333333333333333",
        image_digest="sha256:image-digest-4444444444444444444444444444444444",
        schema_hash="sch-a5c28a8409179d35",
        resolved_hash=contract.resolved_hash,
        receipt_hash="irrelevant",
    )
    decision = advance_decision(contract, None, {"readback": observation})
    assert decision.safe is False
    assert decision.reason == "READBACK_NO_RECEIPT"
