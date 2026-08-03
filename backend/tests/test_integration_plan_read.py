"""Tests for backend/agent_runtime/integration_plan_read.py

The reader CLI is a read-only, non-mutating tool that snapshots every
canonical file in a ``.planning/<integration-id>`` directory.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

TEST_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from agent_runtime.integration_plan_read import (  # noqa: E402
    CANONICAL_FILES,
    read_plan,
)
from agent_runtime.integration_plan_lane import (  # noqa: E402
    EVIDENCE_KIND_CI_WORKFLOW,
    EVIDENCE_KIND_REPO_REVISION,
    EVIDENCE_KIND_RUNTIME_READBACK,
    IntegrationPlanLane,
    Phase,
    PhaseStatus,
)
from agent_runtime.integration_plan_store import (  # noqa: E402
    IntegrationPlanStore,
)


EXAMPLE_DIR = ROOT / ".planning" / "example-llm-boundary-binding"


class TestCommitedExample:
    def test_example_directory_exists(self) -> None:
        assert EXAMPLE_DIR.is_dir()
        for name in CANONICAL_FILES:
            assert (EXAMPLE_DIR / name).exists(), f"missing {name}"

    def test_example_attestation_matches(self) -> None:
        receipt = json.loads((EXAMPLE_DIR / "plan.receipt.json").read_text())
        on_disk = (EXAMPLE_DIR / ".attestation").read_text().strip()
        assert receipt["attestationSha256"] == on_disk

    def test_example_active_revision_matches(self) -> None:
        receipt = json.loads((EXAMPLE_DIR / "plan.receipt.json").read_text())
        on_disk = (EXAMPLE_DIR / ".active_revision").read_text().strip()
        assert receipt["baseRevision"] == on_disk

    def test_example_receipt_is_not_runtime_verified(self) -> None:
        receipt = json.loads((EXAMPLE_DIR / "plan.receipt.json").read_text())
        assert receipt["runtimeVerified"] is False
        assert receipt["mutationPerformed"] is False
        assert receipt["secretValuesReturned"] is False


@pytest.fixture
def synth_plan(tmp_path: Path) -> Path:
    """Build a fresh .planning/<integration-id> directory in a tmp dir."""
    store = IntegrationPlanStore(tmp_path)
    plan_id = "synthetic-plan"
    store.init_plan(plan_id)

    phase = Phase(
        phase_id="phase-x",
        title="X",
        description="synthetic",
        acceptance_criteria=("ok",),
        required_evidence_kinds=(EVIDENCE_KIND_REPO_REVISION, EVIDENCE_KIND_CI_WORKFLOW),
        status=PhaseStatus.VERIFIED,
    )
    receipt = IntegrationPlanLane.create_receipt(
        plan_id=plan_id,
        plan_schema_version="1",
        owner="ci",
        repo_owner="X",
        repo_name="Y",
        workspace_id="ci",
        base_revision="a" * 40,
        issue_reference="1112",
        acceptance_criteria=("ok",),
        allowed_mutation_surfaces=("ok",),
        phases=(phase,),
        next_step="ok",
        recorded_at_iso="2026-08-04T00:00:00+00:00",
    )
    store.write_receipt(receipt)
    store.write_attestation(plan_id, receipt.attestation_sha256)
    store.write_active_revision(plan_id, "a" * 40)
    store.write_text(plan_id, "task_plan.md", "synthetic task plan")
    store.write_text(plan_id, "findings.md", "synthetic findings")
    store.write_text(plan_id, "progress.md", "synthetic progress")
    store.append_evidence(
        plan_id,
        {
            "evidenceId": "ev-x-1",
            "phaseId": "phase-x",
            "kind": EVIDENCE_KIND_REPO_REVISION,
            "source": "a" * 40,
            "contentSha256": "b" * 64,
            "receivedAtIso": "2026-08-04T00:00:00+00:00",
            "isVerified": True,
            "redacted": True,
            "verificationNotes": "ok",
        },
    )
    store.append_ledger_action(
        plan_id,
        {
            "schemaVersion": "sovereign.integration-plan-ledger-action.v1",
            "actionId": "ac-test-1",
            "ts": "2026-08-04T00:00:00+00:00",
            "kind": "plan_open",
            "planId": plan_id,
            "actor": "test",
        },
    )
    store.write_mode(plan_id, "open")
    return store.plan_directory(plan_id)


class TestReadPlan:
    def test_read_committed_example(self) -> None:
        snapshot = read_plan(EXAMPLE_DIR)
        assert snapshot["planId"] == "example-llm-boundary-binding"
        assert snapshot["evidenceRecordCount"] >= 1
        assert snapshot["files"]["attestation"]["matchesReceipt"] is True
        assert snapshot["files"]["activeRevision"]["matchesReceipt"] is True
        assert all(snapshot["invariants"]), snapshot.get("errors")
        assert snapshot["errors"] == []

    def test_read_synthetic_plan(self, synth_plan: Path) -> None:
        snapshot = read_plan(synth_plan)
        assert snapshot["planId"] == "synthetic-plan"
        assert snapshot["evidenceRecordCount"] == 1
        assert snapshot["files"]["mode"]["value"] == "open"
        assert snapshot["files"]["attestation"]["matchesReceipt"] is True

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        # Build a partial directory (only the receipt).
        partial = tmp_path / "partial"
        partial.mkdir()
        (partial / "plan.receipt.json").write_text("{}")
        with pytest.raises(FileNotFoundError):
            read_plan(partial)

    def test_attestation_mismatch_detected(self, synth_plan: Path) -> None:
        # Tamper with the .attestation file.
        (synth_plan / ".attestation").write_text("deadbeef" + "00" * 28)
        snapshot = read_plan(synth_plan)
        assert snapshot["files"]["attestation"]["matchesReceipt"] is False
        assert snapshot["errors"] != []
        # The attestation_ok invariant (index 3) should be False.
        assert snapshot["invariants"][3] is False


class TestReaderCLI:
    def test_main_help(self) -> None:
        import agent_runtime.integration_plan_read as reader
        from unittest import mock
        with mock.patch.object(reader.sys, "argv", ["integration_plan_read.py", "--help"]):
            with pytest.raises(SystemExit):
                reader.main()

    def test_main_missing_dir(self, tmp_path: Path) -> None:
        import agent_runtime.integration_plan_read as reader
        from unittest import mock
        with mock.patch.object(
            reader.sys,
            "argv",
            ["integration_plan_read.py", str(tmp_path / "not-here")],
        ):
            rc = reader.main()
        assert rc == 1

    def test_main_strict_on_example(self) -> None:
        import agent_runtime.integration_plan_read as reader
        from unittest import mock
        with mock.patch.object(
            reader.sys,
            "argv",
            ["integration_plan_read.py", str(EXAMPLE_DIR), "--strict"],
        ):
            rc = reader.main()
        assert rc == 0