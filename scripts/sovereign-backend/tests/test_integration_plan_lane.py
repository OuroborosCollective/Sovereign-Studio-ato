"""Tests for backend/agent_runtime/integration_plan_lane.py

Coverage targets from Issue #1112 acceptance criteria:
- Schema-versioned receipt and evidence records are immutable dataclasses.
- Plan amendment is append-only and binds the predecessor attestation hash.
- Attestation hash is recomputable from canonical content.
- Phase status is computed from required evidence kinds; Markdown alone
  cannot promote a phase to ``verified``.
- Verified evidence records must be marked redacted.
- Secret-shaped content is rejected at every entry point.
- Cross-plan / cross-repo / cross-workspace / cross-revision bindings are
  preserved across amendments.
- No I/O in the module (structural check).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.integration_plan_lane import (  # noqa: E402
    EVIDENCE_KIND_ARTIFACT_DIGEST,
    EVIDENCE_KIND_CI_WORKFLOW,
    EVIDENCE_KIND_LEDGER_HEAD,
    EVIDENCE_KIND_PR_HEAD,
    EVIDENCE_KIND_REPO_REVISION,
    EVIDENCE_KIND_RUNTIME_READBACK,
    EVIDENCE_KIND_PATCHMON_READBACK,
    EVIDENCE_SCHEMA_VERSION,
    SCHEMA_VERSION,
    EvidenceRecord,
    IntegrationPlanContractError,
    IntegrationPlanLane,
    Phase,
    PhaseStatus,
    PlanReceipt,
    RedactionFilter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_GOOD_SHA = "a" * 40
_GOOD_SHA2 = "b" * 40
_GOOD_SHA3 = "c" * 40
_GOOD_SHA64 = "d" * 64
_GOOD_SHA64_B = "e" * 64
_OWNER = "OuroborosCollective"
_REPO = "Sovereign-Studio-ato"


def _phase(
    phase_id: str = "design",
    *,
    title: str = "Scope and plan",
    description: str = "Document acceptance and evidence kinds.",
    acceptance: tuple[str, ...] = ("Scope is documented.",),
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
    base_revision: str = _GOOD_SHA,
    phases: tuple[Phase, ...] = (_phase(),),
    next_step: str = "Write live-path tests",
    acceptance: tuple[str, ...] = ("Lane is implemented and tested.",),
    pr_reference: str | None = None,
    amendment_reason: str = "initial plan attestation",
    predecessor: PlanReceipt | None = None,
    recorded_at_iso: str = "2026-08-03T22:00:00+00:00",
) -> PlanReceipt:
    if predecessor is None:
        return IntegrationPlanLane.create_receipt(
            plan_id=plan_id,
            plan_schema_version="1",
            owner="thomas",
            repo_owner=_OWNER,
            repo_name=_REPO,
            workspace_id="ws-1112",
            base_revision=base_revision,
            issue_reference="1112",
            acceptance_criteria=acceptance,
            allowed_mutation_surfaces=(
                "backend/agent_runtime/integration_plan_lane.py",
                "backend/agent_runtime/integration_plan_store.py",
                "backend/tests/test_integration_plan_lane.py",
                "backend/tests/test_integration_plan_store.py",
            ),
            phases=phases,
            next_step=next_step,
            amendment_reason=amendment_reason,
            recorded_at_iso=recorded_at_iso,
        )
    return IntegrationPlanLane.amend_receipt(
        predecessor,
        acceptance_criteria=acceptance,
        allowed_mutation_surfaces=predecessor.allowed_mutation_surfaces,
        phases=phases,
        next_step=next_step,
        amendment_reason=amendment_reason,
        recorded_at_iso=recorded_at_iso,
        pr_reference=pr_reference,
    )


def _evidence(
    *,
    evidence_id: str = "ev-1",
    phase_id: str = "design",
    kind: str = EVIDENCE_KIND_REPO_REVISION,
    source: str = _GOOD_SHA,
    content_sha256: str = _GOOD_SHA64,
    received_at_iso: str = "2026-08-03T22:01:00+00:00",
    is_verified: bool = True,
) -> EvidenceRecord:
    return IntegrationPlanLane.create_evidence_record(
        evidence_id=evidence_id,
        phase_id=phase_id,
        kind=kind,
        source=source,
        content_sha256=content_sha256,
        received_at_iso=received_at_iso,
        is_verified=is_verified,
    )


# ===========================================================================
# Schema + Phase
# ===========================================================================
class TestPhaseContract:
    def test_phase_requires_acceptance_criteria(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="acceptance_criterion"):
            Phase(
                phase_id="design",
                title="Design",
                description="...",
                acceptance_criteria=(),
                required_evidence_kinds=(EVIDENCE_KIND_REPO_REVISION,),
                status=PhaseStatus.PENDING,
            )

    def test_phase_id_must_match_identifier_pattern(self) -> None:
        with pytest.raises(IntegrationPlanContractError):
            Phase(
                phase_id="BadID",
                title="Design",
                description="...",
                acceptance_criteria=("ok",),
                required_evidence_kinds=(EVIDENCE_KIND_REPO_REVISION,),
                status=PhaseStatus.PENDING,
            )

    def test_phase_rejects_unknown_evidence_kind(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="kind"):
            Phase(
                phase_id="design",
                title="Design",
                description="...",
                acceptance_criteria=("ok",),
                required_evidence_kinds=("no_such_kind",),
                status=PhaseStatus.PENDING,
            )

    def test_phase_rejects_secret_shaped_title(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="secret"):
            Phase(
                phase_id="design",
                title="Title with bearer abcdefghijklmnop",
                description="...",
                acceptance_criteria=("ok",),
                required_evidence_kinds=(EVIDENCE_KIND_REPO_REVISION,),
                status=PhaseStatus.PENDING,
            )


# ===========================================================================
# Receipt creation + attestation
# ===========================================================================
class TestReceiptCreation:
    def test_create_receipt_assigns_attestation_and_provenance(self) -> None:
        receipt = _receipt()
        assert receipt.attestation_sha256 != "0" * 64
        assert receipt.attestation_sha256 == _GOOD_SHA64 or len(receipt.attestation_sha256) == 64
        assert receipt.predecessor_attestation_sha256 is None
        assert IntegrationPlanLane.verify_receipt_attestation(receipt) is True

    def test_amendment_binds_predecessor_hash(self) -> None:
        first = _receipt()
        second = _receipt(
            predecessor=first,
            amendment_reason="add verification phase",
            phases=(_phase(), _phase(
                phase_id="verify",
                required_kinds=(EVIDENCE_KIND_RUNTIME_READBACK, EVIDENCE_KIND_ARTIFACT_DIGEST),
            )),
        )
        assert second.predecessor_attestation_sha256 == first.attestation_sha256
        assert second.plan_id == first.plan_id
        assert second.repo_owner == first.repo_owner
        assert second.repo_name == first.repo_name
        assert second.workspace_id == first.workspace_id
        assert second.base_revision == first.base_revision
        assert IntegrationPlanLane.verify_receipt_attestation(second) is True

    def test_amendment_preserves_plan_identity(self) -> None:
        first = _receipt()
        second = _receipt(predecessor=first)
        assert second.plan_id == first.plan_id
        assert second.owner == first.owner
        assert second.issue_reference == first.issue_reference

    def test_amendment_must_have_reason(self) -> None:
        first = _receipt()
        with pytest.raises(IntegrationPlanContractError, match="amendment_reason"):
            IntegrationPlanLane.amend_receipt(
                first,
                acceptance_criteria=first.acceptance_criteria,
                allowed_mutation_surfaces=first.allowed_mutation_surfaces,
                phases=first.phases,
                next_step=first.next_step,
                amendment_reason="   ",
                recorded_at_iso="2026-08-03T22:30:00+00:00",
            )

    def test_tampered_next_step_breaks_attestation(self) -> None:
        receipt = _receipt()
        tampered = PlanReceipt(
            plan_id=receipt.plan_id,
            schema_version=receipt.schema_version,
            plan_schema_version=receipt.plan_schema_version,
            owner=receipt.owner,
            repo_owner=receipt.repo_owner,
            repo_name=receipt.repo_name,
            workspace_id=receipt.workspace_id,
            base_revision=receipt.base_revision,
            issue_reference=receipt.issue_reference,
            pr_reference=receipt.pr_reference,
            acceptance_criteria=receipt.acceptance_criteria,
            allowed_mutation_surfaces=receipt.allowed_mutation_surfaces,
            phases=receipt.phases,
            next_step="Hacked next step",
            attestation_sha256=receipt.attestation_sha256,
            predecessor_attestation_sha256=receipt.predecessor_attestation_sha256,
            amendment_reason=receipt.amendment_reason,
            recorded_at_iso=receipt.recorded_at_iso,
            plan_content_sha256=receipt.plan_content_sha256,
        )
        assert IntegrationPlanLane.verify_receipt_attestation(tampered) is False

    def test_tampered_base_revision_breaks_attestation(self) -> None:
        receipt = _receipt()
        tampered = PlanReceipt(
            plan_id=receipt.plan_id,
            schema_version=receipt.schema_version,
            plan_schema_version=receipt.plan_schema_version,
            owner=receipt.owner,
            repo_owner=receipt.repo_owner,
            repo_name=receipt.repo_name,
            workspace_id=receipt.workspace_id,
            base_revision=_GOOD_SHA3,  # changed
            issue_reference=receipt.issue_reference,
            pr_reference=receipt.pr_reference,
            acceptance_criteria=receipt.acceptance_criteria,
            allowed_mutation_surfaces=receipt.allowed_mutation_surfaces,
            phases=receipt.phases,
            next_step=receipt.next_step,
            attestation_sha256=receipt.attestation_sha256,
            predecessor_attestation_sha256=receipt.predecessor_attestation_sha256,
            amendment_reason=receipt.amendment_reason,
            recorded_at_iso=receipt.recorded_at_iso,
            plan_content_sha256=receipt.plan_content_sha256,
        )
        assert IntegrationPlanLane.verify_receipt_attestation(tampered) is False

    def test_create_receipt_rejects_short_revision(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="base_revision"):
            _receipt(base_revision="not-a-sha")

    def test_create_receipt_rejects_secret_in_owner(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="secret"):
            IntegrationPlanLane.create_receipt(
                plan_id="issue-1112",
                plan_schema_version="1",
                owner="bearer abcdefghijklmnop",
                repo_owner=_OWNER,
                repo_name=_REPO,
                workspace_id="ws-1112",
                base_revision=_GOOD_SHA,
                issue_reference="1112",
                acceptance_criteria=("ok",),
                allowed_mutation_surfaces=("ok",),
                phases=(_phase(),),
                next_step="ok",
                recorded_at_iso="2026-08-03T22:00:00+00:00",
            )


# ===========================================================================
# Plan amendment: rejection of scope, merge-right, deployment and acceptance
# ===========================================================================
class TestAmendmentGuards:
    def test_amendment_cannot_change_repo_identity(self) -> None:
        first = _receipt()
        # The amend API does not accept owner/repo/etc, but lets prove that
        # producing a receipt with a different repo_owner through a manual
        # construction with the same attestation fails verification.
        tampered = PlanReceipt(
            plan_id=first.plan_id,
            schema_version=first.schema_version,
            plan_schema_version=first.plan_schema_version,
            owner=first.owner,
            repo_owner="OtherOwner",
            repo_name=first.repo_name,
            workspace_id=first.workspace_id,
            base_revision=first.base_revision,
            issue_reference=first.issue_reference,
            pr_reference=first.pr_reference,
            acceptance_criteria=first.acceptance_criteria,
            allowed_mutation_surfaces=first.allowed_mutation_surfaces,
            phases=first.phases,
            next_step=first.next_step,
            attestation_sha256=first.attestation_sha256,
            predecessor_attestation_sha256=first.predecessor_attestation_sha256,
            amendment_reason=first.amendment_reason,
            recorded_at_iso=first.recorded_at_iso,
            plan_content_sha256=first.plan_content_sha256,
        )
        assert IntegrationPlanLane.verify_receipt_attestation(tampered) is False

    def test_receipt_round_trip_through_dict_is_stable(self) -> None:
        first = _receipt()
        round = json.dumps(first.to_dict(), sort_keys=True)
        again = json.loads(round)
        assert again["attestationSha256"] == first.attestation_sha256
        assert again["baseRevision"] == first.base_revision
        assert again["planId"] == first.plan_id
        assert again["phases"][0]["phaseId"] == "design"


# ===========================================================================
# Evidence records
# ===========================================================================
class TestEvidenceRecords:
    def test_create_verified_evidence_requires_redacted(self) -> None:
        # Manually trying to construct an unredacted+verified record fails.
        with pytest.raises(IntegrationPlanContractError, match="redacted"):
            EvidenceRecord(
                evidence_id="ev-1",
                schema_version=EVIDENCE_SCHEMA_VERSION,
                phase_id="design",
                kind=EVIDENCE_KIND_REPO_REVISION,
                source=_GOOD_SHA,
                content_sha256=_GOOD_SHA64,
                received_at_iso="2026-08-03T22:01:00+00:00",
                redacted=False,
                is_verified=True,
            )

    def test_unverified_evidence_does_not_promote_phase(self) -> None:
        receipt = _receipt()
        unverified = _evidence(is_verified=False)
        assert IntegrationPlanLane.evaluate_phase(receipt.phases[0], [unverified]) is PhaseStatus.PENDING

    def test_verified_evidence_with_required_kind_promotes_phase(self) -> None:
        phase = _phase(
            required_kinds=(EVIDENCE_KIND_REPO_REVISION, EVIDENCE_KIND_CI_WORKFLOW),
            status=PhaseStatus.IN_PROGRESS,
        )
        receipt = _receipt(phases=(phase,))
        records = [
            _evidence(kind=EVIDENCE_KIND_REPO_REVISION, source=_GOOD_SHA, content_sha256=_GOOD_SHA64),
            _evidence(
                evidence_id="ev-2",
                kind=EVIDENCE_KIND_CI_WORKFLOW,
                source="ci.yml",
                content_sha256=_GOOD_SHA64_B,
            ),
        ]
        assert IntegrationPlanLane.evaluate_phase(phase, records) is PhaseStatus.VERIFIED

    def test_missing_required_kind_keeps_phase_blocked(self) -> None:
        phase = _phase(
            required_kinds=(EVIDENCE_KIND_REPO_REVISION, EVIDENCE_KIND_RUNTIME_READBACK),
            status=PhaseStatus.IN_PROGRESS,
        )
        receipt = _receipt(phases=(phase,))
        only_repo = [_evidence()]
        assert IntegrationPlanLane.evaluate_phase(phase, only_repo) is PhaseStatus.BLOCKED

    def test_markdown_only_evidence_never_promotes_phase(self) -> None:
        # Even with an is_verified record, if the kind does not match a
        # required kind, the phase must NOT move to verified.
        phase = _phase(
            required_kinds=(EVIDENCE_KIND_REPO_REVISION,),
            status=PhaseStatus.IN_PROGRESS,
        )
        wrong_kind = _evidence(
            evidence_id="ev-wrong",
            kind=EVIDENCE_KIND_LEDGER_HEAD,
            source="entry-abc",
        )
        assert IntegrationPlanLane.evaluate_phase(phase, [wrong_kind]) is PhaseStatus.BLOCKED

    def test_evaluator_ignores_records_for_other_phases(self) -> None:
        phase = _phase(required_kinds=(EVIDENCE_KIND_REPO_REVISION,), status=PhaseStatus.IN_PROGRESS)
        other = _evidence(phase_id="other", kind=EVIDENCE_KIND_REPO_REVISION)
        assert IntegrationPlanLane.evaluate_phase(phase, [other]) is PhaseStatus.BLOCKED

    def test_evidence_with_wrong_kind_source_fails_construction(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="binding"):
            _evidence(kind=EVIDENCE_KIND_ARTIFACT_DIGEST, source="not-a-digest")

    def test_invalid_evidence_kind_rejected(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="kind"):
            IntegrationPlanLane.create_evidence_record(
                evidence_id="ev-x",
                phase_id="design",
                kind="unknown_kind",
                source="x",
                content_sha256=_GOOD_SHA64,
                received_at_iso="2026-08-03T22:01:00+00:00",
            )

    def test_invalid_content_sha_rejected(self) -> None:
        with pytest.raises(IntegrationPlanContractError, match="content_sha256"):
            IntegrationPlanLane.create_evidence_record(
                evidence_id="ev-x",
                phase_id="design",
                kind=EVIDENCE_KIND_REPO_REVISION,
                source=_GOOD_SHA,
                content_sha256="not-a-sha",
                received_at_iso="2026-08-03T22:01:00+00:00",
            )

    def test_invalidation_record_overrides_verified(self) -> None:
        phase = _phase(
            required_kinds=(EVIDENCE_KIND_REPO_REVISION, EVIDENCE_KIND_CI_WORKFLOW),
            status=PhaseStatus.IN_PROGRESS,
        )
        records = [
            _evidence(kind=EVIDENCE_KIND_REPO_REVISION, source=_GOOD_SHA),
            _evidence(evidence_id="ev-2", kind=EVIDENCE_KIND_CI_WORKFLOW, source="ci.yml", content_sha256=_GOOD_SHA64_B),
            _evidence(
                evidence_id="ev-3:invalidated",
                phase_id=phase.phase_id,
                kind=EVIDENCE_KIND_LEDGER_HEAD,
                source="entry-supersede",
                content_sha256=_GOOD_SHA64_B,
            ),
        ]
        assert IntegrationPlanLane.evaluate_phase(phase, records) is PhaseStatus.INVALIDATED


class TestEvaluateAll:
    def test_returns_one_status_per_phase(self) -> None:
        phase_pending = _phase("p-pending")
        phase_blocked = _phase(
            "p-blocked",
            required_kinds=(EVIDENCE_KIND_RUNTIME_READBACK,),
            status=PhaseStatus.IN_PROGRESS,
        )
        phase_verified = _phase(
            "p-verified",
            required_kinds=(EVIDENCE_KIND_REPO_REVISION,),
            status=PhaseStatus.IN_PROGRESS,
        )
        receipt = _receipt(phases=(phase_pending, phase_blocked, phase_verified))
        verified_record = _evidence(phase_id="p-verified")
        status_map = IntegrationPlanLane.evaluate_all(receipt, [verified_record])
        assert status_map == {
            "p-pending": PhaseStatus.PENDING.value,
            "p-blocked": PhaseStatus.BLOCKED.value,
            "p-verified": PhaseStatus.VERIFIED.value,
        }


# ===========================================================================
# RedactionFilter
# ===========================================================================
class TestRedactionFilter:
    def test_bearer_rejected(self) -> None:
        assert RedactionFilter.contains_secret("Authorization: Bearer abcdefghijklmnop")

    def test_github_token_rejected(self) -> None:
        assert RedactionFilter.contains_secret("token ghp_abcdefghijklmnopqrstuvwxyz0123456789AB")

    def test_aws_key_rejected(self) -> None:
        assert RedactionFilter.contains_secret("AKIAIOSFODNN7EXAMPLE")

    def test_pem_block_rejected(self) -> None:
        assert RedactionFilter.contains_secret("-----BEGIN RSA PRIVATE KEY-----")

    def test_password_kv_rejected(self) -> None:
        assert RedactionFilter.contains_secret("password=hunter2hunter")

    def test_postgres_dsn_rejected(self) -> None:
        assert RedactionFilter.contains_secret("postgres://u:pw@host/db")

    def test_jwt_rejected(self) -> None:
        assert RedactionFilter.contains_secret(
            "eyJabcdefghijk.lmnopqrstuvwxyz1234.zyxwabcdefghijklmnopqr"
        )

    def test_clean_text_passes(self) -> None:
        assert RedactionFilter.contains_secret("clean evidence text with sha=abcd1234") is False


# ===========================================================================
# No I/O in module (structural check)
# ===========================================================================
class TestNoIOInModule:
    def test_module_has_no_open_calls(self) -> None:
        import agent_runtime.integration_plan_lane as mod
        src = inspect.getsource(mod)
        assert "open(" not in src

    def test_module_has_no_socket_or_requests(self) -> None:
        import agent_runtime.integration_plan_lane as mod
        src = inspect.getsource(mod)
        assert "import socket" not in src
        assert "import requests" not in src
        assert "import urllib.request" not in src
        assert "import aiohttp" not in src

    def test_module_has_no_time_or_datetime(self) -> None:
        import agent_runtime.integration_plan_lane as mod
        src = inspect.getsource(mod)
        assert "import time" not in src
        assert "import datetime" not in src

    def test_module_has_no_psycopg2(self) -> None:
        import agent_runtime.integration_plan_lane as mod
        src = inspect.getsource(mod)
        assert "psycopg2" not in src


# ===========================================================================
# Schema versions
# ===========================================================================
class TestSchemaVersions:
    def test_receipt_schema_version_is_stable(self) -> None:
        assert SCHEMA_VERSION == "sovereign.integration-plan-lane.v1"

    def test_evidence_schema_version_is_stable(self) -> None:
        assert EVIDENCE_SCHEMA_VERSION == "sovereign.integration-plan-evidence.v1"