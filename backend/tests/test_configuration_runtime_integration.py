"""Issue #1169 consolidated runtime/PatchMon provenance regression tests."""

from __future__ import annotations

import dataclasses
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.configuration import (  # noqa: E402
    ConfigReadbackObservation,
    ConfigSourceContract,
    ResolveOptions,
    advance_decision,
    bind_config_fingerprint,
    default_priority_for,
    materialize_receipt,
    resolve_config_sources,
    verify_config_readback,
)
from agent_runtime.configuration.config_canonicalize import hash_value  # noqa: E402
from agent_runtime.provider_neutral_runtime import (  # noqa: E402
    ProviderNeutralRuntimeKernel,
    RuntimeContext,
    RuntimeInputEnvelope,
    RuntimeInputPart,
)


def _resolved_contract():
    schema_hash = hash_value({"schema": "v1"})
    source = ConfigSourceContract(
        id="defaults",
        kind="compiled-defaults",
        revision="a" * 40,
        content_hash=hash_value({"source": "defaults"}),
        schema_hash=schema_hash,
        priority=default_priority_for("compiled-defaults"),
        values={"feature": {"enabled": True}},
        remote=None,
    )
    return resolve_config_sources([source])


def _receipt():
    contract = _resolved_contract()
    return materialize_receipt(
        contract,
        {"revision": "b" * 40, "image_digest": "sha256:" + "c" * 64},
    )


def test_patchmon_readback_requires_integrity_resolved_state_and_receipt_hash():
    receipt = _receipt()
    observation = ConfigReadbackObservation(
        revision=receipt.revision,
        image_digest=receipt.image_digest,
        schema_hash=receipt.schema_hash,
        resolved_hash=receipt.resolved_hash,
        receipt_hash=receipt.receipt_hash,
    )
    audit = verify_config_readback(receipt, observation)
    assert audit.accepted is True
    assert audit.blocker is None

    missing_hash = dataclasses.replace(observation, receipt_hash=None)
    assert verify_config_readback(receipt, missing_hash).blocker == "config_readback_missing_bound_field"

    wrong_hash = dataclasses.replace(observation, receipt_hash="0" * 64)
    wrong = verify_config_readback(receipt, wrong_hash)
    assert wrong.accepted is False
    assert wrong.contradicted is True

    tampered = dataclasses.replace(receipt, revision="d" * 40)
    assert verify_config_readback(tampered, observation).blocker == "config_receipt_self_verification_failed"


def test_runtime_binding_rejects_tampered_and_non_resolved_receipts():
    receipt = _receipt()
    binding = bind_config_fingerprint(receipt)
    assert binding.verified is True
    assert binding.status == "RESOLVED"

    with pytest.raises(ValueError, match="integrity verification"):
        bind_config_fingerprint(dataclasses.replace(receipt, revision="d" * 40))

    contract = _resolved_contract()
    contradicted = resolve_config_sources(
        [
            ConfigSourceContract(
                id="defaults",
                kind="compiled-defaults",
                revision="a" * 40,
                content_hash=hash_value({"source": "defaults"}),
                schema_hash=contract.schema_hash,
                priority=default_priority_for("compiled-defaults"),
                values={"feature": {"enabled": True}},
                remote=None,
            )
        ],
        ResolveOptions(expected_receipt_hash="0" * 64),
    )
    contradicted_receipt = materialize_receipt(contradicted, {"revision": "b" * 40})
    assert advance_decision(contradicted, contradicted_receipt).safe is False
    with pytest.raises(ValueError, match="not RESOLVED"):
        bind_config_fingerprint(contradicted_receipt)


def test_run_preparation_identity_is_bound_to_verified_config_fingerprint():
    receipt = _receipt()
    binding = bind_config_fingerprint(receipt)
    part = RuntimeInputPart(kind="text", text="hello")
    plain = RuntimeInputEnvelope(parts=(part,))
    bound = RuntimeInputEnvelope.with_config_binding(parts=(part,), config_binding=binding)

    assert bound.sha256 == plain.sha256
    assert bound.bound_sha256 != plain.sha256
    assert bound.config_fingerprint == binding.fingerprint_hash

    context = RuntimeContext(
        run_id="run-config-1",
        owner_id="owner-1",
        revision="e" * 40,
        tick=1,
        epoch_ms=1,
    )
    prepared = ProviderNeutralRuntimeKernel().prepare_run(
        context=context,
        envelope=bound,
        tools=(),
    )
    assert prepared.status == "ready"
    assert prepared.input_sha256 == bound.bound_sha256
    assert prepared.events[0].payload["inputSha256"] == bound.bound_sha256
    assert prepared.events[0].payload["configFingerprintHash"] == binding.fingerprint_hash


