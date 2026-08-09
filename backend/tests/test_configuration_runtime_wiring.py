"""Configuration Provenance - runtime wiring integration tests (#1169).

These tests verify the provenance layer is wired into the runtime truth chain:

1. PatchMon config readback gate: a container is configured only when
   PatchMon's independent observation matches the resolved receipt exactly.
   Mismatch -> CONTRADICTED; missing/unbound -> BLOCKED; never green.
2. RunEnvelope config binding (#1116): a redacted config fingerprint is bound
   deterministically to a run envelope hash.
3. Drift-based invalidation: a verified ``config_drift`` evidence record forces
   an active integration-plan phase to ``INVALIDATED`` rather than silently
   continuing on a stale config projection.

Cross-language parity with ``src/runtime/config/configProvenance.test.ts`` is
covered by the existing mirror / parity tests; these tests exercise the real
live-path Python implementations and the integration plan lane.
"""

from __future__ import annotations

import hashlib
import os
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.configuration import (  # noqa: E402
    ConfigSourceContract,
    RemoteBinding,
    ResolveOptions,
    compare_patchmon_readback,
    materialize_receipt,
    resolve_config_sources,
    bind_config_to_run,
    PatchMonReadback,
    READBACK_VERIFIED,
    READBACK_CONTRADICTED,
    READBACK_BLOCKED,
)
from agent_runtime.configuration.config_sources import default_priority_for  # noqa: E402


def _src(
    id: str,
    kind: str,
    values: dict[str, Any],
    *,
    revision: str = "rev-1",
    content_hash: str | None = None,
    schema_hash: str = "sch-default",
    priority: int | None = None,
    remote: RemoteBinding | None = None,
) -> ConfigSourceContract:
    if priority is None:
        try:
            priority = default_priority_for(kind)  # type: ignore[arg-type]
        except KeyError:
            priority = 999
    return ConfigSourceContract(
        id=id,
        kind=kind,  # type: ignore[arg-type]
        revision=revision,
        content_hash=content_hash or f"ch-{id}",
        schema_hash=schema_hash,
        priority=priority,
        values=values,
        remote=remote,
    )


BASE_SOURCES = [
    _src("defaults", "compiled-defaults", {"a": 1, "b": {"x": 1}, "arr": [1, 2]}),
    _src("deploy", "deployment-config", {"b": {"y": 2}, "c": 3}),
]


def _resolved_receipt(revision: str = "rev-1", image_digest: str = "sha256:img-1"):
    contract = resolve_config_sources(BASE_SOURCES)
    assert contract.status == "RESOLVED", contract.errors
    return materialize_receipt(
        contract, {"revision": revision, "image_digest": image_digest}
    )  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# PatchMon config readback gate (#1169)
# ---------------------------------------------------------------------------


def test_patchmon_readback_verified_on_exact_match():
    receipt = _resolved_receipt()
    observed = PatchMonReadback(
        revision=receipt.revision,
        image_digest=receipt.image_digest,
        schema_hash=receipt.schema_hash,
        config_hash=receipt.resolved_hash,
    )
    result = compare_patchmon_readback(receipt, observed)
    assert result.verdict == READBACK_VERIFIED
    assert result.mismatched_fields == ()
    assert result.missing_fields == ()


def test_patchmon_readback_contradicted_on_image_digest_drift():
    receipt = _resolved_receipt()
    observed = PatchMonReadback(
        revision=receipt.revision,
        image_digest="sha256:" + "b" * 64,
        schema_hash=receipt.schema_hash,
        config_hash=receipt.resolved_hash,
    )
    result = compare_patchmon_readback(receipt, observed)
    assert result.verdict == READBACK_CONTRADICTED
    assert "imageDigest" in result.mismatched_fields


def test_patchmon_readback_contradicted_on_config_hash_drift():
    receipt = _resolved_receipt()
    observed = PatchMonReadback(
        revision=receipt.revision,
        image_digest=receipt.image_digest,
        schema_hash=receipt.schema_hash,
        config_hash=hashlib.sha256(b"different-config").hexdigest(),
    )
    result = compare_patchmon_readback(receipt, observed)
    assert result.verdict == READBACK_CONTRADICTED
    assert "resolvedHash (config)" in result.mismatched_fields


