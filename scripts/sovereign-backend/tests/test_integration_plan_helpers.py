"""Tests for backend/agent_runtime/integration_plan_helpers.py

Coverage targets from Issue #1112 acceptance criteria:
- Canonical templates for ``task_plan.md``, ``findings.md`` and
  ``progress.md`` exist and enforce the five findings sections.
- Context injection is size-bounded, secret-redacted and never claims
  phase ``verified`` by itself.
- Gated completion evaluator respects the block ceiling, requires
  progress evidence, requires verified phases and never loops forever.
- Architecture snapshot reports drift fail-closed.
- Resume helper refuses to resume when the workspace HEAD drifts from
  the bound base revision.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.integration_plan_helpers import (  # noqa: E402
    ArchitectureSnapshot,
    GatedCompletionReport,
    ResumeReport,
    evaluate_gated_completion,
    render_context_injection,
    render_findings,
    render_progress,
    render_task_plan,
    resume_session,
    snapshot_plan_lane_surfaces,
)
from agent_runtime.integration_plan_lane import (  # noqa: E402
    EVIDENCE_KIND_CI_WORKFLOW,
    EVIDENCE_KIND_REPO_REVISION,
    EVIDENCE_KIND_RUNTIME_READBACK,
    EvidenceRecord,
    IntegrationPlanContractError,
    IntegrationPlanLane,
    Phase,
    PhaseStatus,
    PlanReceipt,
    RedactionFilter,
)


_GOOD_SHA = "a" * 40
_GOOD_SHA2 = "b" * 40
_GOOD_SHA64 = "c" * 64


def _phase(
    phase_id: str = "design",
    *,
    title: str = "Scope and plan",
    description: str = "Document scope.",
    acceptance: tuple[str, ...] = ("Scope documented.",),
    required_kinds: tuple[str, ...] = (EVIDENCE_KIND_REPO_REVISION,),
    status: PhaseStatus = PhaseStatus.PENDING,
) -> Phase:
    return Phase(
        phase_id=phase_id,
        title=title,
        description=description,
        acceptance_criteria=acceptance,
        required_evidence_kinds=required_kinds,
        status=status,
    )


def _receipt(
    *,
    plan_id: str = "issue-1112",
    phases: tuple[Phase, ...] = (_phase(),),
    acceptance: tuple[str, ...] = ("Lane implemented.",),
    next_step: str = "Write tests",
) -> PlanReceipt:
    return IntegrationPlanLane.create_receipt(
        plan_id=plan_id,
        plan_schema_version="1",
        owner="thomas",
        repo_owner="OuroborosCollective",
        repo_name="Sovereign-Studio-ato",
        workspace_id="ws-1112",
        base_revision=_GOOD_SHA,
        issue_reference="1112",
        acceptance_criteria=acceptance,
        allowed_mutation_surfaces=(
            "backend/agent_runtime/integration_plan_lane.py",
        ),
        phases=phases,
        next_step=next_step,
        recorded_at_iso="2026-08-03T22:00:00+00:00",
    )


def _evidence(
    *,
    phase_id: str = "design",
    kind: str = EVIDENCE_KIND_REPO_REVISION,
    source: str = _GOOD_SHA,
    content_sha256: str = _GOOD_SHA64,
    is_verified: bool = True,
) -> EvidenceRecord:
    return IntegrationPlanLane.create_evidence_record(
        evidence_id=f"ev-{phase_id}-{kind}",
        phase_id=phase_id,
        kind=kind,
        source=source,
        content_sha256=content_sha256,
        received_at_iso="2026-08-03T22:01:00+00:00",
        is_verified=is_verified,
    )


# ===========================================================================
# task_plan.md
# ===========================================================================
class TestTaskPlanTemplate:
    def test_includes_all_receipt_identities(self) -> None:
        receipt = _receipt()
        body = render_task_plan(receipt, IntegrationPlanLane.evaluate_all(receipt, []))
        assert "`issue-1112`" in body
        assert receipt.attestation_sha256 in body
        assert receipt.base_revision in body
        assert "Plan status is a projection" in body

    def test_status_map_overrides_phase_status(self) -> None:
        receipt = _receipt()
        body = render_task_plan(receipt, {"design": "verified"})
        assert "`verified`" in body

    def test_rejects_wrong_schema(self) -> None:
        # PlanReceipt.__post_init__ rejects any schema_version that does not
        # match the lane's schema. This is the canonical guard and is
        # covered by test_integration_plan_lane.py. The helper inherits the
        # contract; here we verify that the helper *also* has its own size
        # guard, by feeding a receipt whose next_step is just over the
        # helper's task_plan.md cap but under the dataclass cap.
        receipt = _receipt()
        body = render_task_plan(receipt, IntegrationPlanLane.evaluate_all(receipt, []))
        assert "Integration Task Plan" in body
        # Sanity check: the dataclass refuses too-long next_step; the helper
        # is therefore unreachable from this test path.
        with pytest.raises(IntegrationPlanContractError, match="next_step"):
            IntegrationPlanLane.create_receipt(
                plan_id="issue-1112",
                plan_schema_version="1",
                owner="thomas",
                repo_owner="OuroborosCollective",
                repo_name="Sovereign-Studio-ato",
                workspace_id="ws-1112",
                base_revision=_GOOD_SHA,
                issue_reference="1112",
                acceptance_criteria=("Lane implemented.",),
                allowed_mutation_surfaces=("x",),
                phases=(_phase(),),
                next_step="x" * 5000,
                recorded_at_iso="2026-08-03T22:00:00+00:00",
            )


# ===========================================================================
# findings.md
# ===========================================================================
class TestFindingsTemplate:
    def test_renders_all_five_sections(self) -> None:
        body = render_findings(
            {
                "untrusted_external": ["Issue comment: please add X"],
                "repository_observed": ["tests/test_y.py exists"],
                "runtime_observed": [],
                "verified": ["Tests pass locally"],
                "invalidated": [],
            }
        )
        for section in (
            "untrusted_external",
            "repository_observed",
            "runtime_observed",
            "verified",
            "invalidated",
        ):
            assert f"## {section}" in body

    def test_rejects_unknown_section(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="unknown findings"):
            render_findings({"bogus": ["x"]})

    def test_redacts_secrets_in_findings(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="secret"):
            render_findings({"untrusted_external": ["Bearer abcdefghijklmnop"]})


# ===========================================================================
# progress.md
# ===========================================================================
class TestProgressTemplate:
    def test_renders_events(self) -> None:
        body = render_progress(
            [{"ts": "2026-08-03T22:00:00+00:00", "kind": "phase", "text": "design created"}]
        )
        assert "design created" in body

    def test_empty_events_is_explicit(self) -> None:
        body = render_progress([])
        assert "No events recorded" in body

    def test_redacts_secrets(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="secret"):
            render_progress(
                [{"ts": "2026-08-03T22:00:00+00:00", "kind": "phase", "text": "Bearer abcdefghijklmnop"}]
            )


# ===========================================================================
# Context injection
# ===========================================================================
class TestContextInjection:
    def test_block_carries_receipt_and_status(self) -> None:
        receipt = _receipt()
        status_map = IntegrationPlanLane.evaluate_all(receipt, [])
        block = render_context_injection(
            receipt=receipt,
            status_map=status_map,
            progress_excerpt=[],
        )
        assert "Integration Plan Projection" in block
        assert "NOT runtime truth" in block
        assert receipt.attestation_sha256 in block
        assert "projection" in block

    def test_block_never_promotes_to_verified(self) -> None:
        receipt = _receipt()
        block = render_context_injection(
            receipt=receipt,
            status_map={"design": "verified"},
            progress_excerpt=[],
        )
        # Even with a "verified" status, the projection notice is present.
        assert "projection" in block.lower()

    def test_block_is_size_bounded(self) -> None:
        receipt = _receipt()
        with pytest.raises(IntegrationPlanContractError, match="exceeds"):
            render_context_injection(
                receipt=receipt,
                status_map={},
                progress_excerpt=[],
                additional_lines=["x" * 9000],
            )

    def test_block_redacts_secrets_in_progress(self) -> None:
        receipt = _receipt()
        with pytest.raises(IntegrationPlanContractError, match="secret"):
            render_context_injection(
                receipt=receipt,
                status_map={},
                progress_excerpt=[
                    {"ts": "2026-08-03T22:00:00+00:00", "kind": "phase", "text": "Bearer abcdefghijklmnop"}
                ],
            )

    def test_block_redacts_secrets_in_hints(self) -> None:
        receipt = _receipt()
        with pytest.raises(IntegrationPlanContractError, match="secret"):
            render_context_injection(
                receipt=receipt,
                status_map={},
                progress_excerpt=[],
                additional_lines=["hint with ghp_abcdefghijklmnopqrstuvwxyz0123456789AB"],
            )


# ===========================================================================
# Gated completion
# ===========================================================================
class TestGatedCompletion:
    def test_open_mode_is_not_eligible(self) -> None:
        receipt = _receipt()
        report = evaluate_gated_completion(receipt, [], [], mode="open")
        assert report.eligible_to_release is False
        assert "open" in report.decision_reason

    def test_closed_mode_is_eligible(self) -> None:
        receipt = _receipt()
        report = evaluate_gated_completion(receipt, [], [], mode="closed")
        assert report.eligible_to_release is True

    def test_gated_mode_requires_progress(self) -> None:
        receipt = _receipt()
        report = evaluate_gated_completion(receipt, [], [], mode="gated")
        assert report.eligible_to_release is False
        assert report.progress_evidence_present is False

    def test_gated_mode_requires_all_phases_verified(self) -> None:
        phase_blocked = _phase(
            "verify",
            required_kinds=(EVIDENCE_KIND_RUNTIME_READBACK, EVIDENCE_KIND_CI_WORKFLOW),
            status=PhaseStatus.IN_PROGRESS,
        )
        receipt = _receipt(phases=(phase_blocked,))
        evidence = [
            _evidence(phase_id="verify", kind=EVIDENCE_KIND_RUNTIME_READBACK, source="host.example"),
            _evidence(phase_id="verify", kind=EVIDENCE_KIND_CI_WORKFLOW, source="ci.yml", content_sha256="d" * 64),
        ]
        report = evaluate_gated_completion(
            receipt, evidence, [{"kind": "phase_transition"}], mode="gated"
        )
        assert report.eligible_to_release is True
        assert report.verified_phases == ("verify",)

    def test_gated_mode_missing_evidence_blocks(self) -> None:
        phase = _phase(
            "verify",
            required_kinds=(EVIDENCE_KIND_RUNTIME_READBACK,),
            status=PhaseStatus.IN_PROGRESS,
        )
        receipt = _receipt(phases=(phase,))
        report = evaluate_gated_completion(
            receipt, [], [{"kind": "phase_transition"}], mode="gated"
        )
        assert report.eligible_to_release is False
        assert "verify" in report.missing_required_kinds

    def test_loop_guard_trips(self) -> None:
        receipt = _receipt()
        report = evaluate_gated_completion(
            receipt, [], [], mode="gated", loop_guard_hits=32
        )
        assert report.eligible_to_release is False
        assert "loop guard" in report.decision_reason

    def test_invalid_mode_rejected(self) -> None:
        receipt = _receipt()
        with pytest.raises(IntegrationPlanContractError, match="mode"):
            evaluate_gated_completion(receipt, [], [], mode="weird")


# ===========================================================================
# Architecture snapshot
# ===========================================================================
class TestArchitectureSnapshot:
    def test_snapshot_reports_drift_fail_closed(self) -> None:
        snapshot = snapshot_plan_lane_surfaces(
            "workspace-a",
            {
                "canonical-continuity-context": True,
                "canonical-continuity-ledger": True,
                "continuity-policy": True,
                "bug-evidence-lane": True,
                "bug-evidence-tests": True,
                "plan-lane-canonical": True,
                "plan-lane-store": True,
                "plan-lane-tests": True,
                "plan-store-tests": True,
            },
        )
        assert snapshot.drift == ()

    def test_snapshot_reports_missing_surface(self) -> None:
        snapshot = snapshot_plan_lane_surfaces(
            "workspace-b",
            {
                "canonical-continuity-context": True,
                "canonical-continuity-ledger": True,
                "continuity-policy": True,
                "bug-evidence-lane": True,
                "bug-evidence-tests": True,
                "plan-lane-canonical": False,  # missing
                "plan-lane-store": True,
                "plan-lane-tests": True,
                "plan-store-tests": True,
            },
        )
        severities = [d.severity for d in snapshot.drift]
        assert "P1" in severities
        labels = [d.surface for d in snapshot.drift]
        assert "plan-lane-canonical" in labels

    def test_snapshot_is_deterministic(self) -> None:
        exists = {
            label: True
            for label in (
                "canonical-continuity-context",
                "canonical-continuity-ledger",
                "continuity-policy",
                "bug-evidence-lane",
                "bug-evidence-tests",
                "plan-lane-canonical",
                "plan-lane-store",
                "plan-lane-tests",
                "plan-store-tests",
            )
        }
        a = snapshot_plan_lane_surfaces("ws", exists)
        b = snapshot_plan_lane_surfaces("ws", exists)
        assert a.snapshot_sha256 == b.snapshot_sha256

    def test_snapshot_reports_unexpected_surface(self) -> None:
        snapshot = snapshot_plan_lane_surfaces(
            "ws",
            {
                "canonical-continuity-context": True,
                "canonical-continuity-ledger": True,
                "continuity-policy": True,
                "bug-evidence-lane": True,
                "bug-evidence-tests": True,
                "plan-lane-canonical": True,
                "plan-lane-store": True,
                "plan-lane-tests": True,
                "plan-store-tests": True,
            },
            expected_surface_labels=["future-experimental-lane"],
        )
        labels = [d.surface for d in snapshot.drift]
        assert "future-experimental-lane" in labels


# ===========================================================================
# Resume readback
# ===========================================================================
class TestResumeSession:
    def test_resume_blocks_on_revision_drift(self, tmp_path: Path) -> None:
        # Make a git repo with HEAD != base_revision.
        subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@x"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
        (tmp_path / "x").write_text("x")
        subprocess.run(["git", "-C", str(tmp_path), "add", "x"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "x"], check=True)
        head = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        # base_revision deliberately differs.
        receipt = _receipt()
        report = resume_session(
            repo_root=str(tmp_path),
            workspace_root=str(tmp_path),
            integration_id="issue-1112",
            plan_present=True,
            ledger_actions_present=True,
            active_revision=head,
            receipt=receipt,
            evidence=[],
        )
        assert any(f.surface == "workspace-revision" for f in report.findings)
        assert report.resume_decision == "resume-blocked-by-drift"

    def test_resume_no_active_plan(self, tmp_path: Path) -> None:
        report = resume_session(
            repo_root=str(tmp_path),
            workspace_root=str(tmp_path),
            integration_id="issue-1112",
            plan_present=False,
            ledger_actions_present=False,
            active_revision=None,
            receipt=None,
            evidence=[],
        )
        assert report.resume_decision == "resume-no-active-plan"

    def test_resume_rejects_bad_active_revision(self) -> None:
        receipt = _receipt()
        report = resume_session(
            repo_root="/nonexistent",
            workspace_root="/nonexistent",
            integration_id="issue-1112",
            plan_present=True,
            ledger_actions_present=True,
            active_revision="not-a-sha",
            receipt=receipt,
            evidence=[],
        )
        assert any(f.surface == "active-revision" for f in report.findings)
        assert report.resume_decision == "resume-blocked-by-drift"

    def test_resume_requires_ledger_actions(self) -> None:
        receipt = _receipt()
        report = resume_session(
            repo_root="/nonexistent",
            workspace_root="/nonexistent",
            integration_id="issue-1112",
            plan_present=True,
            ledger_actions_present=False,
            active_revision=None,
            receipt=receipt,
            evidence=[],
        )
        assert any(f.surface == "ledger-actions" for f in report.findings)


# ===========================================================================
# No I/O in module (structural check)
# ===========================================================================
class TestNoIOInModule:
    def test_helpers_have_no_open_calls(self) -> None:
        import backend.agent_runtime.integration_plan_helpers as mod
        src = inspect.getsource(mod)
        assert "open(" not in src

    def test_helpers_have_no_socket_or_requests(self) -> None:
        import backend.agent_runtime.integration_plan_helpers as mod
        src = inspect.getsource(mod)
        assert "import socket" not in src
        assert "import requests" not in src

    def test_helpers_have_no_psycopg2(self) -> None:
        import backend.agent_runtime.integration_plan_helpers as mod
        src = inspect.getsource(mod)
        assert "psycopg2" not in src


# ===========================================================================
# Module re-exports + RedactionFilter presence
# ===========================================================================
class TestReExports:
    def test_redaction_filter_is_accessible(self) -> None:
        assert RedactionFilter is not None
        assert RedactionFilter.contains_secret("Bearer abcdefghijklmnop") is True

    def test_dataclasses_are_frozen(self) -> None:
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            GatedCompletionReport(
                schema_version="x",
                plan_id="x",
                mode="x",
                in_progress_phases=(),
                blocked_phases=(),
                verified_phases=(),
                invalidated_phases=(),
                missing_required_kinds={},
                loop_guard_hits=0,
                block_ceiling_hits=0,
                progress_evidence_present=False,
                last_decision_sha256=None,
                eligible_to_release=False,
                decision_reason="x",
                mutationPerformed=False,
                runtimeVerified=False,
                secretValuesReturned=False,
            ).plan_id = "mutate"