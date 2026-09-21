from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime import repository_execution  # noqa: E402
from backend.agent_runtime.agent_zero_a2a import AgentZeroA2ATask  # noqa: E402


def _job(*, external_ref: str, status: str = "running"):
    return SimpleNamespace(
        job_id="agent-test",
        user_id="owner-test",
        status=status,
        external_ref=external_ref,
        workspace_id="agent-test",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Implement one bounded repository change.",
        changed_files=(),
        blocker=None,
    )


def test_pending_submit_is_blocked_when_permission_is_revoked(monkeypatch):
    pending = repository_execution._pending_submit_ref("agent-test")
    job = _job(external_ref=pending)
    state = {"job": job}
    monkeypatch.setattr(
        repository_execution,
        "compare_and_swap_agent_job_external_ref",
        lambda _conn, *, job_id, expected_ref, new_ref: True,
    )
    monkeypatch.setattr(
        repository_execution,
        "read_agent_job",
        lambda *_args, **_kwargs: state["job"],
    )
    monkeypatch.setattr(
        repository_execution,
        "_require_repository_effect_authority",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            repository_execution.RevocationClosureError("permission receipt is revoked")
        ),
    )
    blocked = []
    monkeypatch.setattr(
        repository_execution,
        "_block_job",
        lambda _conn, current, message, stage: blocked.append((message, stage)) or current,
    )

    class Client:
        def submit_repository_task(self, **_kwargs):
            raise AssertionError("revoked job must not reach Agent Zero")

    result = repository_execution._submit_pending_repository_job(
        object(),
        job=job,
        a2a_client_factory=lambda: Client(),
    )

    assert result is job
    assert blocked
    assert blocked[0][1] == "repository_revocation_blocked"
    assert "REVOKED_BEFORE_EXTERNAL_EFFECT" in blocked[0][0]


def test_retry_rechecks_live_permission_after_claim(monkeypatch):
    claim = repository_execution._claim("retry", "task-original")
    job = _job(external_ref=claim)
    checks = {"count": 0}

    def gate(_conn, *, job):
        checks["count"] += 1
        raise repository_execution.RevocationClosureError("permission receipt is superseded")

    monkeypatch.setattr(repository_execution, "_require_repository_effect_authority", gate)
    monkeypatch.setattr(
        repository_execution,
        "_block_job",
        lambda _conn, current, _message, _stage: current,
    )

    class Client:
        def submit_repository_task(self, **_kwargs):
            raise AssertionError("retry must be blocked before external submit")

    repository_execution._submit_after_claim(
        object(),
        job=job,
        claim_ref=claim,
        retry=True,
        a2a_client_factory=lambda: Client(),
    )

    assert checks["count"] == 1


def test_claim_does_not_replace_live_authority_check(monkeypatch):
    pending = repository_execution._pending_submit_ref("agent-test")
    job = _job(external_ref=pending)
    claim_calls = {"count": 0}
    gate_calls = {"count": 0}

    monkeypatch.setattr(
        repository_execution,
        "compare_and_swap_agent_job_external_ref",
        lambda _conn, *, job_id, expected_ref, new_ref: claim_calls.__setitem__("count", claim_calls["count"] + 1) or True,
    )
    monkeypatch.setattr(repository_execution, "read_agent_job", lambda *_args, **_kwargs: job)

    def gate(_conn, *, job):
        gate_calls["count"] += 1
        return True

    monkeypatch.setattr(repository_execution, "_require_repository_effect_authority", gate)

    class Client:
        def submit_repository_task(self, **_kwargs):
            return AgentZeroA2ATask(task_id="task-authorized", state="submitted")

    monkeypatch.setattr(repository_execution, "append_agent_event", lambda *_args, **_kwargs: None)

    repository_execution._submit_pending_repository_job(
        object(),
        job=job,
        a2a_client_factory=lambda: Client(),
    )

    assert claim_calls["count"] >= 1
    assert gate_calls["count"] == 1


def test_unbound_repository_effect_path_blocks_fail_closed(monkeypatch):
    claim = repository_execution._claim("submit", "agent-test")
    job = _job(external_ref=claim)

    monkeypatch.setattr(repository_execution, "_require_repository_effect_authority", lambda *_args, **_kwargs: False)
    blocked = []
    monkeypatch.setattr(
        repository_execution,
        "_block_job",
        lambda _conn, current, message, stage: blocked.append((message, stage)) or current,
    )

    class Client:
        def submit_repository_task(self, **_kwargs):
            raise AssertionError("unbound path must not reach external submit")

    repository_execution._submit_after_claim(
        object(),
        job=job,
        claim_ref=claim,
        retry=False,
        a2a_client_factory=lambda: Client(),
    )

    assert blocked == [(
        "Repository effect path is not bound to a live canonical permission; submit is blocked.",
        "repository_permission_unbound",
    )]