def test_patchmon_readback_blocked_on_missing_fields():
    receipt = _resolved_receipt()
    observed = PatchMonReadback(
        revision=None, image_digest=None, schema_hash=None, config_hash=None
    )
    result = compare_patchmon_readback(receipt, observed)
    assert result.verdict == READBACK_BLOCKED
    assert len(result.missing_fields) == 4


def test_patchmon_readback_blocked_when_receipt_not_resolved():
    # Unknown source kind -> resolver fails closed to BLOCKED (not RESOLVED).
    contract = resolve_config_sources([_src("bad", "unknown-kind", {"a": 1})])
    assert contract.status != "RESOLVED"
    receipt = materialize_receipt(contract, {"revision": "rev-1"})  # type: ignore[arg-type]
    observed = PatchMonReadback(
        revision="rev-1",
        image_digest="sha256:img-1",
        schema_hash=receipt.schema_hash,
        config_hash=receipt.resolved_hash,
    )
    result = compare_patchmon_readback(receipt, observed)
    # A non-RESOLVED receipt must never be promoted to VERIFIED by readback.
    assert result.verdict == READBACK_BLOCKED


# ---------------------------------------------------------------------------
# RunEnvelope config binding (#1116 / #1169)
# ---------------------------------------------------------------------------


def test_bind_config_to_run_is_deterministic():
    receipt = _resolved_receipt()
    b1 = bind_config_to_run("envelope-A", receipt)
    b2 = bind_config_to_run("envelope-A", receipt)
    assert b1.binding_hash == b2.binding_hash
    assert len(b1.binding_hash) == 64
    assert b1.config_fingerprint == receipt.resolved_hash
    assert b1.config_receipt_hash == receipt.receipt_hash


def test_bind_config_to_run_differs_per_envelope():
    receipt = _resolved_receipt()
    b1 = bind_config_to_run("envelope-A", receipt)
    b2 = bind_config_to_run("envelope-B", receipt)
    assert b1.binding_hash != b2.binding_hash


def test_bind_config_to_run_differs_per_config_receipt():
    contract = resolve_config_sources(BASE_SOURCES)
    r1 = materialize_receipt(contract, {"revision": "rev-1"})  # type: ignore[arg-type]
    r2 = materialize_receipt(contract, {"revision": "rev-2"})  # type: ignore[arg-type]
    b1 = bind_config_to_run("envelope-A", r1)
    b2 = bind_config_to_run("envelope-A", r2)
    assert b1.binding_hash != b2.binding_hash


def test_bind_config_to_run_rejects_empty_envelope():
    receipt = _resolved_receipt()
    with pytest.raises(ValueError):
        bind_config_to_run("", receipt)


def test_bind_config_to_run_carries_only_redacted_material():
    receipt = _resolved_receipt()
    binding = bind_config_to_run("envelope-A", receipt)
    # The binding carries only hashes/redacted identity, never raw resolved
    # config or secret material.
    assert binding.config_fingerprint == receipt.resolved_hash
    assert binding.schema_hash == receipt.schema_hash
    assert not any(
        isinstance(getattr(binding, f), dict)
        for f in binding.__dataclass_fields__
    )


# ---------------------------------------------------------------------------
# Drift-based invalidation of active action plans (integration plan lane #1169)
# ---------------------------------------------------------------------------


def _config_drift_evidence(phase_id: str, prior_hash: str):
    """Build a verified config_drift EvidenceRecord over the real live path."""
    from agent_runtime.integration_plan_lane import IntegrationPlanLane

    return IntegrationPlanLane.create_evidence_record(
        evidence_id=f"{phase_id}:config-drift",
        phase_id=phase_id,
        kind="config_drift",
        source=prior_hash,
        content_sha256=hashlib.sha256(prior_hash.encode()).hexdigest(),
        received_at_iso="1970-01-01T00:00:00Z",
        is_verified=True,
    )


def _make_phase(phase_id: str = "deploy", status=None):
    from agent_runtime.integration_plan_lane import Phase, PhaseStatus

    return Phase(
        phase_id=phase_id,
        title="Deploy",
        description="Deploy the build",
        acceptance_criteria=("container healthy",),
        required_evidence_kinds=(),
        status=status or PhaseStatus.IN_PROGRESS,
    )


