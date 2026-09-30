from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.job_store import StoredSovereignAgentJob
from agent_runtime import cag_self_healing_runtime as runtime
from agent_runtime.cag_self_healing import SelfHealingContractError
from agent_runtime import repository_execution


def _job(**overrides) -> StoredSovereignAgentJob:
    values = {
        "job_id": "agent-source-1",
        "user_id": "00000000-0000-4000-8000-000000000001",
        "executor": "sovereign-local-runner",
        "repo_url": "https://github.com/example/repo",
        "branch": "main",
        "mission": "bounded mission",
        "status": "running",
        "workspace_id": "agent-source-1",
        "external_ref": "sovereign-local-runner:agent-source-1",
        "blocker": None,
        "events": (
            {"stage": "agent_job_created"},
            {"stage": "sovereign_repository_checked_out"},
            {"stage": "repository_execution_contract_bound"},
            {"stage": "sovereign_local_execution_queued"},
            {"stage": "sovereign_executor_started"},
            {"stage": "sovereign_executor_bound"},
        ),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return StoredSovereignAgentJob(**values)


def test_runtime_observation_uses_sovereign_local_executor(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "_billing_summary", lambda _conn, _job_id: {
        "settlementCount": 0,
        "providerCostMicros": 0,
        "chargedCostMicros": 0,
        "creditDeltaMicros": 0,
        "settled": False,
    })
    monkeypatch.setattr(runtime, "_repository_execution_route_path", lambda: "/api/user/agent/repository/run")
    monkeypatch.setattr(runtime, "_source_revision", lambda: "a" * 40)
    monkeypatch.setattr(runtime, "_readback_available_for_timeout", lambda _job, _timeout, _root: False)

    observed = runtime._build_observation(object(), _job(), None)

    assert observed.external_ref_class == "sovereign-local-runner"
    assert observed.observed_endpoint_path == "/api/user/agent/repository/run"
    assert observed.billing_mode == "free"
    # Executor identity and implementation authority are the same persisted local contract.
    assert _job().executor == "sovereign-local-runner"


def test_runtime_marks_stalled_local_execution_from_persisted_blocker(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "_billing_summary", lambda _conn, _job_id: {
        "settlementCount": 0,
        "providerCostMicros": 0,
        "chargedCostMicros": 0,
        "creditDeltaMicros": 0,
        "settled": False,
    })
    monkeypatch.setattr(runtime, "_repository_execution_route_path", lambda: "/api/user/agent/repository/run")
    monkeypatch.setattr(runtime, "_source_revision", lambda: "a" * 40)
    monkeypatch.setattr(runtime, "_readback_available_for_timeout", lambda _job, _timeout, _root: True)

    observed = runtime._build_observation(
        object(),
        _job(
            status="blocked",
            blocker="SOVEREIGN_LOCAL_EXECUTION_STALLED: bounded reconciliation window elapsed",
            updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ),
        None,
    )
    assert observed.handoff_timed_out is True
    assert observed.task_readback_available is True


def test_verified_workspace_recovery_never_reexecutes(monkeypatch) -> None:
    state = {
        "job": _job(
            status="blocked",
            blocker="SOVEREIGN_LOCAL_EXECUTION_STALLED: bounded reconciliation window elapsed",
        ),
        "events": [],
        "updated": 0,
    }

    monkeypatch.setattr(
        repository_execution,
        "read_agent_job",
        lambda _conn, *, user_id, job_id: state["job"],
    )

    def update_state(_conn, *, job_id, status, clear_blocker=False, **_kwargs):
        state["updated"] += 1
        state["job"] = replace(
            state["job"],
            status=status,
            blocker=None if clear_blocker else state["job"].blocker,
        )

    monkeypatch.setattr(repository_execution, "update_agent_job_state", update_state)
    monkeypatch.setattr(
        repository_execution,
        "append_agent_event",
        lambda _conn, _job_id, event: state["events"].append(event),
    )
    monkeypatch.setattr(
        repository_execution,
        "reconcile_repository_execution",
        lambda _conn, **_kwargs: state["job"],
    )

    monkeypatch.setattr(
        repository_execution,
        "run_agent_job_tool",
        lambda _job, tool, _payload, _root: SimpleNamespace(
            status="done",
            changed_files=("testfile.txt",),
        ) if tool == "git-status" else SimpleNamespace(status="blocked", changed_files=()),
    )

    recovered_job, recovered = repository_execution.recover_stalled_repository_job_from_verified_readback(
        object(),
        user_id=state["job"].user_id,
        job_id=state["job"].job_id,
        workspace_root=Path("/tmp/sovereign-test-root"),
    )

    assert recovered is True
    assert recovered_job is not None
    assert recovered_job.status == "running"
    assert state["updated"] == 1
    assert [event.stage for event in state["events"]] == [
        "self_healing_workspace_readback_recovered"
    ]


def test_unproven_workspace_recovery_does_not_mutate(monkeypatch) -> None:
    state = {
        "job": _job(
            status="blocked",
            blocker="SOVEREIGN_LOCAL_EXECUTION_STALLED: bounded reconciliation window elapsed",
        ),
        "updated": 0,
    }
    monkeypatch.setattr(
        repository_execution,
        "read_agent_job",
        lambda _conn, *, user_id, job_id: state["job"],
    )
    monkeypatch.setattr(
        repository_execution,
        "update_agent_job_state",
        lambda *_args, **_kwargs: state.__setitem__("updated", state["updated"] + 1),
    )
    monkeypatch.setattr(
        repository_execution,
        "run_agent_job_tool",
        lambda *_args, **_kwargs: SimpleNamespace(status="done", changed_files=()),
    )

    _, recovered = repository_execution.recover_stalled_repository_job_from_verified_readback(
        object(),
        user_id=state["job"].user_id,
        job_id=state["job"].job_id,
        workspace_root=Path("/tmp/sovereign-test-root"),
    )
    assert recovered is False
    assert state["updated"] == 0


def test_persisted_cag_evidence_is_reusable_and_divergence_fails_closed() -> None:
    request_sha = "1" * 64
    response_sha = "2" * 64
    result_sha = "3" * 64
    incidents = [
        {
            "cag_verified": True,
            "cag_request_sha256": request_sha,
            "cag_response_sha256": response_sha,
            "cag_result_sha256": result_sha,
        },
        {"cag_verified": False},
    ]
    projection = runtime._persisted_cag_evidence(incidents)
    assert projection == {
        "requestSha256": request_sha,
        "responseSha256": response_sha,
        "resultSha256": result_sha,
    }
    with pytest.raises(SelfHealingContractError, match="diverged"):
        runtime._persisted_cag_evidence([
            incidents[0],
            {
                "cag_verified": True,
                "cag_request_sha256": "4" * 64,
                "cag_response_sha256": response_sha,
                "cag_result_sha256": result_sha,
            },
        ])


def test_owner_identity_resolution_matches_owner_input_id_or_email_policy(monkeypatch) -> None:
    owner_id = "00000000-0000-4000-8000-000000000001"

    class Cursor:
        def __init__(self, rows):
            self.rows = rows
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, sql, params):
            assert "FROM admin_users" in sql
            assert params == ("owner@example.test",)
        def fetchall(self):
            return list(self.rows)

    class Connection:
        def __init__(self, rows):
            self.rows = rows
        def cursor(self):
            return Cursor(self.rows)

    monkeypatch.delenv("SOVEREIGN_OWNER_ADMIN_ID", raising=False)
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_EMAIL", "Owner@Example.Test")
    assert runtime._configured_owner_admin_id(Connection([{"id": owner_id}])) == owner_id
    assert runtime._configured_owner_admin_id(Connection([])) == ""
    assert runtime._configured_owner_admin_id(Connection([{"id": owner_id}, {"id": owner_id}])) == ""
    assert runtime._configured_owner_matches_admin({"id": owner_id, "email": "OWNER@example.test"}) is True
    assert runtime._configured_owner_matches_admin({"id": owner_id, "email": "other@example.test"}) is False

    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_ID", owner_id)
    monkeypatch.delenv("SOVEREIGN_OWNER_ADMIN_EMAIL", raising=False)
    assert runtime._configured_owner_admin_id(None) == owner_id
    assert runtime._configured_owner_matches_admin({"id": owner_id, "email": "other@example.test"}) is True