def _matching_observation(binding):
    return ConfigReadbackObservation(
        revision=binding.revision,
        image_digest=binding.image_digest,
        schema_hash=binding.schema_hash,
        resolved_hash=binding.resolved_hash,
        receipt_hash=binding.receipt_hash,
    )


def test_runenvelope_readback_accepts_matching_patchmon_observation():
    """#1169 DoD: RunEnvelope and PatchMon read back the same redacted fingerprint."""
    binding = bind_config_fingerprint(_receipt())
    envelope = RuntimeInputEnvelope.with_config_binding(
        parts=(RuntimeInputPart(kind="text", text="hello"),),
        config_binding=binding,
    )
    audit = envelope.compare_patchmon_readback(_matching_observation(binding))
    assert audit.accepted is True
    assert audit.blocker is None


def test_runenvelope_readback_blocks_when_receipt_hash_missing():
    binding = bind_config_fingerprint(_receipt())
    envelope = RuntimeInputEnvelope.with_config_binding(
        parts=(RuntimeInputPart(kind="text", text="hello"),),
        config_binding=binding,
    )
    missing = dataclasses.replace(_matching_observation(binding), receipt_hash=None)
    audit = envelope.compare_patchmon_readback(missing)
    assert audit.accepted is False
    assert audit.blocker == "config_readback_missing_bound_field"


def test_runenvelope_readback_contradicts_wrong_receipt_hash():
    binding = bind_config_fingerprint(_receipt())
    envelope = RuntimeInputEnvelope.with_config_binding(
        parts=(RuntimeInputPart(kind="text", text="hello"),),
        config_binding=binding,
    )
    wrong = dataclasses.replace(_matching_observation(binding), receipt_hash="0" * 64)
    audit = envelope.compare_patchmon_readback(wrong)
    assert audit.accepted is False
    assert audit.blocker == "config_readback_contradicts_receipt"
    assert audit.contradicted is True


def test_runenvelope_readback_contradicts_wrong_resolved_hash():
    binding = bind_config_fingerprint(_receipt())
    envelope = RuntimeInputEnvelope.with_config_binding(
        parts=(RuntimeInputPart(kind="text", text="hello"),),
        config_binding=binding,
    )
    wrong = dataclasses.replace(_matching_observation(binding), resolved_hash="0" * 64)
    audit = envelope.compare_patchmon_readback(wrong)
    assert audit.accepted is False
    assert audit.blocker == "config_readback_contradicts_receipt"
    assert audit.contradicted is True


def test_runenvelope_readback_blocks_when_no_binding_bound():
    """No bound truth -> readback is incomplete, never silently accepted."""
    plain = RuntimeInputEnvelope(parts=(RuntimeInputPart(kind="text", text="hello"),))
    audit = plain.compare_patchmon_readback(
        ConfigReadbackObservation(
            revision=None,
            image_digest=None,
            schema_hash=None,
            resolved_hash=None,
            receipt_hash=None,
        )
    )
    assert audit.accepted is False
    assert audit.blocker == "config_readback_missing_bound_field"


def test_runenvelope_readback_matches_receipt_side_reason_codes():
    """The envelope-side audit reuses the receipt-side reason codes (#1169 parity)."""
    binding = bind_config_fingerprint(_receipt())
    envelope = RuntimeInputEnvelope.with_config_binding(
        parts=(RuntimeInputPart(kind="text", text="hello"),),
        config_binding=binding,
    )
    wrong = dataclasses.replace(_matching_observation(binding), receipt_hash="0" * 64)
    envelope_audit = envelope.compare_patchmon_readback(wrong)
    receipt_audit = verify_config_readback(_receipt(), wrong)
    assert envelope_audit.blocker == receipt_audit.blocker
    assert envelope_audit.accepted == receipt_audit.accepted
    assert envelope_audit.contradicted == receipt_audit.contradicted