def test_config_drift_evidence_kind_is_accepted():
    """The config_drift evidence kind must be a known, bindable kind."""
    from agent_runtime.integration_plan_lane import _KNOWN_EVIDENCE_KINDS

    assert "config_drift" in _KNOWN_EVIDENCE_KINDS


def test_config_drift_record_invalidates_phase():
    """A verified config_drift record forces a phase to INVALIDATED."""
    from agent_runtime.integration_plan_lane import (
        IntegrationPlanLane,
        PhaseStatus,
    )

    phase = _make_phase("deploy")
    drift = _config_drift_evidence("deploy", "a" * 64)
    status = IntegrationPlanLane.evaluate_phase(phase, [drift])
    assert status == PhaseStatus.INVALIDATED


def test_config_drift_does_not_invalidate_when_unverified():
    """An unverified config_drift record must NOT invalidate a phase."""
    from agent_runtime.integration_plan_lane import (
        IntegrationPlanLane,
        PhaseStatus,
    )

    phase = _make_phase("deploy")
    prior_hash = "a" * 64
    unverified = IntegrationPlanLane.create_evidence_record(
        evidence_id="deploy:config-drift",
        phase_id="deploy",
        kind="config_drift",
        source=prior_hash,
        content_sha256=hashlib.sha256(prior_hash.encode()).hexdigest(),
        received_at_iso="1970-01-01T00:00:00Z",
        is_verified=False,
    )
    status = IntegrationPlanLane.evaluate_phase(phase, [unverified])
    # No required kinds and no verified drift -> stays in its current state.
    assert status != PhaseStatus.INVALIDATED


def test_config_drift_invalidates_even_when_required_evidence_present():
    """Drift supersedes verification: a verified phase with required evidence
    still goes INVALIDATED when a verified config_drift record appears."""
    from agent_runtime.integration_plan_lane import (
        IntegrationPlanLane,
        Phase,
        PhaseStatus,
    )

    phase = Phase(
        phase_id="deploy",
        title="Deploy",
        description="Deploy",
        acceptance_criteria=("container healthy",),
        required_evidence_kinds=("patchmon_readback",),
        status=PhaseStatus.VERIFIED,
    )
    drift = _config_drift_evidence("deploy", "b" * 64)
    readback = IntegrationPlanLane.create_evidence_record(
        evidence_id="deploy:readback",
        phase_id="deploy",
        kind="patchmon_readback",
        source="patchmon.sovereign.local",
        content_sha256="c" * 64,
        received_at_iso="1970-01-01T00:00:00Z",
        is_verified=True,
    )
    status = IntegrationPlanLane.evaluate_phase(phase, [drift, readback])
    assert status == PhaseStatus.INVALIDATED


# ---------------------------------------------------------------------------
# RunEnvelope config binding (#1116): the envelope carries a redacted config
# fingerprint and exposes a config-bound run identity. This is the envelope
# side of the PatchMon readback contract.
# ---------------------------------------------------------------------------


def _make_receipt():
    contract = resolve_config_sources(
        [_src("defaults", "compiled-defaults", {"model": "a", "feature": True})]
    )
    assert contract.status == "RESOLVED", contract.errors
    return materialize_receipt(contract, {"revision": "rev-1", "image_digest": "sha256:img-1"})  # type: ignore[arg-type]


def test_run_envelope_carries_config_fingerprint():
    from agent_runtime.provider_neutral_runtime import RuntimeInputEnvelope, RuntimeInputPart

    receipt = _make_receipt()
    envelope = RuntimeInputEnvelope(
        parts=(RuntimeInputPart(kind="text", text="hi"),),
    )
    assert envelope.config_fingerprint is None
    assert envelope.bound_sha256 == envelope.sha256

    bound = bind_config_to_run(envelope.sha256, receipt)
    env_bound = RuntimeInputEnvelope.with_config_binding(
        envelope.parts, config_binding=bound
    )
    assert env_bound.config_fingerprint == bound.config_fingerprint
    body = env_bound.to_dict()
    cb = body["configBinding"]
    assert cb["configFingerprint"] == bound.config_fingerprint
    assert cb["bindingHash"] == bound.binding_hash
    assert cb["schemaHash"] == bound.schema_hash
    # config binding changes the bound run identity but not the base sha256
    assert env_bound.sha256 == envelope.sha256
    assert env_bound.bound_sha256 != envelope.sha256