def test_runtime_source_has_scoped_consent_and_no_direct_repository_mutator() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "agent_runtime"
        / "cag_self_healing_runtime.py"
    ).read_text("utf-8")
    assert '"/api/admin/self-healing/authority"' in source
    assert 'methods=["DELETE"]' in source
    assert "expiresInSeconds must be between 300 and 604800" in source
    assert "maxAutoRepairsPerHour must be between 1 and 10" in source
    assert "maxAutoRepairsPerDay must be between 1 and 30" in source
    assert "SELF_HEALING_DAILY_LIMIT_REACHED_MANUAL_APPROVAL_REQUIRED" in source
    assert "_claim_manual_approval(" in source
    assert "/api/admin/self-healing/incidents/<incident_id>/approve" in source
    assert "execute_live_cag_request(" in source
    assert 'capability_id="wolfram.cag.compute"' in source
    assert "start_repository_execution(" in source
    assert "recover_stalled_repository_job_from_verified_readback(" in source
    assert "_claim_incident_for_cag(" in source
    assert "CAG_VERIFYING" in source
    assert "owner_authority_required" in source
    assert "SOVEREIGN_OWNER_ADMIN_EMAIL" in source
    assert "_configured_owner_matches_admin(" in source
    assert "STANDING_AUTHORITY_REVOKED_OR_EXPIRED" in source
    assert "automaticMerge" in source
    assert '"sovereign-local-runner"' in source
    # CAG and this controller never write repository files directly.
    assert "run_git_command(" not in source
    assert "git push" not in source
