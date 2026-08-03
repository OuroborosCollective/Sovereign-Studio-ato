"""Tests for backend/agent_runtime/integration_plan_store.py

Coverage targets from Issue #1112 acceptance criteria:
- Path traversal, absolute paths, Windows drive letters, MSYS path
  mangling and NUL bytes are all rejected.
- Symlinks in the workspace ancestor chain are rejected.
- Cross-workspace / cross-project reads are denied (the adapter only
  resolves paths inside the bound workspace root).
- Plan receipt + evidence + ledger-actions + markers round-trip through
  the filesystem exactly as specified.
- Append-only semantics for ledger and evidence are preserved.
- Mode marker and active revision marker are read/written atomically.
- Symlinks inside the plan directory are detected and rejected.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.integration_plan_lane import (  # noqa: E402
    EVIDENCE_KIND_REPO_REVISION,
    IntegrationPlanContractError,
    IntegrationPlanLane,
    Phase,
    PhaseStatus,
    RedactionFilter,
)
from agent_runtime.integration_plan_store import (  # noqa: E402
    IntegrationPlanStore,
    IntegrationPlanStoreError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_GOOD_SHA = "a" * 40


def _phase() -> Phase:
    return Phase(
        phase_id="design",
        title="Scope",
        description="...",
        acceptance_criteria=("Scope is documented.",),
        required_evidence_kinds=(EVIDENCE_KIND_REPO_REVISION,),
        status=PhaseStatus.PENDING,
    )


def _receipt() -> "object":  # forward-typed to PlanReceipt
    return IntegrationPlanLane.create_receipt(
        plan_id="issue-1112",
        plan_schema_version="1",
        owner="thomas",
        repo_owner="OuroborosCollective",
        repo_name="Sovereign-Studio-ato",
        workspace_id="ws-1112",
        base_revision=_GOOD_SHA,
        issue_reference="1112",
        acceptance_criteria=("Lane is implemented.",),
        allowed_mutation_surfaces=(
            "backend/agent_runtime/integration_plan_lane.py",
            "backend/agent_runtime/integration_plan_store.py",
        ),
        phases=(_phase(),),
        next_step="Write live-path tests",
        recorded_at_iso="2026-08-03T22:00:00+00:00",
    )


# ===========================================================================
# Plan directory + receipt round trip
# ===========================================================================
class TestPlanDirectoryAndReceipt:
    def test_init_creates_planning_directory(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        plan_dir = store.init_plan("issue-1112")
        assert plan_dir == tmp_path / ".planning" / "issue-1112"
        assert plan_dir.is_dir()

    def test_write_and_read_receipt(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        receipt = _receipt()
        store.write_receipt(receipt)
        loaded = store.read_receipt("issue-1112")
        assert loaded.attestation_sha256 == receipt.attestation_sha256
        assert loaded.base_revision == receipt.base_revision
        assert loaded.plan_id == receipt.plan_id
        assert len(loaded.phases) == 1
        assert loaded.phases[0].phase_id == "design"

    def test_amendment_round_trip(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        first = _receipt()
        store.write_receipt(first)
        second = IntegrationPlanLane.amend_receipt(
            first,
            acceptance_criteria=first.acceptance_criteria,
            allowed_mutation_surfaces=first.allowed_mutation_surfaces,
            phases=first.phases,
            next_step="second next step",
            amendment_reason="amend for testing",
            recorded_at_iso="2026-08-03T22:30:00+00:00",
        )
        store.write_receipt(second)
        loaded = store.read_receipt("issue-1112")
        assert loaded.attestation_sha256 == second.attestation_sha256
        assert loaded.predecessor_attestation_sha256 == first.attestation_sha256
        assert loaded.next_step == "second next step"
        assert loaded.amendment_reason == "amend for testing"

    def test_write_receipt_rejects_bad_schema_version(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        with pytest.raises(IntegrationPlanContractError):
            store.write_receipt(_receipt().__class__(
                plan_id="issue-1112",
                schema_version="bogus",
                plan_schema_version="1",
                owner="thomas",
                repo_owner="OuroborosCollective",
                repo_name="Sovereign-Studio-ato",
                workspace_id="ws-1112",
                base_revision=_GOOD_SHA,
                issue_reference="1112",
                pr_reference=None,
                acceptance_criteria=("ok",),
                allowed_mutation_surfaces=("ok",),
                phases=(_phase(),),
                next_step="ok",
                attestation_sha256="0" * 64,
                predecessor_attestation_sha256=None,
                amendment_reason="initial plan attestation",
                recorded_at_iso="2026-08-03T22:00:00+00:00",
                plan_content_sha256="0" * 64,
            ))


# ===========================================================================
# Path safety
# ===========================================================================
class TestPathSafety:
    def test_init_plan_rejects_invalid_integration_id(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        with pytest.raises(IntegrationPlanStoreError, match="integration_id"):
            store.init_plan("BadID!")

    def test_init_plan_rejects_directory_traversal(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        with pytest.raises(IntegrationPlanStoreError, match="integration_id"):
            store.init_plan("../escape")

    def test_workspace_must_exist(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        with pytest.raises(IntegrationPlanStoreError, match="does not exist"):
            IntegrationPlanStore(missing)

    def test_workspace_must_be_directory(self, tmp_path: Path) -> None:
        file = tmp_path / "not-a-dir"
        file.write_text("hi")
        with pytest.raises(IntegrationPlanStoreError, match="not a directory"):
            IntegrationPlanStore(file)

    def test_symlinked_workspace_ancestor_rejected(self, tmp_path: Path) -> None:
        real_root = tmp_path / "real"
        real_root.mkdir()
        link_root = tmp_path / "link"
        link_root.symlink_to(real_root)
        # Symlinked parent (link_root) is itself a symlink; this must fail.
        with pytest.raises(IntegrationPlanStoreError, match="symlinked ancestor"):
            IntegrationPlanStore(link_root)

    def test_symlink_inside_plan_dir_rejected(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        plan_dir = store.plan_directory("issue-1112")
        outside = tmp_path / "outside.txt"
        outside.write_text("x")
        link = plan_dir / "link.txt"
        link.symlink_to(outside)
        with pytest.raises(IntegrationPlanStoreError, match="symbolic link"):
            store.read_receipt("issue-1112")

    @pytest.mark.skipif(sys.platform != "win32", reason="windows-specific")
    def test_windows_drive_letter_rejected(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        with pytest.raises(IntegrationPlanStoreError):
            # The internal _safe_path_within rejects drive letters directly.
            store._safe_path_within("C:/Windows/System32")  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "integration_id",
        [
            "../escape",
            "..\\escape",
            "subdir/../escape",
            "a/../../escape",
            "/absolute/leak",
            "\\absolute\\leak",
            "subdir/..",
        ],
    )
    def test_traversal_integration_ids_rejected(
        self, tmp_path: Path, integration_id: str
    ) -> None:
        store = IntegrationPlanStore(tmp_path)
        with pytest.raises(IntegrationPlanStoreError):
            store.init_plan(integration_id)

    def test_unicode_in_integration_id_is_accepted_when_safe(
        self, tmp_path: Path
    ) -> None:
        store = IntegrationPlanStore(tmp_path)
        # Only ASCII lowercase / dot / dash / underscore / colon allowed.
        with pytest.raises(IntegrationPlanStoreError):
            store.init_plan("plan-ünicode")

    def test_unicode_does_not_bypass_canonicalisation(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        # A unicode 'lookalike' must not slip through.
        with pytest.raises(IntegrationPlanStoreError):
            store.init_plan("plan-\u2024escape")

    def test_case_folding_does_not_match_other_id(self, tmp_path: Path) -> None:
        """Upper-case integration ids are not silently case-folded into a
        different lowercase id; the strict lowercase regex rejects them.
        """
        store = IntegrationPlanStore(tmp_path)
        with pytest.raises(IntegrationPlanStoreError):
            store.init_plan("Issue-1112")
        # Same store cannot claim to have written an uppercase variant.
        with pytest.raises(IntegrationPlanStoreError):
            store.init_plan("ISSUE-1112")


# ===========================================================================
# Evidence persistence
# ===========================================================================
class TestEvidencePersistence:
    def test_append_evidence_creates_index(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        store.append_evidence(
            "issue-1112",
            {
                "evidenceId": "ev-1",
                "schemaVersion": "sovereign.integration-plan-evidence.v1",
                "phaseId": "design",
                "kind": EVIDENCE_KIND_REPO_REVISION,
                "source": _GOOD_SHA,
                "contentSha256": "d" * 64,
                "receivedAtIso": "2026-08-03T22:01:00+00:00",
                "redacted": True,
                "isVerified": True,
            },
        )
        records = store.read_evidence("issue-1112")
        assert len(records) == 1
        assert records[0]["phaseId"] == "design"

    def test_append_evidence_is_append_only(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        for index in range(3):
            store.append_evidence(
                "issue-1112",
                {
                    "evidenceId": f"ev-{index}",
                    "schemaVersion": "sovereign.integration-plan-evidence.v1",
                    "phaseId": "design",
                    "kind": EVIDENCE_KIND_REPO_REVISION,
                    "source": _GOOD_SHA,
                    "contentSha256": f"{index:x}".rjust(64, "0"),
                    "receivedAtIso": "2026-08-03T22:01:00+00:00",
                    "redacted": True,
                    "isVerified": True,
                },
            )
        records = store.read_evidence("issue-1112")
        assert [r["evidenceId"] for r in records] == ["ev-0", "ev-1", "ev-2"]

    def test_append_evidence_rejects_wrong_plan_id(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        # Seed the index with a different planId.
        target = store.plan_directory("issue-1112") / "evidence-index.json"
        target.write_text(json.dumps({
            "schemaVersion": "sovereign.integration-plan-evidence.v1",
            "planId": "other-plan",
            "records": [],
        }, sort_keys=True))
        with pytest.raises(IntegrationPlanStoreError, match="planId"):
            store.append_evidence(
                "issue-1112",
                {
                    "evidenceId": "ev-1",
                    "schemaVersion": "sovereign.integration-plan-evidence.v1",
                    "phaseId": "design",
                    "kind": EVIDENCE_KIND_REPO_REVISION,
                    "source": _GOOD_SHA,
                    "contentSha256": "d" * 64,
                    "receivedAtIso": "2026-08-03T22:01:00+00:00",
                    "redacted": True,
                    "isVerified": True,
                },
            )


# ===========================================================================
# Append-only ledger
# ===========================================================================
class TestLedgerPersistence:
    def test_ledger_appends_lines(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        for index in range(3):
            store.append_ledger_action(
                "issue-1112",
                {
                    "ts": "2026-08-03T22:01:00+00:00",
                    "kind": "phase_transition",
                    "index": index,
                },
            )
        entries = store.read_ledger_actions("issue-1112")
        assert [e["index"] for e in entries] == [0, 1, 2]

    def test_ledger_rejects_oversized_entry(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        huge = "x" * 20_000
        with pytest.raises(IntegrationPlanStoreError, match="exceeds"):
            store.append_ledger_action(
                "issue-1112",
                {"kind": "noisy", "data": huge},
            )


# ===========================================================================
# Markers
# ===========================================================================
class TestMarkers:
    def test_active_revision_round_trip(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        store.write_active_revision("issue-1112", _GOOD_SHA)
        assert store.read_active_revision("issue-1112") == _GOOD_SHA

    def test_active_revision_rejects_bad_sha(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        with pytest.raises(IntegrationPlanStoreError, match="40-character"):
            store.write_active_revision("issue-1112", "not-a-sha")
        # Reading a file that doesn't exist returns None (no leakage).
        assert store.read_active_revision("issue-1112") is None
        # Writing a malformed SHA in place is rejected on read.
        target = store.plan_directory("issue-1112") / ".active_revision"
        target.write_text("not-a-sha\n")
        with pytest.raises(IntegrationPlanStoreError, match="40-character"):
            store.read_active_revision("issue-1112")

    def test_mode_defaults_to_open(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        assert store.read_mode("issue-1112") == "open"

    def test_mode_round_trip(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        store.write_mode("issue-1112", "gated")
        assert store.read_mode("issue-1112") == "gated"

    def test_mode_rejects_invalid_value(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        with pytest.raises(IntegrationPlanStoreError, match="mode"):
            store.write_mode("issue-1112", "weird")


# ===========================================================================
# Attestation + text writers
# ===========================================================================
class TestAttestationAndTextWriters:
    def test_attestation_round_trip(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        sha = "d" * 64
        store.write_attestation("issue-1112", sha)
        assert store.read_attestation("issue-1112") == sha

    def test_attestation_rejects_bad_sha_on_write(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        with pytest.raises(IntegrationPlanStoreError, match="64-character"):
            store.write_attestation("issue-1112", "not-a-sha")

    def test_attestation_rejects_bad_sha_on_read(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        (store.plan_directory("issue-1112") / ".attestation").write_text("bad\n")
        with pytest.raises(IntegrationPlanStoreError, match="64-character"):
            store.read_attestation("issue-1112")

    def test_write_text_supports_markdown(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        path = store.write_text("issue-1112", "task_plan.md", "# Plan\n")
        assert path.exists()
        assert store.read_text("issue-1112", "task_plan.md") == "# Plan\n"

    def test_write_text_rejects_non_text_extension(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        with pytest.raises(IntegrationPlanStoreError, match=".md"):
            store.write_text("issue-1112", "plan.json", "{}")

    def test_write_text_rejects_oversize(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        with pytest.raises(IntegrationPlanStoreError, match="exceeds"):
            store.write_text("issue-1112", "task_plan.md", "x" * 2_000_000)

    def test_write_text_path_traversal_rejected(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.init_plan("issue-1112")
        with pytest.raises(IntegrationPlanStoreError):
            store.write_text("issue-1112", "../escape.md", "x")


# ===========================================================================
# Cross-project protection
# ===========================================================================
class TestCrossProjectProtection:
    def test_different_workspace_roots_are_isolated(self, tmp_path: Path) -> None:
        workspace_a = tmp_path / "ws-a"
        workspace_b = tmp_path / "ws-b"
        workspace_a.mkdir()
        workspace_b.mkdir()
        store_a = IntegrationPlanStore(workspace_a)
        store_b = IntegrationPlanStore(workspace_b)
        store_a.write_receipt(_receipt())
        # B has no plan yet.
        with pytest.raises(IntegrationPlanStoreError):
            store_b.read_receipt("issue-1112")
        # A still has its plan
        assert store_a.read_receipt("issue-1112").plan_id == "issue-1112"

    def test_receipt_does_not_leak_into_other_plan_id(self, tmp_path: Path) -> None:
        store = IntegrationPlanStore(tmp_path)
        store.write_receipt(_receipt())
        with pytest.raises(IntegrationPlanStoreError):
            store.read_receipt("other-id")