def test_run_envelope_config_change_changes_bound_identity():
    from agent_runtime.provider_neutral_runtime import RuntimeInputEnvelope, RuntimeInputPart

    c1 = _src("defaults", "compiled-defaults", {"model": "a"})
    c2 = _src("defaults", "compiled-defaults", {"model": "b"})
    r1 = materialize_receipt(resolve_config_sources([c1]), {"revision": "rev-1", "image_digest": "sha256:img-1"})  # type: ignore[arg-type]
    r2 = materialize_receipt(resolve_config_sources([c2]), {"revision": "rev-1", "image_digest": "sha256:img-1"})  # type: ignore[arg-type]
    assert r1.resolved_hash != r2.resolved_hash

    parts = (RuntimeInputPart(kind="text", text="hi"),)
    e1 = RuntimeInputEnvelope.with_config_binding(
        parts, config_binding=bind_config_to_run(
            RuntimeInputEnvelope(parts=parts).sha256, r1
        )
    )
    e2 = RuntimeInputEnvelope.with_config_binding(
        parts, config_binding=bind_config_to_run(
            RuntimeInputEnvelope(parts=parts).sha256, r2
        )
    )
    # same parts, different config -> different bound identity
    assert e1.sha256 == e2.sha256
    assert e1.bound_sha256 != e2.bound_sha256
    assert e1.config_fingerprint != e2.config_fingerprint


def test_run_envelope_rejects_invalid_binding_hash():
    from agent_runtime.provider_neutral_runtime import RuntimeInputEnvelope, RuntimeInputPart

    receipt = _make_receipt()
    bound = bind_config_to_run("0" * 64, receipt)
    bad = bound.__class__(
        run_envelope_hash=bound.run_envelope_hash,
        config_receipt_hash=bound.config_receipt_hash,
        config_fingerprint=bound.config_fingerprint,
        schema_hash=bound.schema_hash,
        revision=bound.revision,
        image_digest=bound.image_digest,
        binding_hash="not-a-hash",
    )
    with pytest.raises(Exception):
        RuntimeInputEnvelope(
            parts=(RuntimeInputPart(kind="text", text="hi"),),
            config_binding=bad,
        )


def test_envelope_config_fingerprint_matches_patchmon_readback():
    """DoD: RunEnvelope and PatchMon read back the same redacted fingerprint."""
    from agent_runtime.provider_neutral_runtime import RuntimeInputEnvelope, RuntimeInputPart

    receipt = _make_receipt()
    envelope = RuntimeInputEnvelope.with_config_binding(
        (RuntimeInputPart(kind="text", text="hi"),),
        config_binding=bind_config_to_run(
            RuntimeInputEnvelope(parts=(RuntimeInputPart(kind="text", text="hi"),)).sha256,
            receipt,
        ),
    )
    readback = PatchMonReadback(
        revision=receipt.revision,
        image_digest=receipt.image_digest,
        schema_hash=receipt.schema_hash,
        config_hash=receipt.resolved_hash,
    )
    result = compare_patchmon_readback(receipt, readback)
    assert result.verdict == READBACK_VERIFIED
    assert receipt.resolved_hash == envelope.config_fingerprint


# ---------------------------------------------------------------------------
# Mirror parity (canonical backend == deployment mirror)
# ---------------------------------------------------------------------------


def test_configuration_receipt_mirror_parity():
    """Canonical and mirror receipt modules must be byte-identical (#1169)."""
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    canonical = os.path.join(repo_root, "agent_runtime", "configuration", "receipt.py")
    mirror = os.path.join(
        repo_root,
        "..",
        "scripts",
        "sovereign-backend",
        "agent_runtime",
        "configuration",
        "receipt.py",
    )
    canonical = os.path.normpath(canonical)
    mirror = os.path.normpath(mirror)
    if not os.path.exists(mirror):
        pytest.skip("deployment mirror not present in this checkout")
    with open(canonical, "rb") as f:
        a = f.read()
    with open(mirror, "rb") as f:
        b = f.read()
    assert a == b, "canonical and mirror receipt.py diverged"
