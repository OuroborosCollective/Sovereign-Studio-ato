from pathlib import Path

BASE_SHA = "5a682f8407536d6f7ccbc0b6908a9d04e8fdd434"


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} matches, got {actual}")
    target.write_text(text.replace(old, new, count), encoding="utf-8")


old = '''def _recover_lost_original_task(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    bound_ref: str,
    task_id: str,
    a2a_client_factory: A2AClientFactory,
) -> StoredSovereignAgentJob:
    claim_ref = _claim("retry", task_id)
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=bound_ref,
        new_ref=claim_ref,
    ):
        return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
    claimed = read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="agent_zero_a2a_original_task_lost",
        level="warning",
        message="The persisted original Agent Zero task is gone after runtime restart; one atomic recovery submit is allowed.",
    ))
    return _submit_after_claim(
        conn,
        job=claimed,
        claim_ref=claim_ref,
        retry=True,
        a2a_client_factory=a2a_client_factory,
    )
'''

new = '''def _recover_lost_original_task(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    bound_ref: str,
    task_id: str,
    workspace_root: Path | None,
    a2a_client_factory: A2AClientFactory,
) -> StoredSovereignAgentJob:
    # A2A task storage is not the repository truth boundary. A missing task may
    # follow an Agent Zero restart or an in-memory task-store loss after the
    # shared workspace was already mutated. Inspect the owned workspace first;
    # never duplicate repository work merely because tasks/get returned 404.
    status_result = run_agent_job_tool(job, "git-status", {}, workspace_root)
    if status_result.status != "done":
        return _block_job(
            conn,
            job,
            (
                "AGENT_ZERO_A2A_TASK_LOST: the original task is no longer readable and "
                "workspace mutation state could not be verified; recovery submit is quarantined."
            ),
            "agent_zero_a2a_lost_workspace_unverified",
        )

    if status_result.changed_files:
        claim_ref = _claim("closeout-lost", task_id)
        if not compare_and_swap_agent_job_external_ref(
            conn,
            job_id=job.job_id,
            expected_ref=bound_ref,
            new_ref=claim_ref,
        ):
            return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
        claimed = read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
        append_agent_event(conn, job.job_id, SovereignAgentEvent(
            stage="agent_zero_a2a_lost_workspace_changes_detected",
            level="warning",
            message=(
                "The original Agent Zero task is no longer readable, but the owned shared workspace "
                "contains real changes; Sovereign will close out those changes without resubmitting."
            ),
        ))
        return _closeout_repository_job(
            conn,
            job=claimed,
            claim_ref=claim_ref,
            bound_ref=bound_ref,
            workspace_root=workspace_root,
        )

    claim_ref = _claim("retry", task_id)
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=bound_ref,
        new_ref=claim_ref,
    ):
        return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
    claimed = read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="agent_zero_a2a_original_task_lost",
        level="warning",
        message=(
            "The persisted original Agent Zero task is gone and the owned workspace has no changes; "
            "one atomic recovery submit is allowed."
        ),
    ))
    return _submit_after_claim(
        conn,
        job=claimed,
        claim_ref=claim_ref,
        retry=True,
        a2a_client_factory=a2a_client_factory,
    )
'''

for path in (
    "backend/agent_runtime/repository_execution.py",
    "scripts/sovereign-backend/agent_runtime/repository_execution.py",
):
    replace(path, old, new)
    replace(
        path,
        '''        return _recover_lost_original_task(\n            conn,\n            job=job,\n            bound_ref=external_ref,\n            task_id=task_id,\n            a2a_client_factory=a2a_client_factory,\n        )''',
        '''        return _recover_lost_original_task(\n            conn,\n            job=job,\n            bound_ref=external_ref,\n            task_id=task_id,\n            workspace_root=workspace_root,\n            a2a_client_factory=a2a_client_factory,\n        )''',
    )

test_path = "backend/tests/test_repository_execution.py"
replace(
    test_path,
    '''    client = Client()\n    recovered = repository_execution.reconcile_repository_execution(''',
    '''    client = Client()\n    monkeypatch.setattr(\n        repository_execution,\n        "run_agent_job_tool",\n        lambda *_args, **_kwargs: _done_tool(changed_files=()),\n    )\n    recovered = repository_execution.reconcile_repository_execution(''',
)

anchor = '''def test_ambiguous_submit_outcome_blocks_without_any_automatic_second_submit(monkeypatch):\n'''
added = '''def test_original_task_lost_with_workspace_changes_closes_out_without_resubmit(monkeypatch):
    state = _patch_job_store(monkeypatch, _job())
    closeout_calls = []

    class Client:
        submit_count = 0

        def get_task(self, _task_id):
            raise AgentZeroA2ATaskLost(
                "AGENT_ZERO_A2A_TASK_LOST",
                "USE_SINGLE_ATOMIC_RESTART_RECOVERY",
                http_status=404,
            )

        def submit_repository_task(self, **_kwargs):
            self.submit_count += 1
            raise AssertionError("workspace mutation must be closed out before any recovery submit")

    monkeypatch.setattr(
        repository_execution,
        "run_agent_job_tool",
        lambda *_args, **_kwargs: _done_tool(changed_files=("README.md",)),
    )

    def closeout(_conn, *, job, claim_ref, bound_ref, workspace_root):
        closeout_calls.append((claim_ref, bound_ref, workspace_root))
        state["job"] = replace(job, status="validating", pr_state="ready", external_ref=bound_ref)
        return state["job"]

    monkeypatch.setattr(repository_execution, "_closeout_repository_job", closeout)
    client = Client()
    result = repository_execution.reconcile_repository_execution(
        object(),
        user_id="owner-test",
        job_id="agent-test",
        workspace_root=Path("/tmp/shared-workspaces"),
        a2a_client_factory=lambda: client,
    )

    assert result is not None
    assert result.status == "validating"
    assert result.pr_state == "ready"
    assert result.external_ref == "agent-zero-a2a:task-original"
    assert client.submit_count == 0
    assert len(closeout_calls) == 1
    assert closeout_calls[0][1] == "agent-zero-a2a:task-original"


def test_original_task_lost_with_unverifiable_workspace_blocks_without_resubmit(monkeypatch):
    state = _patch_job_store(monkeypatch, _job())

    class Client:
        submit_count = 0

        def get_task(self, _task_id):
            raise AgentZeroA2ATaskLost(
                "AGENT_ZERO_A2A_TASK_LOST",
                "USE_SINGLE_ATOMIC_RESTART_RECOVERY",
                http_status=404,
            )

        def submit_repository_task(self, **_kwargs):
            self.submit_count += 1
            raise AssertionError("unverified workspace must never be resubmitted")

    monkeypatch.setattr(
        repository_execution,
        "run_agent_job_tool",
        lambda *_args, **_kwargs: _failed_tool("git status unavailable"),
    )
    client = Client()
    result = repository_execution.reconcile_repository_execution(
        object(),
        user_id="owner-test",
        job_id="agent-test",
        a2a_client_factory=lambda: client,
    )

    assert result is not None
    assert result.status == "blocked"
    assert "workspace mutation state could not be verified" in (result.blocker or "")
    assert client.submit_count == 0
    assert state["job"].external_ref == "agent-zero-a2a:task-original"


'''
replace(test_path, anchor, added + anchor)

canonical = Path("backend/agent_runtime/repository_execution.py").read_bytes()
mirror = Path("scripts/sovereign-backend/agent_runtime/repository_execution.py").read_bytes()
if canonical != mirror:
    raise SystemExit("repository_execution mirror mismatch")
