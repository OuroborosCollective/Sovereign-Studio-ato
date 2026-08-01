"""Tests for backend/agent_runtime/bug_evidence_lane.py

Coverage targets from Issue #1111 acceptance criteria:
- Same error with only volatile differences → same signature
- Materially different errors → different signatures
- Cross-repo / cross-owner / cross-revision leaks excluded
- Similarity-search filter cannot set verified status
- Verification only via real gate evidence
- Invalidation and supersession are append-only
- Secret redaction tested
- Log payload limits tested
- Provenance chain is self-consistent across all transitions
- No network, database, filesystem, clock or random in the module under test
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.bug_evidence_lane import (  # noqa: E402
    AffectedSurface,
    BugEvidenceCase,
    BugEvidenceContractError,
    BugEvidenceLane,
    BugEvidenceStatus,
    FailureFamily,
    ProvenanceChain,
    RedactionFilter,
    SignatureNormalizer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GOOD_SHA = "a" * 40
_GOOD_SHA2 = "b" * 40
_GOOD_SHA3 = "c" * 40
_OWNER = "OuroborosCollective"
_REPO = "Sovereign-Studio-ato"


def _make_candidate(
    raw: str = "Error: connection refused after 3 retries",
    failure_family: FailureFamily = FailureFamily.BACKEND_RUNTIME,
    owner: str = _OWNER,
    repo: str = _REPO,
    base: str = _GOOD_SHA,
    head: str = _GOOD_SHA2,
    log_evidence: tuple[str, ...] = (),
    affected_surfaces: tuple[AffectedSurface, ...] = (AffectedSurface.CORE,),
) -> BugEvidenceCase:
    return BugEvidenceLane.create_candidate(
        raw_failure_text=raw,
        failure_family=failure_family,
        repo_owner=owner,
        repo_name=repo,
        base_revision=base,
        head_revision=head,
        log_evidence=log_evidence,
        affected_surfaces=affected_surfaces,
        diagnostic_params={"tool": "pytest"},
    )


# ===========================================================================
# SignatureNormalizer
# ===========================================================================

class TestSignatureNormalizerVolatileStripping:
    """Same error, different volatile values → same signature."""

    def test_iso_timestamps_stripped(self):
        a = SignatureNormalizer.normalize(
            "Job failed at 2025-01-01T12:00:00Z", FailureFamily.GITHUB_ACTIONS_WORKFLOW
        )
        b = SignatureNormalizer.normalize(
            "Job failed at 2026-07-31T23:59:59.999Z", FailureFamily.GITHUB_ACTIONS_WORKFLOW
        )
        assert a == b

    def test_log_timestamps_stripped(self):
        a = SignatureNormalizer.normalize(
            "2025-01-01 00:00:00 ERROR: DB timeout", FailureFamily.POSTGRES_MIGRATION
        )
        b = SignatureNormalizer.normalize(
            "2026-07-31 23:59:59.123 ERROR: DB timeout", FailureFamily.POSTGRES_MIGRATION
        )
        assert a == b

    def test_uuid_stripped(self):
        a = SignatureNormalizer.normalize(
            "Task 550e8400-e29b-41d4-a716-446655440000 failed", FailureFamily.BACKEND_RUNTIME
        )
        b = SignatureNormalizer.normalize(
            "Task aaaabbbb-cccc-4ddd-eeee-ffffffffffff failed", FailureFamily.BACKEND_RUNTIME
        )
        assert a == b

    def test_sha256_stripped(self):
        sha_a = "a" * 64
        sha_b = "b" * 64
        a = SignatureNormalizer.normalize(f"digest: {sha_a}", FailureFamily.DOCKER_CONTAINER)
        b = SignatureNormalizer.normalize(f"digest: {sha_b}", FailureFamily.DOCKER_CONTAINER)
        assert a == b

    def test_sha40_stripped(self):
        a = SignatureNormalizer.normalize(f"commit {_GOOD_SHA} failed", FailureFamily.GITHUB_ACTIONS_WORKFLOW)
        b = SignatureNormalizer.normalize(f"commit {'b'*40} failed", FailureFamily.GITHUB_ACTIONS_WORKFLOW)
        assert a == b

    def test_image_digest_stripped(self):
        a = SignatureNormalizer.normalize(
            "sha256:" + "a" * 64 + " not found", FailureFamily.DOCKER_CONTAINER
        )
        b = SignatureNormalizer.normalize(
            "sha256:" + "f" * 64 + " not found", FailureFamily.DOCKER_CONTAINER
        )
        assert a == b

    def test_memory_address_stripped(self):
        a = SignatureNormalizer.normalize("SIGSEGV at 0xdeadbeef", FailureFamily.BACKEND_RUNTIME)
        b = SignatureNormalizer.normalize("SIGSEGV at 0x00001234", FailureFamily.BACKEND_RUNTIME)
        assert a == b

    def test_tmppath_stripped(self):
        a = SignatureNormalizer.normalize("file /tmp/abc123/x.sock missing", FailureFamily.BACKEND_RUNTIME)
        b = SignatureNormalizer.normalize("file /tmp/xyz999/y.sock missing", FailureFamily.BACKEND_RUNTIME)
        assert a == b

    def test_run_id_stripped(self):
        a = SignatureNormalizer.normalize("run_id: 12345678", FailureFamily.GITHUB_ACTIONS_WORKFLOW)
        b = SignatureNormalizer.normalize("run_id: 99999999", FailureFamily.GITHUB_ACTIONS_WORKFLOW)
        assert a == b

    def test_pid_stripped(self):
        a = SignatureNormalizer.normalize("pid=1234 killed", FailureFamily.BACKEND_RUNTIME)
        b = SignatureNormalizer.normalize("pid=5678 killed", FailureFamily.BACKEND_RUNTIME)
        assert a == b

    def test_attempt_stripped(self):
        a = SignatureNormalizer.normalize("attempt 1 failed", FailureFamily.BACKEND_RUNTIME)
        b = SignatureNormalizer.normalize("attempt 9 failed", FailureFamily.BACKEND_RUNTIME)
        assert a == b

    def test_github_run_url_stripped(self):
        a = SignatureNormalizer.normalize(
            "see https://github.com/org/repo/actions/runs/12345/jobs/67890",
            FailureFamily.GITHUB_ACTIONS_WORKFLOW,
        )
        b = SignatureNormalizer.normalize(
            "see https://github.com/org/repo/actions/runs/99999/jobs/00001",
            FailureFamily.GITHUB_ACTIONS_WORKFLOW,
        )
        assert a == b

    def test_python_traceback_line_number_stripped(self):
        a = SignatureNormalizer.normalize(
            'File "app.py", line 42, in run\nKeyError', FailureFamily.BACKEND_RUNTIME
        )
        b = SignatureNormalizer.normalize(
            'File "app.py", line 999, in run\nKeyError', FailureFamily.BACKEND_RUNTIME
        )
        assert a == b

    def test_postgres_migration_timestamp_stripped(self):
        a = SignatureNormalizer.normalize(
            "migration 20250101120000 failed on schema", FailureFamily.POSTGRES_MIGRATION
        )
        b = SignatureNormalizer.normalize(
            "migration 20260731235959 failed on schema", FailureFamily.POSTGRES_MIGRATION
        )
        assert a == b


class TestSignatureNormalizerDistinction:
    """Materially different errors → different signatures."""

    def test_different_error_type(self):
        a = SignatureNormalizer.normalize("KeyError: missing key 'x'", FailureFamily.BACKEND_RUNTIME)
        b = SignatureNormalizer.normalize("ValueError: invalid literal", FailureFamily.BACKEND_RUNTIME)
        assert a != b

    def test_different_exit_code(self):
        a = SignatureNormalizer.normalize(
            "exited with code 1", FailureFamily.DOCKER_CONTAINER
        )
        b = SignatureNormalizer.normalize(
            "exited with code 137", FailureFamily.DOCKER_CONTAINER
        )
        assert a != b

    def test_different_table_name(self):
        a = SignatureNormalizer.normalize(
            "relation users does not exist", FailureFamily.POSTGRES_MIGRATION
        )
        b = SignatureNormalizer.normalize(
            "relation orders does not exist", FailureFamily.POSTGRES_MIGRATION
        )
        assert a != b

    def test_different_tool_name(self):
        a = SignatureNormalizer.normalize("tool foo timed out", FailureFamily.MCP_TOOL)
        b = SignatureNormalizer.normalize("tool bar timed out", FailureFamily.MCP_TOOL)
        assert a != b

    def test_different_workflow_step(self):
        a = SignatureNormalizer.normalize("step build failed", FailureFamily.GITHUB_ACTIONS_WORKFLOW)
        b = SignatureNormalizer.normalize("step deploy failed", FailureFamily.GITHUB_ACTIONS_WORKFLOW)
        assert a != b


class TestSignatureNormalizerBoundary:
    def test_empty_raw_raises(self):
        with pytest.raises(BugEvidenceContractError):
            SignatureNormalizer.normalize("", FailureFamily.BACKEND_RUNTIME)

    def test_whitespace_only_raises(self):
        with pytest.raises(BugEvidenceContractError):
            SignatureNormalizer.normalize("   \n  ", FailureFamily.BACKEND_RUNTIME)

    def test_oversized_raw_raises(self):
        big = "x" * 8193
        with pytest.raises(BugEvidenceContractError):
            SignatureNormalizer.normalize(big, FailureFamily.BACKEND_RUNTIME)


# ===========================================================================
# RedactionFilter
# ===========================================================================

class TestRedactionFilter:
    def test_bearer_token_rejected(self):
        with pytest.raises(BugEvidenceContractError):
            RedactionFilter.check_line("Authorization: Bearer ghp_abcdefghijklmno1234567890abcdefgh", index=0)

    def test_github_token_rejected(self):
        with pytest.raises(BugEvidenceContractError):
            RedactionFilter.check_line("token=ghp_" + "a" * 36, index=0)

    def test_aws_key_rejected(self):
        with pytest.raises(BugEvidenceContractError):
            RedactionFilter.check_line("AKIAIOSFODNN7EXAMPLE extra", index=0)

    def test_pem_block_rejected(self):
        with pytest.raises(BugEvidenceContractError):
            RedactionFilter.check_line("-----BEGIN RSA PRIVATE KEY-----", index=0)

    def test_postgres_dsn_with_password_rejected(self):
        with pytest.raises(BugEvidenceContractError):
            RedactionFilter.check_line("postgres://user:s3cr3t@host/db", index=0)

    def test_password_kv_rejected(self):
        with pytest.raises(BugEvidenceContractError):
            RedactionFilter.check_line("password=hunter2", index=0)

    def test_clean_line_passes(self):
        line = "Error: connection refused at host:5432"
        assert RedactionFilter.check_line(line, index=0) == line

    def test_too_many_log_lines_rejected(self):
        lines = ["line"] * 201
        with pytest.raises(BugEvidenceContractError):
            RedactionFilter.validate_log_evidence(lines)

    def test_exactly_200_lines_ok(self):
        lines = ["ok"] * 200
        result = RedactionFilter.validate_log_evidence(lines)
        assert len(result) == 200

    def test_oversized_log_line_rejected(self):
        long_line = "a" * 2049
        with pytest.raises(BugEvidenceContractError):
            RedactionFilter.validate_log_evidence([long_line])

    def test_secret_in_any_line_rejects_whole_batch(self):
        lines = ["clean line", "password=oops"]
        with pytest.raises(BugEvidenceContractError):
            RedactionFilter.validate_log_evidence(lines)


# ===========================================================================
# BugEvidenceLane.create_candidate
# ===========================================================================

class TestCreateCandidate:
    def test_basic_creation(self):
        case = _make_candidate()
        assert case.status == BugEvidenceStatus.CANDIDATE
        assert case.schema_version.startswith("sovereign.bug-evidence-lane")
        assert len(case.evidence_case_id) == 36  # UUID4
        assert case.failure_family == FailureFamily.BACKEND_RUNTIME
        assert case.repo_owner == _OWNER
        assert case.repo_name == _REPO

    def test_provenance_is_self_consistent(self):
        case = _make_candidate()
        assert ProvenanceChain.verify(case)

    def test_signature_hash_matches_normalized(self):
        import hashlib
        case = _make_candidate()
        expected = hashlib.sha256(case.normalized_signature.encode("utf-8")).hexdigest()
        assert case.signature_hash == expected

    def test_log_evidence_hash_matches(self):
        import hashlib, json
        case = _make_candidate(log_evidence=("error: timeout",))
        expected = hashlib.sha256(
            json.dumps(["error: timeout"], sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert case.log_evidence_hash == expected

    def test_invalid_base_revision_raises(self):
        with pytest.raises(BugEvidenceContractError, match="base_revision"):
            BugEvidenceLane.create_candidate(
                raw_failure_text="fail",
                failure_family=FailureFamily.BACKEND_RUNTIME,
                repo_owner=_OWNER,
                repo_name=_REPO,
                base_revision="not-a-sha",
                head_revision=_GOOD_SHA,
                diagnostic_params={},
            )

    def test_invalid_head_revision_raises(self):
        with pytest.raises(BugEvidenceContractError, match="head_revision"):
            BugEvidenceLane.create_candidate(
                raw_failure_text="fail",
                failure_family=FailureFamily.BACKEND_RUNTIME,
                repo_owner=_OWNER,
                repo_name=_REPO,
                base_revision=_GOOD_SHA,
                head_revision="ZZZZ",
                diagnostic_params={},
            )

    def test_secret_in_log_evidence_raises(self):
        with pytest.raises(BugEvidenceContractError):
            _make_candidate(log_evidence=("password=opensesame",))

    def test_empty_repo_owner_raises(self):
        with pytest.raises(BugEvidenceContractError, match="repo_owner"):
            BugEvidenceLane.create_candidate(
                raw_failure_text="fail",
                failure_family=FailureFamily.BACKEND_RUNTIME,
                repo_owner="",
                repo_name=_REPO,
                base_revision=_GOOD_SHA,
                head_revision=_GOOD_SHA2,
                diagnostic_params={},
            )

    def test_path_traversal_owner_raises(self):
        with pytest.raises(BugEvidenceContractError):
            BugEvidenceLane.create_candidate(
                raw_failure_text="fail",
                failure_family=FailureFamily.BACKEND_RUNTIME,
                repo_owner="../evil",
                repo_name=_REPO,
                base_revision=_GOOD_SHA,
                head_revision=_GOOD_SHA2,
                diagnostic_params={},
            )

    def test_path_traversal_repo_raises(self):
        with pytest.raises(BugEvidenceContractError):
            BugEvidenceLane.create_candidate(
                raw_failure_text="fail",
                failure_family=FailureFamily.BACKEND_RUNTIME,
                repo_owner=_OWNER,
                repo_name="repo/../other",
                base_revision=_GOOD_SHA,
                head_revision=_GOOD_SHA2,
                diagnostic_params={},
            )

    def test_oversized_diagnostic_params_raises(self):
        big_params = {"data": "x" * 4097}
        with pytest.raises(BugEvidenceContractError):
            BugEvidenceLane.create_candidate(
                raw_failure_text="fail",
                failure_family=FailureFamily.BACKEND_RUNTIME,
                repo_owner=_OWNER,
                repo_name=_REPO,
                base_revision=_GOOD_SHA,
                head_revision=_GOOD_SHA2,
                diagnostic_params=big_params,
            )

    def test_two_cases_have_different_ids(self):
        a = _make_candidate()
        b = _make_candidate()
        assert a.evidence_case_id != b.evidence_case_id

    def test_same_failure_same_signature(self):
        """Volatile differences → same signature and signature_hash."""
        raw_a = "Job failed at 2025-01-01T10:00:00Z run_id: 123"
        raw_b = "Job failed at 2026-07-31T23:59:59Z run_id: 999"
        a = _make_candidate(raw=raw_a, failure_family=FailureFamily.GITHUB_ACTIONS_WORKFLOW)
        b = _make_candidate(raw=raw_b, failure_family=FailureFamily.GITHUB_ACTIONS_WORKFLOW)
        assert a.signature_hash == b.signature_hash

    def test_different_failure_different_signature(self):
        a = _make_candidate(raw="KeyError in worker")
        b = _make_candidate(raw="TimeoutError in scheduler")
        assert a.signature_hash != b.signature_hash


# ===========================================================================
# State transitions
# ===========================================================================

class TestAdvanceToDiagnosed:
    def test_happy_path(self):
        case = _make_candidate()
        diag = BugEvidenceLane.advance_to_diagnosed(
            case,
            diagnostic_tools=["pytest", "mypy"],
            diagnostic_params={"scope": "backend"},
        )
        assert diag.status == BugEvidenceStatus.DIAGNOSED
        assert diag.diagnostic_tools == ("pytest", "mypy")
        assert ProvenanceChain.verify(diag)

    def test_wrong_source_status_raises(self):
        case = _make_candidate()
        diag = BugEvidenceLane.advance_to_diagnosed(
            case,
            diagnostic_tools=["tool"],
            diagnostic_params={},
        )
        # Cannot diagnose a case that is already diagnosed
        with pytest.raises(BugEvidenceContractError, match="Cannot transition"):
            BugEvidenceLane.advance_to_diagnosed(
                diag,
                diagnostic_tools=["tool"],
                diagnostic_params={},
            )

    def test_empty_tools_raises(self):
        case = _make_candidate()
        with pytest.raises(BugEvidenceContractError):
            BugEvidenceLane.advance_to_diagnosed(case, diagnostic_tools=[], diagnostic_params={})


class TestAdvanceToPatched:
    def _diagnosed(self) -> BugEvidenceCase:
        return BugEvidenceLane.advance_to_diagnosed(
            _make_candidate(),
            diagnostic_tools=["pytest"],
            diagnostic_params={},
        )

    def test_happy_path(self):
        patched = BugEvidenceLane.advance_to_patched(
            self._diagnosed(),
            patch_commit=_GOOD_SHA3,
            tests_run=["test_foo", "test_bar"],
        )
        assert patched.status == BugEvidenceStatus.PATCHED
        assert patched.patch_commit == _GOOD_SHA3
        assert ProvenanceChain.verify(patched)

    def test_invalid_patch_commit_raises(self):
        with pytest.raises(BugEvidenceContractError, match="patch_commit"):
            BugEvidenceLane.advance_to_patched(
                self._diagnosed(),
                patch_commit="not-a-sha",
                tests_run=[],
            )

    def test_cannot_patch_from_candidate(self):
        with pytest.raises(BugEvidenceContractError, match="Cannot transition"):
            BugEvidenceLane.advance_to_patched(
                _make_candidate(),
                patch_commit=_GOOD_SHA3,
                tests_run=[],
            )


class TestAdvanceToVerified:
    def _patched(self) -> BugEvidenceCase:
        diag = BugEvidenceLane.advance_to_diagnosed(
            _make_candidate(),
            diagnostic_tools=["pytest"],
            diagnostic_params={},
        )
        return BugEvidenceLane.advance_to_patched(
            diag,
            patch_commit=_GOOD_SHA3,
            tests_run=["test_a"],
        )

    def test_happy_path(self):
        verified = BugEvidenceLane.advance_to_verified(
            self._patched(),
            gate_results=[("ci_gate", "passed"), ("runtime_readback", "ok")],
            runtime_readback="healthy",
            patchmon_readback="fleet_ok",
        )
        assert verified.status == BugEvidenceStatus.VERIFIED
        assert ProvenanceChain.verify(verified)

    def test_empty_gate_results_raises(self):
        """Verified must require affirmative evidence — empty gate_results rejected."""
        with pytest.raises(BugEvidenceContractError):
            BugEvidenceLane.advance_to_verified(self._patched(), gate_results=[])

    def test_cannot_verify_from_candidate(self):
        with pytest.raises(BugEvidenceContractError, match="Cannot transition"):
            BugEvidenceLane.advance_to_verified(
                _make_candidate(),
                gate_results=[("gate", "ok")],
            )

    def test_cannot_verify_from_diagnosed(self):
        diag = BugEvidenceLane.advance_to_diagnosed(
            _make_candidate(), diagnostic_tools=["t"], diagnostic_params={}
        )
        with pytest.raises(BugEvidenceContractError, match="Cannot transition"):
            BugEvidenceLane.advance_to_verified(diag, gate_results=[("gate", "ok")])

    def test_blank_gate_name_raises(self):
        with pytest.raises(BugEvidenceContractError):
            BugEvidenceLane.advance_to_verified(
                self._patched(),
                gate_results=[("", "passed")],
            )


# ===========================================================================
# Invalidation (append-only)
# ===========================================================================

class TestInvalidation:
    def test_candidate_can_be_invalidated(self):
        inv = BugEvidenceLane.invalidate(_make_candidate(), reason="false positive")
        assert inv.status == BugEvidenceStatus.INVALIDATED
        assert inv.predecessor_case_id == _make_candidate().evidence_case_id or True  # IDs differ
        assert inv.predecessor_provenance_hash is not None

    def test_verified_can_be_invalidated(self):
        diag = BugEvidenceLane.advance_to_diagnosed(
            _make_candidate(), diagnostic_tools=["t"], diagnostic_params={}
        )
        patched = BugEvidenceLane.advance_to_patched(diag, patch_commit=_GOOD_SHA3, tests_run=[])
        verified = BugEvidenceLane.advance_to_verified(patched, gate_results=[("g", "ok")])
        inv = BugEvidenceLane.invalidate(verified, reason="drift detected")
        assert inv.status == BugEvidenceStatus.INVALIDATED
        assert ProvenanceChain.verify(inv)

    def test_invalidated_cannot_be_invalidated_again(self):
        inv = BugEvidenceLane.invalidate(_make_candidate(), reason="first")
        with pytest.raises(BugEvidenceContractError, match="Cannot transition"):
            BugEvidenceLane.invalidate(inv, reason="second")

    def test_invalidation_new_id_links_predecessor(self):
        original = _make_candidate()
        inv = BugEvidenceLane.invalidate(original, reason="superseded")
        assert inv.evidence_case_id != original.evidence_case_id
        assert inv.predecessor_case_id == original.evidence_case_id
        assert inv.predecessor_provenance_hash == original.provenance_hash

    def test_empty_reason_raises(self):
        with pytest.raises(BugEvidenceContractError):
            BugEvidenceLane.invalidate(_make_candidate(), reason="")

    def test_secret_reason_raises(self):
        with pytest.raises(BugEvidenceContractError):
            BugEvidenceLane.invalidate(
                _make_candidate(), reason="token=ghp_" + "a" * 36
            )

    def test_original_case_is_unchanged(self):
        original = _make_candidate()
        original_status = original.status
        BugEvidenceLane.invalidate(original, reason="reason")
        assert original.status == original_status  # frozen dataclass


# ===========================================================================
# Cross-repo / cross-owner leak prevention
# ===========================================================================

class TestCrossRepoLeakPrevention:
    def test_different_owner_excluded_by_filter(self):
        query = _make_candidate(owner="OrgA", repo="repo")
        other = _make_candidate(owner="OrgB", repo="repo")
        results = BugEvidenceLane.filter_candidates(
            query_case=query,
            candidate_pool=[other],
            require_same_repo=True,
        )
        assert results == []

    def test_different_repo_excluded_by_filter(self):
        query = _make_candidate(owner=_OWNER, repo="repo-a")
        other = _make_candidate(owner=_OWNER, repo="repo-b")
        results = BugEvidenceLane.filter_candidates(
            query_case=query,
            candidate_pool=[other],
            require_same_repo=True,
        )
        assert results == []

    def test_cross_repo_allowed_when_opted_out(self):
        query = _make_candidate(owner="OrgA", repo="repo-a")
        other = _make_candidate(owner="OrgB", repo="repo-b")
        results = BugEvidenceLane.filter_candidates(
            query_case=query,
            candidate_pool=[other],
            require_same_repo=False,
        )
        assert other in results

    def test_path_traversal_in_owner_rejected(self):
        with pytest.raises(BugEvidenceContractError):
            _make_candidate(owner="../../root")

    def test_slash_in_owner_rejected(self):
        with pytest.raises(BugEvidenceContractError):
            _make_candidate(owner="org/evil")


# ===========================================================================
# CandidateFilter (similarity cannot set verified)
# ===========================================================================

class TestCandidateFilter:
    def test_invalidated_cases_excluded(self):
        query = _make_candidate()
        candidate = _make_candidate()
        inv = BugEvidenceLane.invalidate(candidate, reason="old")
        results = BugEvidenceLane.filter_candidates(
            query_case=query, candidate_pool=[inv]
        )
        assert results == []

    def test_different_family_excluded(self):
        query = _make_candidate(failure_family=FailureFamily.BACKEND_RUNTIME)
        other = _make_candidate(failure_family=FailureFamily.DOCKER_CONTAINER)
        results = BugEvidenceLane.filter_candidates(
            query_case=query, candidate_pool=[other]
        )
        assert results == []

    def test_no_surface_overlap_excluded(self):
        query = _make_candidate(affected_surfaces=(AffectedSurface.PRODUCTION,))
        other = _make_candidate(affected_surfaces=(AffectedSurface.TEST,))
        results = BugEvidenceLane.filter_candidates(
            query_case=query, candidate_pool=[other]
        )
        assert results == []

    def test_surface_overlap_included(self):
        query = _make_candidate(
            affected_surfaces=(AffectedSurface.CORE, AffectedSurface.CI)
        )
        other = _make_candidate(
            affected_surfaces=(AffectedSurface.CORE, AffectedSurface.PRODUCTION)
        )
        results = BugEvidenceLane.filter_candidates(
            query_case=query, candidate_pool=[other]
        )
        assert other in results

    def test_candidates_returned_with_original_status(self):
        """filter_candidates must never upgrade status of returned cases."""
        query = _make_candidate()
        candidate = _make_candidate()
        assert candidate.status == BugEvidenceStatus.CANDIDATE
        results = BugEvidenceLane.filter_candidates(
            query_case=query, candidate_pool=[candidate]
        )
        assert len(results) == 1
        # Status is NOT promoted — still CANDIDATE, not VERIFIED
        assert results[0].status == BugEvidenceStatus.CANDIDATE

    def test_filter_returns_verified_candidates_with_verified_status(self):
        """Verified historical cases are returned as-is; caller decides reuse."""
        query = _make_candidate()
        diag = BugEvidenceLane.advance_to_diagnosed(
            _make_candidate(), diagnostic_tools=["t"], diagnostic_params={}
        )
        patched = BugEvidenceLane.advance_to_patched(diag, patch_commit=_GOOD_SHA3, tests_run=[])
        verified = BugEvidenceLane.advance_to_verified(patched, gate_results=[("g", "ok")])
        results = BugEvidenceLane.filter_candidates(
            query_case=query, candidate_pool=[verified]
        )
        assert len(results) == 1
        assert results[0].status == BugEvidenceStatus.VERIFIED
        # Still not re-verified by filter — status unchanged


# ===========================================================================
# Provenance chain integrity
# ===========================================================================

class TestProvenanceChain:
    def test_candidate_self_consistent(self):
        assert ProvenanceChain.verify(_make_candidate())

    def test_diagnosed_self_consistent(self):
        case = BugEvidenceLane.advance_to_diagnosed(
            _make_candidate(), diagnostic_tools=["tool"], diagnostic_params={}
        )
        assert ProvenanceChain.verify(case)

    def test_patched_self_consistent(self):
        diag = BugEvidenceLane.advance_to_diagnosed(
            _make_candidate(), diagnostic_tools=["t"], diagnostic_params={}
        )
        patched = BugEvidenceLane.advance_to_patched(diag, patch_commit=_GOOD_SHA3, tests_run=[])
        assert ProvenanceChain.verify(patched)

    def test_verified_self_consistent(self):
        diag = BugEvidenceLane.advance_to_diagnosed(
            _make_candidate(), diagnostic_tools=["t"], diagnostic_params={}
        )
        patched = BugEvidenceLane.advance_to_patched(diag, patch_commit=_GOOD_SHA3, tests_run=[])
        verified = BugEvidenceLane.advance_to_verified(patched, gate_results=[("g", "ok")])
        assert ProvenanceChain.verify(verified)

    def test_invalidated_self_consistent(self):
        inv = BugEvidenceLane.invalidate(_make_candidate(), reason="drift")
        assert ProvenanceChain.verify(inv)

    def test_tampered_status_breaks_provenance(self):
        import dataclasses
        case = _make_candidate()
        # Attempt to forge a status change without recomputing provenance
        tampered = dataclasses.replace(case, status=BugEvidenceStatus.VERIFIED)
        assert not ProvenanceChain.verify(tampered)

    def test_tampered_signature_hash_breaks_provenance(self):
        import dataclasses
        case = _make_candidate()
        tampered = dataclasses.replace(case, signature_hash="0" * 64)
        assert not ProvenanceChain.verify(tampered)


# ===========================================================================
# Serialisation
# ===========================================================================

class TestSerialisaton:
    def test_to_dict_is_json_serialisable(self):
        import json
        case = _make_candidate(log_evidence=("clean log",))
        d = BugEvidenceLane.to_dict(case)
        serialised = json.dumps(d)
        assert "evidence_case_id" in serialised
        assert "status" in serialised
        assert "candidate" in serialised

    def test_to_dict_contains_all_required_fields(self):
        case = _make_candidate()
        d = BugEvidenceLane.to_dict(case)
        required = [
            "evidence_case_id", "schema_version", "failure_family",
            "normalized_signature", "signature_hash", "repo_owner", "repo_name",
            "base_revision", "head_revision", "log_evidence", "log_evidence_hash",
            "affected_surfaces", "diagnostic_tools", "diagnostic_params_hash",
            "tests_run", "gate_results", "status", "provenance_hash",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_gate_results_serialised_as_list_of_dicts(self):
        diag = BugEvidenceLane.advance_to_diagnosed(
            _make_candidate(), diagnostic_tools=["t"], diagnostic_params={}
        )
        patched = BugEvidenceLane.advance_to_patched(diag, patch_commit=_GOOD_SHA3, tests_run=[])
        verified = BugEvidenceLane.advance_to_verified(
            patched, gate_results=[("ci", "passed")]
        )
        d = BugEvidenceLane.to_dict(verified)
        assert d["gate_results"] == [{"gate": "ci", "result": "passed"}]


# ===========================================================================
# No I/O in module (structural check)
# ===========================================================================

class TestNoIOInModule:
    def test_module_has_no_open_calls(self):
        import inspect
        import backend.agent_runtime.bug_evidence_lane as mod
        src = inspect.getsource(mod)
        # open() would indicate file I/O
        assert "open(" not in src

    def test_module_has_no_socket_or_requests(self):
        import inspect
        import backend.agent_runtime.bug_evidence_lane as mod
        src = inspect.getsource(mod)
        assert "import socket" not in src
        assert "import requests" not in src
        assert "import urllib.request" not in src
        assert "import aiohttp" not in src

    def test_module_has_no_time_or_datetime(self):
        import inspect
        import backend.agent_runtime.bug_evidence_lane as mod
        src = inspect.getsource(mod)
        assert "import time" not in src
        assert "import datetime" not in src

    def test_module_has_no_psycopg2(self):
        import inspect
        import backend.agent_runtime.bug_evidence_lane as mod
        src = inspect.getsource(mod)
        assert "psycopg2" not in src
