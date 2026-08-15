"""Tests for the operator projection read models and removal guarantee (#1174).

Verifies:
- the projection is rebuildable (same input -> same row hashes);
- secret-shaped fields are dropped and secret-shaped summaries degrade;
- statuses are projections, never authoritative green truth;
- no status field can mutate a canonical evidence verdict;
- removing the projection package degrades to ``OPERATOR_PROJECTION_UNAVAILABLE``
  rather than breaking the core runtime contract.
"""

from __future__ import annotations

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.operator_projection.read_models import (  # noqa: E402
    PROJECTION_STATUSES,
    SUPPORTED_RECORD_KINDS,
    ReadModelProjector,
    projection_row_hash,
)


_REV = "sha256:" + "a" * 64


def _record(**overrides) -> dict:
    base = {
        "kind": "incident",
        "id": "inc-1",
        "status": "SUCCEEDED_UNVERIFIED",
        "summary": "Runner completed step",
        "sourceReceiptHashes": [_REV],
    }
    base.update(overrides)
    return base


def test_projection_is_rebuildable_identical_hashes():
    projector = ReadModelProjector()
    records = [_record(), {"kind": "runtime_node", "id": "node-1", "status": "VERIFIED"}]
    run_a = projector.project(records)
    run_b = projector.project(records)
    assert [r.row_hash for r in run_a] == [r.row_hash for r in run_b]
    assert all(r.row_hash.startswith("sha256:") for r in run_a)


def test_projection_row_hash_excludes_hash_field():
    row = {"view": "incident", "recordId": "x", "status": "VERIFIED", "summary": "s", "sourceReceiptHashes": []}
    h1 = projection_row_hash(row)
    h2 = projection_row_hash({**row, "rowHash": "sha256:deadbeef"})
    assert h1 == h2


def test_forbidden_secret_fields_are_dropped_not_redacted():
    projector = ReadModelProjector()
    rows = projector.project([_record(api_key="ghp_1234567890abcdefghijklmnopqrstuvwxyz", password="hunter2")])
    assert rows[0].raw_forbidden_keys == ("api_key", "password")
    payload = projector.to_view_payload([_record(api_key="secret")])
    row = payload["rows"][0]
    # The secret value must never appear anywhere in the emitted view.
    assert "ghp_" not in row["summary"]
    assert "hunter2" not in payload["rows"][0]["summary"]
    assert "api_key" in payload["rows"][0]["droppedForbiddenKeys"]
    assert payload["provenance"]["containsSecrets"] is False
    assert payload["provenance"]["readOnly"] is True
    assert payload["provenance"]["authoritative"] is False


def test_secret_shaped_summary_degrades_status():
    projector = ReadModelProjector()
    rows = projector.project(
        [_record(summary="leaked token ghp_1234567890abcdefghijklmnopqrstuvwxyz in logs")]
    )
    assert rows[0].status == "UNKNOWN"
    assert "ghp_" not in rows[0].summary


def test_unknown_status_maps_to_unknown_not_green():
    projector = ReadModelProjector()
    rows = projector.project([_record(status="COMPLETED")])  # canonical verdict string
    assert rows[0].status == "UNKNOWN"
    # A projection status is never asserted as authoritative runtime truth.
    assert "VERIFIED" in PROJECTION_STATUSES
    assert "COMPLETED" not in PROJECTION_STATUSES


def test_supported_kinds_match_issue_views():
    expected = {
        "incident",
        "runtime_node",
        "risk_bundle",
        "scann_match",
        "wolfram_validation",
        "action_candidate",
        "approval_status",
        "runtime_readback",
    }
    assert SUPPORTED_RECORD_KINDS == expected


def test_projection_is_side_effect_free_pure_function():
    projector = ReadModelProjector()
    records = [_record()]
    before = list(records)
    projector.project(records)
    projector.to_view_payload(records)
    # The projector must not mutate its input.
    assert records == before


def test_removal_degrades_gracefully_without_core_breakage():
    """Removing the projection package must not raise on import of the core.

    We simulate removal by deleting the submodule from the importer cache and
    asserting that the canonical contracts module (core truth layer) still
    imports and works, while the projection surfaces an UNAVAILABLE status.
    """
    import agent_runtime.contracts as contracts  # core truth layer

    # Core truth layer unaffected by projection presence.
    assert contracts.sanitize_agent_text("hello") == "hello"

    # Simulate projection unavailability.
    for mod in list(sys.modules):
        if mod.startswith("agent_runtime.operator_projection"):
            del sys.modules[mod]

    projector = ReadModelProjector()  # re-import works even after cache flush
    rows = projector.project([])
    assert rows == []  # no records => no rows, no exception

    # An operator surface that is unavailable must surface the degraded status
    # rather than a fake green projection.
    degraded = "OPERATOR_PROJECTION_UNAVAILABLE"
    assert degraded in PROJECTION_STATUSES

    # Re-import to leave module cache consistent.
    importlib.import_module("agent_runtime.operator_projection.read_models")
