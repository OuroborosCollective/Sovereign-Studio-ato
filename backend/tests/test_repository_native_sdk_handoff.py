"""Native Agents SDK closeout handoff; mandatory with the shipping CI dependencies."""
from types import SimpleNamespace
from backend.tests.test_repository_empty_file_closeout import workspace

def test_native_sdk_handoff_stops_after_one_model_turn(workspace, monkeypatch):
    import asyncio
    from agents import Model, ModelResponse, RunConfig
    from agents.usage import Usage
    from openai.types.responses import ResponseFunctionToolCall
    from backend.agent_runtime import cognitive_swarm_agents as swarm
    from backend.agent_runtime import cognitive_repository_tools as bound
    from backend.agent_runtime import job_store
    from backend.agent_runtime.job_store import StoredSovereignAgentJob
    from dataclasses import replace

    root, repo, _, _ = workspace
    (repo / "Tester").touch()
    state = SimpleNamespace(job=StoredSovereignAgentJob(
        job_id="agent-empty", workspace_id="agent-empty", user_id="owner-empty",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main", mission="Add empty Tester", status="running",
        executor="sovereign-local-runner",
    ), calls=[], receipts=[], model_calls=0)
    def update(_conn, **kw):
        fields = {key: value for key, value in kw.items() if key in {
            "status", "changed_files", "diff_summary", "test_summary", "blocker"
        } and value is not None}
        if kw.get("clear_blocker"):
            fields["blocker"] = None
        state.job = replace(state.job, **fields)
    monkeypatch.setattr(bound, "read_agent_job", lambda *a, **kw: state.job)
    monkeypatch.setattr(bound, "start_agent_tool_call", lambda *a, **kw: state.calls.append(kw) or f"call-{len(state.calls)}")
    monkeypatch.setattr(bound, "finish_agent_tool_call", lambda *a, **kw: state.receipts.append(kw) or {})
    monkeypatch.setattr(job_store, "append_agent_event", lambda *a, **kw: None)
    monkeypatch.setattr(job_store, "update_agent_job_state", update)
    toolset = bound.BoundRepositoryToolset(
        get_connection=lambda: SimpleNamespace(close=lambda: None),
        user_id="owner-empty", run_id="repo-agent-empty", job_id="agent-empty",
        task_ids_by_agent={"free_single_agent": "task-empty"},
        workspace_root=root, write_confirmed=True,
    )
    class LocalProvider(Model):
        async def get_response(self, **kw):
            state.model_calls += 1
            assert state.model_calls == 1, "Handoff must not re-enter the model"
            return ModelResponse(
                output=[ResponseFunctionToolCall(
                    type="function_call", name="finish_repository_editing",
                    arguments='{"summary":"Added empty Tester; verification pending."}',
                    call_id="handoff-1", id="fc-handoff-1",
                )],
                usage=Usage(requests=1, input_tokens=1, output_tokens=1, total_tokens=2),
                response_id="response-handoff-1",
            )
        async def stream_response(self, **kw):
            raise AssertionError("Streaming is not used")
            yield
    monkeypatch.setattr(swarm, "build_route_run_config", lambda *a, **kw: SimpleNamespace(
        model="local-provider-fixture", transport="freellm",
        run_config=RunConfig(model=LocalProvider(), tracing_disabled=True),
    ))
    intent = swarm.MissionIntent(
        mode="repository_execution", normalized_goal="Add empty Tester",
        requires_online_tools=True, requires_repository_workspace=True,
        learning_scope=[], confidence=1,
    )
    result = asyncio.run(swarm.run_free_single_agent(
        "Add empty Tester", model="local-provider-fixture", route={"id":"fixture"},
        intent=intent, repository_tool_factory=toolset.tools_for_role,
    ))
    assert result["status"] == "COMPLETED"
    assert state.model_calls == 1
    assert [call["tool_name"] for call in state.calls] == ["git-status", "diff"]
    assert "new file mode 100644" in state.job.diff_summary
    assert state.job.test_summary is None
    assert "verification" in result["result"]["assistant_text"]
    assert all(receipt["mutation_performed"] is False for receipt in state.receipts)
    assert all(receipt["evidence_gate_result"] != "PASS" for receipt in state.receipts)


def test_handoff_tool_requires_single_agent_write_authority(workspace):
    from backend.agent_runtime.cognitive_repository_tools import BoundRepositoryToolset
    root, _, _, _ = workspace
    for write_confirmed, role, expected in (
        (False, "free_single_agent", False), (True, "free_single_agent", True),
        (True, "paid_single_agent", True), (True, "predictive_qa", False),
    ):
        toolset = BoundRepositoryToolset(
            get_connection=lambda: None, user_id="owner-empty", run_id="repo-agent-empty",
            job_id="agent-empty", task_ids_by_agent={}, workspace_root=root,
            write_confirmed=write_confirmed,
        )
        names = [tool.name for tool in toolset.tools_for_role(role)]
        assert ("finish_repository_editing" in names) is expected

