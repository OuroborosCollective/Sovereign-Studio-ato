"""Configuration Provenance - runtime binding & advance-gate integration tests.

Covers the integration seam between the read-only provenance layer and the
runtime's advancement / RunEnvelope contracts:

* ``bind_config_fingerprint`` - redacted fingerprint bound into RunEnvelope
  (#1116) and read back by PatchMon; byte-identical for same input; fail-closed
  on a tampered/unverifiable receipt.
* ``advance_decision`` - fail-closed drift gate for new mutations and active
  action plans; ``RESOLVED`` advances, ``CONTRADICTED`` / ``BLOCKED`` /
  ``DEGRADED`` / drift / errors / receipt-mismatch block with explicit reason.

Mutation of configuration runs through #1119; these tests exercise the
read-only resolver + binding + gate against the real live-path implementation.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from typing import Any

import pytest

# Make agent_runtime importable whether pytest runs from the repo root
# (sovereign-agent-backend.yml PR gate) or from backend/ (ci.yml push gate).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.configuration import (  # noqa: E402
    ConfigSourceContract,
    RemoteBinding,
    ResolveOptions,
    advance_decision,
    bind_config_fingerprint,
    default_priority_for,
    is_safe_to_advance,
    materialize_and_bind,
    materialize_receipt,
    resolve_config_sources,
    verify_receipt,
)


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


# ---------------------------------------------------------------------------
# bind_config_fingerprint - RunEnvelope / PatchMon redacted fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_is_byte_identical_for_same_input():
    res = resolve_config_sources(BASE_SOURCES)
    receipt, binding_a = materialize_and_bind(res, {"revision": "rev-1", "image_digest": "img-1"})
    binding_b = bind_config_fingerprint(receipt)
    assert binding_a.fingerprint_hash == binding_b.fingerprint_hash
    assert binding_a.fingerprint_hash != ""


def test_fingerprint_changes_when_bound_revision_or_digest_change():
    res = resolve_config_sources(BASE_SOURCES)
    _, binding_a = materialize_and_bind(res, {"revision": "rev-1", "image_digest": "img-1"})
    _, binding_b = materialize_and_bind(res, {"revision": "rev-2", "image_digest": "img-1"})
    _, binding_c = materialize_and_bind(res, {"revision": "rev-1", "image_digest": "img-2"})
    assert binding_a.fingerprint_hash != binding_b.fingerprint_hash
    assert binding_a.fingerprint_hash != binding_c.fingerprint_hash


def test_fingerprint_exposes_patchmon_readback_fields():
    res = resolve_config_sources(BASE_SOURCES)
    receipt, binding = materialize_and_bind(
        res, {"revision": "rev-1", "image_digest": "sha256:img-1"}
    )
    assert binding.version != ""
    assert binding.status == "RESOLVED"
    assert binding.verified is True
    assert binding.receipt_hash == receipt.receipt_hash
    assert binding.schema_hash == res.schema_hash
    assert binding.resolved_hash == res.resolved_hash
    assert binding.revision == "rev-1"
    assert binding.image_digest == "sha256:img-1"
    assert binding.drift_kind is None


def test_fingerprint_never_carries_raw_secret_material():
    secret = "super-secret-value-do-not-leak"
    redacted_id = (
        "a" * 64
    )  # synthetic redacted id that is not derived from the secret
    sources = [
        _src(
            "env",
            "environment-projection",
            {"apiKey": {"kind": "secret", "redactedId": redacted_id}, "public": "visible"},
        )
    ]
    res = resolve_config_sources(sources)
    assert res.status == "RESOLVED"
    _, binding = materialize_and_bind(res, {"revision": "rev-1"})
    serialized = repr(dataclasses.asdict(binding))
    assert secret not in serialized
    assert redacted_id not in serialized


def test_tampered_receipt_fails_closed_in_fingerprint():
    res = resolve_config_sources(BASE_SOURCES)
    receipt, _ = materialize_and_bind(res, {"revision": "rev-1"})
    tampered = dataclasses.replace(receipt, revision="rev-tampered")
    binding = bind_config_fingerprint(tampered)
    # Fail-closed: tampering is detectable (verified=False), fingerprint still
    # reflects the (tampered) body so the mismatch is auditable, and the gate
    # below blocks advancement.
    assert binding.verified is False


# ---------------------------------------------------------------------------
# advance_decision - fail-closed drift gate
# ---------------------------------------------------------------------------


def test_advance_decision_resolved_contract_is_safe():
    res = resolve_config_sources(BASE_SOURCES)
    decision = advance_decision(res)
    assert decision.safe is True
    assert decision.reason == "RESOLVED"


def test_advance_decision_contradicted_blocks_with_drift_kind():
    res = resolve_config_sources(BASE_SOURCES, ResolveOptions(expected_receipt_hash="deadbeef"))  # type: ignore[call-arg]
    assert res.status == "CONTRADICTED"
    decision = advance_decision(res)
    assert decision.safe is False
    assert decision.reason.startswith("CONFIG_CONTRADICTED:")
    assert decision.drift_kind == "content-drift"


def test_advance_decision_blocked_schema_drift_blocks():
    res = resolve_config_sources(
        [
            _src("a", "compiled-defaults", {"a": 1}, schema_hash="sch-1"),
            _src("b", "deployment-config", {"b": 2}, schema_hash="sch-2"),
        ]
    )
    assert res.status == "BLOCKED"
    decision = advance_decision(res)
    assert decision.safe is False
    assert decision.reason.startswith("CONFIG_BLOCKED:")
    assert decision.drift_kind == "schema-drift"


def test_advance_decision_unverifiable_receipt_blocks():
    res = resolve_config_sources(BASE_SOURCES)
    receipt = materialize_receipt(res, {"revision": "rev-1"})
    tampered = dataclasses.replace(receipt, revision="rev-tampered")
    decision = advance_decision(res, tampered)
    assert decision.safe is False
    assert decision.reason == "RECEIPT_UNVERIFIED"


def test_advance_decision_stale_receipt_mismatch_blocks():
    baseline = resolve_config_sources(BASE_SOURCES)
    receipt = materialize_receipt(baseline, {"revision": "rev-1"})

    # A second resolution with a different value produces a different
    # resolved_hash; binding the old receipt to the new contract is a stale
    # binding and must not authorize advancement.
    other = resolve_config_sources(
        [_src("defaults", "compiled-defaults", {"a": 999})]
    )
    assert other.resolved_hash != baseline.resolved_hash
    assert other.status == "RESOLVED"
    decision = advance_decision(other, receipt)
    assert decision.safe is False
    assert decision.reason == "RECEIPT_MISMATCH"


def test_advance_decision_with_matching_receipt_is_safe():
    res = resolve_config_sources(BASE_SOURCES)
    receipt = materialize_receipt(res, {"revision": "rev-1"})
    assert verify_receipt(receipt)
    decision = advance_decision(res, receipt)
    assert decision.safe is True
    assert decision.reason == "RESOLVED"


def test_advance_decision_consistent_with_is_safe_to_advance():
    """The gate must agree with the boolean primitive on the status axis."""
    res = resolve_config_sources(BASE_SOURCES)
    assert advance_decision(res).safe is is_safe_to_advance(res)

    blocked = resolve_config_sources(
        [
            _src("a", "compiled-defaults", {"a": 1}, schema_hash="sch-1"),
            _src("b", "deployment-config", {"b": 2}, schema_hash="sch-2"),
        ]
    )
    assert advance_decision(blocked).safe is is_safe_to_advance(blocked)


def test_advance_decision_receipt_status_not_resolved_blocks():
    # A receipt legitimately materialized from a BLOCKED contract verifies on
    # its own, but its status is not RESOLVED - binding it to a RESOLVED
    # contract must not authorize advancement.
    blocked = resolve_config_sources(
        [
            _src("a", "compiled-defaults", {"a": 1}, schema_hash="sch-1"),
            _src("b", "deployment-config", {"b": 2}, schema_hash="sch-2"),
        ]
    )
    assert blocked.status == "BLOCKED"
    blocked_receipt = materialize_receipt(blocked, {"revision": "rev-1"})
    assert verify_receipt(blocked_receipt)

    resolved = resolve_config_sources(BASE_SOURCES)
    assert resolved.status == "RESOLVED"
    decision = advance_decision(resolved, blocked_receipt)
    assert decision.safe is False
    assert decision.reason == "RECEIPT_STATUS:BLOCKED"
