from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

import agent_zero_backend_probe as probe
from agent_zero_diagnostics import AgentZeroDiagnosticsRuntime, BACKEND, AGENT_ZERO, AGENT_ZERO_PYTHON

REVISION = "e0cf7e91bdb7d5eb65f8b97a76af0fcf0904b066"
DIGEST = "sha256:" + "1" * 64


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    rt = AgentZeroDiagnosticsRuntime()
    rt.evidence_root = tmp_path / "evidence"
    rt.evidence_root.mkdir(mode=0o700)
    calls = []
    response = {"ok": True, "httpStatus": 200, "taskId": "canary-task", "taskState": "working"}

    def docker(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "inspect":
            identity = "a" * 64 if argv[-1] == BACKEND else "b" * 64
            data = {"id": identity, "image": "sha256:" + "c" * 64, "running": True,
                    "startedAt": "2026-09-12T00:00:00Z", "revision": REVISION}
        elif argv[1] == "image":
            data = ["ghcr.io/ouroboroscollective/sovereign-backend@" + DIGEST]
        else:
            assert argv[:6] == ["docker", "exec", "-i", "--user", "0", argv[5]]
            assert kwargs["input"].startswith('"""Fixed, stdin-only diagnostic')
            action = argv[10]
            if action == "inspect":
                data = {"ok": True, "status": "BACKEND_PROCESS_READBACK_VERIFIED"}
            elif action == "agent-zero":
                assert argv[6] == AGENT_ZERO_PYTHON
                data = {"loadedVersionsVerified": False,
                        "serverProcesses": [{"pid": 7, "sameExecutableAsProbe": True}]}
            else:
                if response.get("timeout"):
                    raise subprocess.TimeoutExpired(argv, 55, output="untrusted diagnostic output")
                data = dict(response)
                if action == "poll":
                    data["taskReadbackVerified"] = True
        return subprocess.CompletedProcess(argv, 0, json.dumps(data), "untrusted stderr must not escape")

    monkeypatch.setattr(subprocess, "run", docker)
    return rt, calls, response


def call(rt, operation="1" * 32, action="submit", **extra):
    args = {"expected_revision": REVISION, "expected_image_digest": DIGEST,
            "operation_id": operation, "action": action, "owner_approved": True}
    args.update(extra)
    return rt.canary(**args)


def sends(calls):
    return [c for c in calls if "submit" in c]


def test_submit_requires_terminal_get_and_is_replay_safe(runtime):
    rt, calls, response = runtime
    first = call(rt)
    assert first["ok"] is False
    assert first["result"]["taskId"] == "canary-task"
    assert call(rt) == first
    assert len(sends(calls)) == 1
    response["taskState"] = "completed"
    final = call(rt, action="poll")
    assert final["ok"] is True
    assert final["status"] == "AGENT_ZERO_A2A_CANARY_PASS"
    assert final["repositoryE2ePassed"] is False
    assert len(sends(calls)) == 1


def test_crash_claim_blocks_same_and_different_operation_after_restart(runtime):
    rt, calls, response = runtime
    response["timeout"] = True
    assert call(rt)["ok"] is False
    restarted = AgentZeroDiagnosticsRuntime()
    restarted.evidence_root = rt.evidence_root
    assert call(restarted)["status"] == "SUBMIT_CLAIMED"
    assert call(restarted, operation="2" * 32)["failureFamily"] == "AGENT_ZERO_CANARY_UNRESOLVED_PRIOR_SUBMIT"
    assert len(sends(calls)) == 1
    assert "untrusted" not in json.dumps(call(restarted, action="poll"))


@pytest.mark.parametrize("status", [200, 500, 503, None])
def test_unknown_acceptance_blocks_new_operation(runtime, status):
    rt, calls, response = runtime
    response.clear()
    response.update(ok=False, httpStatus=status, failureFamily="AGENT_ZERO_A2A_RESPONSE_INVALID")
    receipt = call(rt)
    assert receipt["result"]["httpStatus"] == status
    blocked = call(rt, operation="2" * 32)
    assert blocked["failureFamily"] == "AGENT_ZERO_CANARY_UNRESOLVED_PRIOR_SUBMIT"
    assert blocked["unresolvedOperations"][0]["operationId"] == "1" * 32
    assert len(sends(calls)) == 1


def test_old_release_unknown_without_task_is_quarantined_before_distinct_submit(runtime):
    rt, calls, response = runtime
    response["timeout"] = True
    assert call(rt)["failureFamily"] == "AGENT_ZERO_CANARY_OUTCOME_UNVERIFIED"
    receipt_path = next(rt.evidence_root.glob("agent-zero-canary-*.json"))
    receipt = json.loads(receipt_path.read_text())
    receipt["binding"]["revision"] = "0" * 40
    receipt["binding"]["digest"] = "sha256:" + "2" * 64
    receipt_path.write_text(json.dumps(receipt))
    receipt_path.chmod(0o600)

    response.clear()
    response.update(ok=True, httpStatus=200, taskId="new-release-task", taskState="working")
    result = call(rt, operation="2" * 32)
    assert result["result"]["taskId"] == "new-release-task"
    assert result["quarantinedUnknownOperations"] == ["1" * 32]
    assert len(sends(calls)) == 2

    marker = rt.evidence_root / ("agent-zero-canary-quarantine-" + "1" * 32 + ".json")
    quarantine = json.loads(marker.read_text())
    assert quarantine["unknownOutcomePreserved"] is True
    assert quarantine["sameOperationMayResubmit"] is False
    assert quarantine["allowsNewDistinctCanary"] is True
    assert quarantine["sourceRevision"] == "0" * 40
    assert quarantine["supersedingRevision"] == REVISION
    assert marker.stat().st_mode & 0o777 == 0o600

    original = json.loads(receipt_path.read_text())
    assert original["status"] == "SUBMIT_CLAIMED"
    assert original["result"] == {}
    replay = call(rt)
    assert replay["failureFamily"] == "AGENT_ZERO_CANARY_RUNTIME_CHANGED"
    assert len(sends(calls)) == 2


def test_old_release_receipt_with_task_id_stays_poll_only(runtime):
    rt, calls, response = runtime
    first = call(rt)
    assert first["result"]["taskId"] == "canary-task"
    receipt_path = next(rt.evidence_root.glob("agent-zero-canary-*.json"))
    receipt = json.loads(receipt_path.read_text())
    receipt["binding"]["revision"] = "0" * 40
    receipt["binding"]["digest"] = "sha256:" + "2" * 64
    receipt["binding"]["backend"]["revision"] = "0" * 40
    receipt_path.write_text(json.dumps(receipt))
    receipt_path.chmod(0o600)

    blocked = call(rt, operation="2" * 32)
    assert blocked["failureFamily"] == "AGENT_ZERO_CANARY_UNRESOLVED_PRIOR_SUBMIT"
    assert blocked["unresolvedOperations"] == [{
        "operationId": "1" * 32,
        "status": "TASK_OBSERVED",
        "taskIdPresent": True,
        "taskReadbackVerified": False,
        "taskState": "working",
        "httpStatus": 200,
        "bindingRevision": "0" * 40,
        "bindingDigest": "sha256:" + "2" * 64,
    }]
    assert not list(rt.evidence_root.glob("agent-zero-canary-quarantine-*.json"))

    response["taskState"] = "completed"
    polled = call(rt, action="poll")
    assert polled["ok"] is True
    assert polled["status"] == "AGENT_ZERO_A2A_CANARY_PASS"
    assert polled["binding"]["revision"] == "0" * 40
    assert polled["binding"]["backend"]["revision"] == "0" * 40
    assert polled["pollBinding"]["revision"] == REVISION
    assert polled["pollBinding"]["digest"] == DIGEST
    assert polled["pollBinding"]["agentZero"] == polled["binding"]["agentZero"]
    assert len(sends(calls)) == 1

    response["taskState"] = "working"
    next_canary = call(rt, operation="2" * 32)
    assert next_canary["result"]["taskId"] == "canary-task"
    assert len(sends(calls)) == 2


def test_cross_release_poll_fails_closed_if_agent_zero_runtime_changed(runtime):
    rt, calls, _ = runtime
    first = call(rt)
    assert first["result"]["taskId"] == "canary-task"
    receipt_path = next(rt.evidence_root.glob("agent-zero-canary-*.json"))
    receipt = json.loads(receipt_path.read_text())
    receipt["binding"]["revision"] = "0" * 40
    receipt["binding"]["digest"] = "sha256:" + "2" * 64
    receipt["binding"]["backend"]["revision"] = "0" * 40
    receipt["binding"]["agentZero"]["id"] = "d" * 64
    receipt_path.write_text(json.dumps(receipt))
    receipt_path.chmod(0o600)

    result = call(rt, action="poll")
    assert result["failureFamily"] == "AGENT_ZERO_CANARY_AGENT_ZERO_RUNTIME_CHANGED"
    assert len(sends(calls)) == 1


def test_definite_rejection_preserves_status_and_explicit_new_operation(runtime):
    rt, calls, response = runtime
    response.clear()
    response.update(ok=False, httpStatus=422, failureFamily="AGENT_ZERO_A2A_REQUEST_REJECTED")
    assert call(rt)["result"]["httpStatus"] == 422
    assert len(sends(calls)) == 1
    call(rt, operation="2" * 32)
    assert len(sends(calls)) == 2
    call(rt)  # Older receipt is still a replay, even after another attempt.
    assert len(sends(calls)) == 2


def test_poll_failure_keeps_task_identity(runtime):
    rt, calls, response = runtime
    call(rt)
    response.clear()
    response.update(ok=False, httpStatus=503, failureFamily="AGENT_ZERO_A2A_READ_UNAVAILABLE")
    assert call(rt, action="poll")["result"]["taskId"] == "canary-task"
    assert call(rt, operation="2" * 32)["ok"] is False
    assert len(sends(calls)) == 1


@pytest.mark.parametrize("kwargs", [{"owner_approved": False}, {"operation_id": "../escape"},
                                     {"expected_revision": "bad"}, {"expected_image_digest": "latest"},
                                     {"action": "shell"}])
def test_invalid_permission_and_scope_never_submit(runtime, kwargs):
    rt, calls, _ = runtime
    assert call(rt, **kwargs)["ok"] is False
    assert not sends(calls)


def test_runtime_revision_mismatch_never_submits(runtime):
    rt, calls, _ = runtime
    assert call(rt, expected_revision="0" * 40)["ok"] is False
    assert not sends(calls)


def test_receipt_permission_and_symlink_fail_closed(runtime, tmp_path):
    rt, calls, _ = runtime
    call(rt)
    receipt = next(rt.evidence_root.glob("agent-zero-canary-*.json"))
    receipt.chmod(0o644)
    assert call(rt)["ok"] is False
    receipt.unlink()
    receipt.symlink_to(tmp_path / "missing")
    assert call(rt)["ok"] is False
    assert len(sends(calls)) == 1


def test_inspection_is_not_canary_evidence(runtime):
    rt, calls, _ = runtime
    result = rt.inspect(expected_revision=REVISION, expected_image_digest=DIGEST)
    assert result["ok"] is True
    assert result["diagnosticStage"] == "complete"
    assert result["runtimeCanaryPassed"] is False
    assert result["agentZeroPackages"]["loadedVersionsVerified"] is False
    assert result["agentZeroPackages"]["diagnosticInterpreterVerified"] is True
    agent_zero_execs = [call for call in calls if "agent-zero" in call]
    assert len(agent_zero_execs) == 1
    assert agent_zero_execs[0][6] == "/opt/venv-a0/bin/python"
    assert not sends(calls)
    assert not list(rt.evidence_root.iterdir())


def test_agent_zero_probe_requires_running_server_executable_match(runtime, monkeypatch):
    rt, _, _ = runtime
    original_run = rt._run

    def no_match(argv, **kwargs):
        if "agent-zero" in argv:
            return {"serverProcesses": [{"pid": 9, "sameExecutableAsProbe": False}]}
        return original_run(argv, **kwargs)

    monkeypatch.setattr(rt, "_run", no_match)
    result = rt.inspect(expected_revision=REVISION, expected_image_digest=DIGEST)
    assert result["failureFamily"] == "AGENT_ZERO_PYTHON_EXECUTABLE_MISMATCH"
    assert result["diagnosticStage"] == "probe-agent-zero-runtime"


def test_inspection_preserves_bounded_runtime_failure_family(runtime, monkeypatch):
    rt, _, _ = runtime

    def mismatch(*_args, **_kwargs):
        raise RuntimeError("BACKEND_REVISION_OR_DIGEST_MISMATCH")

    monkeypatch.setattr(rt, "_bound_backend", mismatch)
    result = rt.inspect(expected_revision=REVISION, expected_image_digest=DIGEST)
    assert result == {
        "ok": False,
        "status": "BLOCKED",
        "failureFamily": "BACKEND_REVISION_OR_DIGEST_MISMATCH",
        "secretValuesReturned": False,
        "diagnosticStage": "bind-backend-runtime",
    }


def test_inspection_redacts_unbounded_exception_text(runtime, monkeypatch):
    rt, _, _ = runtime

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("sensitive-looking arbitrary process detail")

    monkeypatch.setattr(rt, "_bound_backend", unavailable)
    result = rt.inspect(expected_revision=REVISION, expected_image_digest=DIGEST)
    assert result["failureFamily"] == "AGENT_ZERO_DIAGNOSTIC_UNAVAILABLE"
    assert result["diagnosticStage"] == "bind-backend-runtime"
    assert "sensitive-looking" not in json.dumps(result)


def test_configuration_redacts_invalid_urls_and_unbounded_values():
    data = probe.safe_config({probe.KEY_NAMES[0]: "https://example.invalid/a2a?private",
                              probe.KEY_NAMES[1]: "invalid\nvalue"})
    assert data[probe.KEY_NAMES[0]] == "REDACTED_INVALID_VALUE"
    assert data[probe.KEY_NAMES[1]] == "REDACTED_INVALID_VALUE"
    assert "private" not in json.dumps(data)


def test_key_readback_uses_actual_regular_file_and_blocks_symlinks(tmp_path):
    owner = tmp_path / "owner"
    owner.mkdir()
    path = owner / "agent_zero_api_key.txt"
    path.write_bytes(os.urandom(32))  # Random bytes; never a credential fixture.
    path.chmod(0o600)
    config = {probe.KEY_NAMES[1]: str(owner), probe.KEY_NAMES[2]: str(path)}
    assert probe.key_readback(config)["readableAsWorker"] is True
    path.chmod(0o644)
    with pytest.raises(probe.ProbeFailure, match="PERMISSIONS_INVALID"):
        probe.key_readback(config)
    path.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(owner)
    with pytest.raises(probe.ProbeFailure, match="REJECTED"):
        probe.key_readback({probe.KEY_NAMES[1]: str(alias), probe.KEY_NAMES[2]: str(alias / path.name)})


def test_no_gunicorn_process_never_uses_exec_environment(tmp_path):
    with pytest.raises(probe.ProbeFailure, match="WORKER_NOT_FOUND"):
        probe.process_snapshot(tmp_path)


def test_broker_socket_cannot_invoke_canary():
    from broker import BrokerRuntime
    result = BrokerRuntime().dispatch("agent_zero_a2a_canary", {})
    assert result["failure_family"] == "INBOUND_MUTATION_FORBIDDEN"


def test_worker_discovery_reads_proc_and_rejects_divergent_context(tmp_path):
    def process(pid, parent, revision):
        folder = tmp_path / str(pid)
        folder.mkdir()
        (folder / "cmdline").write_bytes(b"gunicorn app:app")
        (folder / "status").write_text(f"PPid: {parent}\nUid: 42 42 42 42\nGid: 43 43 43 43\nGroups: 43 44\n")
        (folder / "environ").write_bytes(f"SOVEREIGN_SOURCE_REVISION={revision}".encode())
        (folder / "stat").write_text(f"{pid} (gunicorn worker) " + " ".join(["0"] * 20))
        (folder / "cwd").symlink_to(tmp_path, target_is_directory=True)
        (folder / "exe").symlink_to(Path(probe.sys.executable).resolve())
    process(70001, 1, REVISION)
    process(70002, 70001, REVISION)
    observed = probe.process_snapshot(tmp_path)
    assert observed["pid"] == 70002
    assert observed["uid"] == 42 and observed["gid"] == 43
    assert observed["groups"] == [43, 44]
    assert observed["env"]["SOVEREIGN_SOURCE_REVISION"] == REVISION
    process(70003, 70001, "different")
    with pytest.raises(probe.ProbeFailure, match="CONTEXT_DIVERGED"):
        probe.process_snapshot(tmp_path)


def test_fixed_rpc_contract_and_read_only_followup():
    from types import SimpleNamespace
    seen = []
    task = SimpleNamespace(task_id="canary-task", state="working")
    class Client:
        @classmethod
        def from_env(cls):
            return cls()
        def _post_rpc(self, payload, *, submit):
            seen.append((payload, submit))
            return {}
        def get_task(self, identity):
            seen.append(("get", identity))
            return task
    module = SimpleNamespace(AgentZeroA2AClient=Client, requests=SimpleNamespace(post=None),
                             _parse_task=lambda _: task)
    observed = probe.rpc(module, "submit", "", {})
    payload, submit = seen[0]
    assert submit is True
    assert payload["method"] == "message/send"
    assert payload["params"]["message"]["kind"] == "message"
    assert payload["params"]["configuration"] == {"blocking": False, "acceptedOutputModes": ["text", "text/plain"]}
    assert payload["params"]["message"]["parts"] == [{"kind": "text", "text": probe.PROMPT}]
    probe.rpc(module, "poll", observed["taskId"], {})
    assert seen[1] == ("get", "canary-task")
    assert module.requests.post is None


def test_probe_drops_arbitrary_exception_details(monkeypatch):
    def unavailable():
        raise RuntimeError("arbitrary process content")
    monkeypatch.setattr(probe, "process_snapshot", unavailable)
    result = probe.backend_probe("inspect", REVISION, DIGEST)
    assert result["failureFamily"] == "BACKEND_PROBE_FAILED"
    assert "arbitrary process content" not in json.dumps(result)


def test_new_tools_route_through_existing_broker(monkeypatch):
    import server
    seen = []
    monkeypatch.setattr(server.broker, "call", lambda action, arguments, **kw: seen.append((action, arguments)) or {})
    server.agent_zero_backend_diagnostics(REVISION, DIGEST)
    server.agent_zero_a2a_canary(REVISION, DIGEST, "1" * 32, "poll", True)
    assert seen[0][0] == "agent_zero_backend_diagnostics"
    assert seen[1][0] == "agent_zero_a2a_canary"
    assert seen[1][1]["action"] == "poll"
    registered = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}
    assert registered["agent_zero_backend_diagnostics"].annotations.readOnlyHint is True
    assert registered["agent_zero_a2a_canary"].annotations.readOnlyHint is False
