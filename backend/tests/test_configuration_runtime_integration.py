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
    binding_liveness,
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


def _binding():
    receipt = _receipt()
    return bind_config_fingerprint(receipt)


def test_binding_liveness_valid_for_unchanged_resolved_contract():
    binding = _binding()
    live = _resolved_contract()
    verdict = binding_liveness(binding, live)
    assert verdict.valid is True
    assert verdict.reason == "RESOLVED"
    assert verdict.status == "RESOLVED"
    assert verdict.drift_kind is None


def test_binding_liveness_invalidated_by_content_drift():
    binding = _binding()
    contract = _resolved_contract()
    drifted = resolve_config_sources(
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
    assert drifted.status == "CONTRADICTED"
    verdict = binding_liveness(binding, drifted)
    assert verdict.valid is False
    assert verdict.reason.startswith("BINDING_CONTRADICTED:content-drift")
    assert verdict.drift_kind == "content-drift"


def test_binding_liveness_invalidated_by_schema_drift():
    binding = _binding()
    blocked = resolve_config_sources(
        [
            ConfigSourceContract(
                id="a",
                kind="compiled-defaults",
                revision="a" * 40,
                content_hash=hash_value({"source": "a"}),
                schema_hash="sch-1",
                priority=default_priority_for("compiled-defaults"),
                values={"a": 1},
                remote=None,
            ),
            ConfigSourceContract(
                id="b",
                kind="deployment-config",
                revision="a" * 40,
                content_hash=hash_value({"source": "b"}),
                schema_hash="sch-2",
                priority=default_priority_for("deployment-config"),
                values={"b": 2},
                remote=None,
            ),
        ]
    )
    assert blocked.status == "BLOCKED"
    verdict = binding_liveness(binding, blocked)
    assert verdict.valid is False
    assert verdict.reason.startswith("BINDING_BLOCKED:schema-drift")


def test_binding_liveness_invalidated_by_resolved_hash_mismatch():
    binding = _binding()
    other = resolve_config_sources(
        [
            ConfigSourceContract(
                id="defaults",
                kind="compiled-defaults",
                revision="a" * 40,
                content_hash=hash_value({"source": "defaults"}),
                schema_hash=hash_value({"schema": "v1"}),
                priority=default_priority_for("compiled-defaults"),
                values={"feature": {"enabled": False, "extra": True}},
                remote=None,
            )
        ]
    )
    assert other.status == "RESOLVED"
    assert other.resolved_hash != binding.resolved_hash
    verdict = binding_liveness(binding, other)
    assert verdict.valid is False
    assert verdict.reason == "BINDING_RESOLVED_HASH_MISMATCH"


def test_binding_liveness_invalidated_by_stale_schema_hash():
    binding = _binding()
    live = _resolved_contract()
    assert live.status == "RESOLVED"
    stale = dataclasses.replace(binding, schema_hash="stale-schema-hash")
    verdict = binding_liveness(stale, live)
    assert verdict.valid is False
    assert verdict.reason == "BINDING_SCHEMA_HASH_MISMATCH"
