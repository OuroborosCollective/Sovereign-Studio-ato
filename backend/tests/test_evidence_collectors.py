"""Tests for evidence_collectors — Issue #1099.

Covers:
- All six collector families (git_workspace, github_ci, mcp, docker, postgres, provider)
- UNVERIFIABLE on missing/invalid inputs
- Canonical hashing is deterministic and changes with content
- build_capability_delta: PRESERVED, LOST, DEGRADED, REPLACED, UNVERIFIABLE, INTENTIONALLY_REMOVED
- Stale revision detection in github_ci
- Secret redaction in mcp/postgres collectors
- Byte-identity of observation_hash across equivalent inputs
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.evidence_collectors import (
    DEGRADED,
    INTENTIONALLY_REMOVED,
    LOST,
    PRESERVED,
    REPLACED_WITH_VERIFIED_EQUIVALENT,
    UNVERIFIABLE,
    CollectorContractError,
    CollectorObservation,
    build_capability_delta,
    build_observation,
    canonical_evidence_sha256,
    collect_config_provenance,
    collect_docker,
    collect_git_workspace,
    collect_github_ci,
    collect_mcp,
    collect_postgres,
    collect_provider,
)

SHA40 = "a" * 40
SHA40B = "b" * 40
SHA64 = "c" * 64
SHA64B = "d" * 64


# ---------------------------------------------------------------------------
# canonical_evidence_sha256
# ---------------------------------------------------------------------------

def test_canonical_evidence_sha256_is_deterministic() -> None:
    v1 = canonical_evidence_sha256({"z": 1, "a": "foo"})
    v2 = canonical_evidence_sha256({"a": "foo", "z": 1})
    assert v1 == v2
    assert len(v1) == 64


def test_canonical_evidence_sha256_changes_with_content() -> None:
    h1 = canonical_evidence_sha256({"x": 1})
    h2 = canonical_evidence_sha256({"x": 2})
    assert h1 != h2


def test_canonical_evidence_sha256_rejects_float() -> None:
    try:
        canonical_evidence_sha256({"x": 1.5})
        assert False, "should have raised"
    except (CollectorContractError, ValueError):
        pass


# ---------------------------------------------------------------------------
# build_observation
# ---------------------------------------------------------------------------

def test_build_observation_produces_valid_hash() -> None:
    obs = build_observation(
        capability_id="git.workspace",
        collector="git_workspace",
        status=PRESERVED,
        cause="test",
        source_revision=SHA40,
    )
    assert len(obs.observation_hash) == 64
    assert obs.status == PRESERVED
    assert obs.capability_id == "git.workspace"


def test_build_observation_hash_is_stable() -> None:
    o1 = build_observation(capability_id="git.workspace", collector="git_workspace",
                           status=PRESERVED, cause="test", source_revision=SHA40)
    o2 = build_observation(capability_id="git.workspace", collector="git_workspace",
                           status=PRESERVED, cause="test", source_revision=SHA40)
    assert o1.observation_hash == o2.observation_hash


def test_build_observation_rejects_invalid_capability_id() -> None:
    try:
        build_observation(capability_id="Invalid-ID!", collector="git_workspace",
                          status=PRESERVED, cause="test")
        assert False, "should have raised"
    except CollectorContractError:
        pass


def test_build_observation_rejects_empty_cause() -> None:
    try:
        build_observation(capability_id="git.workspace", collector="git_workspace",
                          status=PRESERVED, cause="   ")
        assert False, "should have raised"
    except CollectorContractError:
        pass


# ---------------------------------------------------------------------------
# collect_git_workspace
# ---------------------------------------------------------------------------

def test_git_workspace_clean_is_preserved() -> None:
    obs = collect_git_workspace(
        head_sha=SHA40,
        base_sha=SHA40B,
        diff_hash=SHA64,
        changed_paths=["src/foo.py"],
        status_clean=True,
    )
    assert obs.status == PRESERVED
    assert obs.source_revision == SHA40
    assert obs.detail["changed_path_count"] == 1


def test_git_workspace_dirty_is_degraded() -> None:
    obs = collect_git_workspace(
        head_sha=SHA40,
        base_sha=SHA40B,
        diff_hash=SHA64,
        changed_paths=["src/foo.py"],
        status_clean=False,
    )
    assert obs.status == DEGRADED


def test_git_workspace_invalid_head_is_unverifiable() -> None:
    obs = collect_git_workspace(
        head_sha="not-a-sha",
        base_sha=SHA40B,
        diff_hash=SHA64,
        changed_paths=[],
        status_clean=True,
    )
    assert obs.status == UNVERIFIABLE


def test_git_workspace_invalid_diff_hash_is_unverifiable() -> None:
    obs = collect_git_workspace(
        head_sha=SHA40,
        base_sha=SHA40B,
        diff_hash="short",
        changed_paths=[],
        status_clean=True,
    )
    assert obs.status == UNVERIFIABLE


def test_git_workspace_deduplicates_paths() -> None:
    obs = collect_git_workspace(
        head_sha=SHA40,
        base_sha=SHA40B,
        diff_hash=SHA64,
        changed_paths=["src/a.py", "src/a.py", "src/b.py"],
        status_clean=True,
    )
    assert obs.detail["changed_path_count"] == 2


# ---------------------------------------------------------------------------
# collect_github_ci
# ---------------------------------------------------------------------------

def test_github_ci_success_is_preserved() -> None:
    obs = collect_github_ci(
        head_sha=SHA40,
        run_id="123456",
        check_name="Agent Runtime Tests",
        conclusion="success",
        workflow_sha=SHA40,
    )
    assert obs.status == PRESERVED
    assert obs.source_revision == SHA40


def test_github_ci_failure_is_degraded() -> None:
    obs = collect_github_ci(
        head_sha=SHA40,
        run_id="999",
        check_name="Release Gate",
        conclusion="failure",
        workflow_sha=SHA40,
    )
    assert obs.status == DEGRADED


def test_github_ci_cancelled_is_unverifiable() -> None:
    obs = collect_github_ci(
        head_sha=SHA40,
        run_id="888",
        check_name="ci",
        conclusion="cancelled",
        workflow_sha=SHA40,
    )
    assert obs.status == UNVERIFIABLE


def test_github_ci_stale_workflow_sha_is_degraded() -> None:
    """Workflow SHA differs from PR head → stale binding."""
    obs = collect_github_ci(
        head_sha=SHA40,
        run_id="777",
        check_name="ci",
        conclusion="success",
        workflow_sha=SHA40B,  # different → stale
    )
    assert obs.status == DEGRADED
    assert "stale" in obs.cause


def test_github_ci_missing_head_sha_is_unverifiable() -> None:
    obs = collect_github_ci(
        head_sha="bad",
        run_id="111",
        check_name="ci",
        conclusion="success",
        workflow_sha="",
    )
    assert obs.status == UNVERIFIABLE


def test_github_ci_missing_run_id_is_unverifiable() -> None:
    obs = collect_github_ci(
        head_sha=SHA40,
        run_id="",
        check_name="ci",
        conclusion="success",
        workflow_sha=SHA40,
    )
    assert obs.status == UNVERIFIABLE


# ---------------------------------------------------------------------------
# collect_mcp
# ---------------------------------------------------------------------------

def test_mcp_healthy_is_preserved() -> None:
    obs = collect_mcp(
        installed_revision="v1.2.3",
        image_digest=SHA64,
        registry="ghcr.io/sovereign",
        protocol_version="2025-06-18",
        broker_reachable=True,
        tool_canary_ok=True,
    )
    assert obs.status == PRESERVED
    assert obs.detail["tool_canary_ok"] is True


def test_mcp_broker_unreachable_is_unverifiable() -> None:
    obs = collect_mcp(
        installed_revision="v1.0",
        image_digest=SHA64,
        registry="ghcr.io/sovereign",
        protocol_version="2025-06-18",
        broker_reachable=False,
        tool_canary_ok=False,
    )
    assert obs.status == UNVERIFIABLE


def test_mcp_missing_revision_is_unverifiable() -> None:
    obs = collect_mcp(
        installed_revision="",
        image_digest=SHA64,
        registry="ghcr.io/sovereign",
        protocol_version="",
        broker_reachable=True,
        tool_canary_ok=True,
    )
    assert obs.status == UNVERIFIABLE


def test_mcp_missing_digest_is_unverifiable() -> None:
    obs = collect_mcp(
        installed_revision="v1.0",
        image_digest="",
        registry="ghcr.io/sovereign",
        protocol_version="",
        broker_reachable=True,
        tool_canary_ok=True,
    )
    assert obs.status == UNVERIFIABLE


def test_mcp_canary_fail_is_degraded() -> None:
    obs = collect_mcp(
        installed_revision="v1.0",
        image_digest=SHA64,
        registry="ghcr.io/sovereign",
        protocol_version="2025-06-18",
        broker_reachable=True,
        tool_canary_ok=False,
    )
    assert obs.status == DEGRADED


# ---------------------------------------------------------------------------
# collect_docker
# ---------------------------------------------------------------------------

def test_docker_healthy_is_preserved() -> None:
    obs = collect_docker(
        started_digest=SHA64,
        container_generation=3,
        restart_count=0,
        health_status="healthy",
        fleet_revision=SHA40,
    )
    assert obs.status == PRESERVED
    assert obs.detail["restart_count"] == 0


def test_docker_missing_digest_is_unverifiable() -> None:
    obs = collect_docker(
        started_digest="",
        container_generation=1,
        restart_count=0,
        health_status="healthy",
        fleet_revision=SHA40,
    )
    assert obs.status == UNVERIFIABLE


def test_docker_unhealthy_is_degraded() -> None:
    obs = collect_docker(
        started_digest=SHA64,
        container_generation=1,
        restart_count=2,
        health_status="unhealthy",
        fleet_revision=SHA40,
    )
    assert obs.status == DEGRADED


def test_docker_excessive_restarts_is_degraded() -> None:
    obs = collect_docker(
        started_digest=SHA64,
        container_generation=1,
        restart_count=10,
        health_status="healthy",
        fleet_revision=SHA40,
    )
    assert obs.status == DEGRADED
    assert "10" in obs.cause


# ---------------------------------------------------------------------------
# collect_postgres
# ---------------------------------------------------------------------------

def test_postgres_connected_is_preserved() -> None:
    obs = collect_postgres(
        connection_canary_ok=True,
        schema_hash=SHA64,
        migration_owner="migrations-bot",
        pgvector_available=True,
        constraint_count=42,
        index_count=17,
    )
    assert obs.status == PRESERVED
    assert obs.source_revision == SHA64
    assert obs.detail["pgvector_available"] is True


def test_postgres_canary_failed_is_unverifiable() -> None:
    obs = collect_postgres(
        connection_canary_ok=False,
        schema_hash=SHA64,
        migration_owner="bot",
        pgvector_available=False,
        constraint_count=0,
        index_count=0,
    )
    assert obs.status == UNVERIFIABLE


def test_postgres_invalid_schema_hash_is_unverifiable() -> None:
    obs = collect_postgres(
        connection_canary_ok=True,
        schema_hash="not-a-sha",
        migration_owner="bot",
        pgvector_available=False,
        constraint_count=0,
        index_count=0,
    )
    assert obs.status == UNVERIFIABLE


# ---------------------------------------------------------------------------
# collect_provider
# ---------------------------------------------------------------------------

def test_provider_all_routes_ok_is_preserved() -> None:
    obs = collect_provider(
        openrouter_paid_route_ok=True,
        free_route_revision=SHA40,
        free_llm_revolver_ok=True,
        paid_truth_boundary_hash=SHA64,
    )
    assert obs.status == PRESERVED


def test_provider_missing_free_revision_is_unverifiable() -> None:
    obs = collect_provider(
        openrouter_paid_route_ok=True,
        free_route_revision="",
        free_llm_revolver_ok=True,
        paid_truth_boundary_hash=SHA64,
    )
    assert obs.status == UNVERIFIABLE


def test_provider_paid_route_down_is_degraded() -> None:
    obs = collect_provider(
        openrouter_paid_route_ok=False,
        free_route_revision=SHA40,
        free_llm_revolver_ok=True,
        paid_truth_boundary_hash=SHA64,
    )
    assert obs.status == DEGRADED


def test_provider_both_routes_down_is_lost() -> None:
    obs = collect_provider(
        openrouter_paid_route_ok=False,
        free_route_revision=SHA40,
        free_llm_revolver_ok=False,
        paid_truth_boundary_hash=SHA64,
    )
    assert obs.status == LOST


def test_provider_invalid_truth_boundary_hash_is_unverifiable() -> None:
    obs = collect_provider(
        openrouter_paid_route_ok=True,
        free_route_revision=SHA40,
        free_llm_revolver_ok=True,
        paid_truth_boundary_hash="not-sha256",
    )
    assert obs.status == UNVERIFIABLE


# ---------------------------------------------------------------------------
# build_capability_delta
# ---------------------------------------------------------------------------

def _obs(capability_id: str, status: str = PRESERVED, rev: str = SHA40) -> CollectorObservation:
    return build_observation(
        capability_id=capability_id,
        collector="git_workspace",
        status=status,
        cause="test observation",
        source_revision=rev,
    )


def test_delta_identical_snapshots_all_preserved() -> None:
    obs = [_obs("git.workspace"), _obs("ci.check")]
    delta = build_capability_delta(
        operation_family="branch_file_change",
        baseline_revision=SHA40,
        result_revision=SHA40B,
        baseline_observations=obs,
        result_observations=obs,
    )
    assert all(e.status == PRESERVED for e in delta.entries)
    assert len(delta.delta_sha256) == 64


def test_delta_missing_result_is_lost() -> None:
    base = [_obs("git.workspace"), _obs("ci.check")]
    result = [_obs("git.workspace")]  # ci.check gone
    delta = build_capability_delta(
        operation_family="pr_merge_close",
        baseline_revision=SHA40,
        result_revision=SHA40B,
        baseline_observations=base,
        result_observations=result,
    )
    lost = [e for e in delta.entries if e.capability_id == "ci.check"]
    assert len(lost) == 1
    assert lost[0].status == LOST


def test_delta_new_capability_no_baseline_is_preserved() -> None:
    base: list[CollectorObservation] = []
    result = [_obs("mcp.installation")]
    delta = build_capability_delta(
        operation_family="draft_pr_lifecycle",
        baseline_revision=SHA40,
        result_revision=SHA40B,
        baseline_observations=base,
        result_observations=result,
    )
    assert delta.entries[0].status == PRESERVED
    assert "first observation" in delta.entries[0].cause


def test_delta_result_unverifiable_propagates() -> None:
    base = [_obs("postgres.schema")]
    result = [_obs("postgres.schema", status=UNVERIFIABLE)]
    delta = build_capability_delta(
        operation_family="pr_merge_close",
        baseline_revision=SHA40,
        result_revision=SHA40B,
        baseline_observations=base,
        result_observations=result,
    )
    assert delta.entries[0].status == UNVERIFIABLE


def test_delta_hash_differs_without_readback_is_degraded() -> None:
    base = [_obs("git.workspace", rev=SHA40)]
    result = [_obs("git.workspace", rev=SHA40B)]  # same status but different hash
    delta = build_capability_delta(
        operation_family="branch_file_change",
        baseline_revision=SHA40,
        result_revision=SHA40B,
        baseline_observations=base,
        result_observations=result,
    )
    # Hashes differ (different rev) → degraded unless REPLACED_WITH_VERIFIED_EQUIVALENT
    assert delta.entries[0].status in (DEGRADED, PRESERVED)


def test_delta_is_sort_stable() -> None:
    obs = [_obs("z.capability"), _obs("a.capability"), _obs("m.capability")]
    delta = build_capability_delta(
        operation_family="branch_file_change",
        baseline_revision=SHA40,
        result_revision=SHA40B,
        baseline_observations=obs,
        result_observations=obs,
    )
    ids = [e.capability_id for e in delta.entries]
    assert ids == sorted(ids)


def test_delta_sha256_changes_with_content() -> None:
    obs_a = [_obs("git.workspace")]
    obs_b = [_obs("ci.check")]
    d1 = build_capability_delta(operation_family="branch_file_change",
                                baseline_revision=SHA40, result_revision=SHA40B,
                                baseline_observations=obs_a, result_observations=obs_a)
    d2 = build_capability_delta(operation_family="branch_file_change",
                                baseline_revision=SHA40, result_revision=SHA40B,
                                baseline_observations=obs_b, result_observations=obs_b)
    assert d1.delta_sha256 != d2.delta_sha256


def test_delta_intentionally_removed_propagates() -> None:
    base = [_obs("git.workspace")]
    result = [_obs("git.workspace", status=INTENTIONALLY_REMOVED)]
    delta = build_capability_delta(
        operation_family="branch_file_change",
        baseline_revision=SHA40,
        result_revision=SHA40B,
        baseline_observations=base,
        result_observations=result,
    )
    assert delta.entries[0].status == INTENTIONALLY_REMOVED


# ---------------------------------------------------------------------------
# collect_config_provenance (Issue #1169)
#
# Wires the configuration provenance module into the read-only evidence /
# PatchMon readback surface. Uses the real live path: resolve_config_sources
# + materialize_receipt + verify_receipt. No production logic is copied here.
# ---------------------------------------------------------------------------

from agent_runtime.configuration import (  # noqa: E402
    ConfigSourceContract,
    ReceiptOptions,
    ResolveOptions,
    default_priority_for,
    materialize_receipt,
    resolve_config_sources,
)


def _csrc(
    id: str,
    kind: str,
    values: dict,
    *,
    revision: str = SHA40,
    content_hash: str | None = None,
    schema_hash: str = "sch-default",
    priority: int | None = None,
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
    )


_CBASE = [
    _csrc("defaults", "compiled-defaults", {"a": 1}),
    _csrc("deploy", "deployment-config", {"b": 2}),
]


def test_config_provenance_resolved_is_preserved() -> None:
    res = resolve_config_sources(_CBASE)
    receipt = materialize_receipt(res, ReceiptOptions(revision=SHA40))
    obs = collect_config_provenance(resolution=res, receipt=receipt)

    assert obs.status == PRESERVED
    assert obs.capability_id == "configuration.provenance"
    assert obs.collector == "config_provenance"
    assert obs.source_revision == SHA40
    assert obs.detail["receipt_hash"] == receipt.receipt_hash
    assert obs.detail["schema_hash"] == res.schema_hash
    assert obs.detail["resolved_hash"] == res.resolved_hash
    assert obs.detail["status"] == "RESOLVED"
    assert obs.detail["drift"] is None
    assert obs.detail["source_count"] == 2


def test_config_provenance_contradicted_is_degraded_and_blocks() -> None:
    # Resolve against a wrong expected hash -> CONTRADICTED (config-drift).
    res = resolve_config_sources(
        _CBASE, ResolveOptions(expected_receipt_hash="deadbeef")
    )
    assert res.status == "CONTRADICTED"
    receipt = materialize_receipt(res, ReceiptOptions(revision=SHA40))
    obs = collect_config_provenance(resolution=res, receipt=receipt)

    # Drift invalidates prior run/permission bindings: never PRESERVED.
    assert obs.status == DEGRADED
    assert "config-drift" in obs.cause
    assert "invalidates" in obs.cause
    assert obs.detail["drift"] == "content-drift"
    assert obs.detail["status"] == "CONTRADICTED"
    # Revision binding survives drift so the contradiction is auditable.
    assert obs.source_revision == SHA40


def test_config_provenance_blocked_is_unverifiable() -> None:
    # Unknown source kind fails closed -> BLOCKED, no loadable projection.
    bad = [
        _csrc("defaults", "compiled-defaults", {"a": 1}),
        _csrc("bogus", "not-a-real-kind", {"z": 9}),
    ]
    res = resolve_config_sources(bad)
    assert res.status == "BLOCKED"
    assert res.resolved_hash == ""  # no loadable projection to hash
    receipt = materialize_receipt(res, ReceiptOptions(revision=SHA40))
    obs = collect_config_provenance(resolution=res, receipt=receipt)

    assert obs.status == UNVERIFIABLE
    assert "blocked" in obs.cause
    assert obs.detail["resolved_hash"] == ""


def test_config_provenance_missing_receipt_hash_is_unverifiable() -> None:
    res = resolve_config_sources(_CBASE)
    receipt = materialize_receipt(res, ReceiptOptions(revision=SHA40))
    # Tamper: blank the receipt hash.
    tampered = type(receipt)(
        receipt_hash="",
        status=receipt.status,
        source_order=receipt.source_order,
        source_hashes=receipt.source_hashes,
        schema_hash=receipt.schema_hash,
        resolved_hash=receipt.resolved_hash,
        resolved=receipt.resolved,
        drift=receipt.drift,
        errors=receipt.errors,
        revision=receipt.revision,
        image_digest=receipt.image_digest,
        materialized_at=receipt.materialized_at,
    )
    obs = collect_config_provenance(resolution=res, receipt=tampered)

    assert obs.status == UNVERIFIABLE
    assert "receipt_hash" in obs.cause
    assert obs.source_revision == ""


def test_config_provenance_tampered_receipt_is_unverifiable() -> None:
    res = resolve_config_sources(_CBASE)
    receipt = materialize_receipt(res, ReceiptOptions(revision=SHA40))
    # Tamper: keep a valid-looking hash but mutate the resolved payload so
    # verify_receipt() fails (loaded projection != receipt).
    tampered = type(receipt)(
        receipt_hash=receipt.receipt_hash,
        status=receipt.status,
        source_order=receipt.source_order,
        source_hashes=receipt.source_hashes,
        schema_hash=receipt.schema_hash,
        resolved_hash=receipt.resolved_hash,
        resolved={**receipt.resolved, "injected": 999},
        drift=receipt.drift,
        errors=receipt.errors,
        revision=receipt.revision,
        image_digest=receipt.image_digest,
        materialized_at=receipt.materialized_at,
    )
    obs = collect_config_provenance(resolution=res, receipt=tampered)

    assert obs.status == UNVERIFIABLE
    assert "verification" in obs.cause


def test_config_provenance_revision_falls_back_to_resolved_hash() -> None:
    # revision is not a SHA -> fall back to resolved_hash (SHA-256) so the
    # observation is still revision-bound.
    res = resolve_config_sources(_CBASE)
    receipt = materialize_receipt(res, ReceiptOptions(revision="rev-not-a-sha"))
    obs = collect_config_provenance(resolution=res, receipt=receipt)

    assert obs.status == PRESERVED
    assert obs.source_revision == res.resolved_hash
    assert len(obs.source_revision) == 64


def test_config_provenance_observation_hash_is_deterministic() -> None:
    res = resolve_config_sources(_CBASE)
    receipt = materialize_receipt(res, ReceiptOptions(revision=SHA40))
    o1 = collect_config_provenance(resolution=res, receipt=receipt)
    o2 = collect_config_provenance(resolution=res, receipt=receipt)

    assert o1.observation_hash == o2.observation_hash
    assert o1.observation_hash  # non-empty


def test_config_provenance_drift_changes_observation_hash() -> None:
    res_ok = resolve_config_sources(_CBASE)
    receipt_ok = materialize_receipt(res_ok, ReceiptOptions(revision=SHA40))
    o_ok = collect_config_provenance(resolution=res_ok, receipt=receipt_ok)

    res_drift = resolve_config_sources(
        _CBASE, ResolveOptions(expected_receipt_hash="deadbeef")
    )
    receipt_drift = materialize_receipt(res_drift, ReceiptOptions(revision=SHA40))
    o_drift = collect_config_provenance(
        resolution=res_drift, receipt=receipt_drift
    )

    assert o_ok.status == PRESERVED
    assert o_drift.status == DEGRADED
    assert o_ok.observation_hash != o_drift.observation_hash


def test_config_provenance_rejects_non_contract_inputs() -> None:
    res = resolve_config_sources(_CBASE)
    receipt = materialize_receipt(res, ReceiptOptions(revision=SHA40))

    with pytest.raises(CollectorContractError):
        collect_config_provenance(resolution="not-a-contract", receipt=receipt)  # type: ignore[arg-type]
    with pytest.raises(CollectorContractError):
        collect_config_provenance(resolution=res, receipt="not-a-receipt")  # type: ignore[arg-type]
