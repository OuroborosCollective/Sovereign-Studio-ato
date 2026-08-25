from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


MODULE_PATH = Path(__file__).resolve().parents[1] / "frontend_test_gate.py"
SPEC = importlib.util.spec_from_file_location("frontend_test_gate", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_endpoint_mode_has_fixed_shell_free_stage_order() -> None:
    stages = MODULE.build_stages("endpoint", python_executable="python3")

    assert [stage.name for stage in stages] == [
        "endpoint-contract-compiler",
        "endpoint-client-vitest",
    ]
    assert stages[0].command == (
        "python3",
        "scripts/frontend_endpoint_contracts.py",
        "--check",
    )
    assert stages[1].command[:5] == (
        "python3",
        "scripts/vitest_causal_runner.py",
        "--label",
        "frontend-endpoint-clients",
        "--",
    )
    assert all("&&" not in item and ";" not in item for stage in stages for item in stage.command)


def test_python_mode_is_explicit_and_kept_out_of_node_only_release_jobs() -> None:
    stages = MODULE.build_stages("python", python_executable="python3")

    assert [stage.name for stage in stages] == ["endpoint-python-regressions"]
    assert stages[0].command[:4] == (
        "python3",
        "-m",
        "pytest",
        "scripts/tests/test_frontend_endpoint_contracts.py",
    )
    assert "scripts/tests/test_frontend_test_gate.py" in stages[0].command
    assert stages[0].forward_causal_output is True


def test_smoke_mode_adds_broad_frontend_stage_with_existing_exclusions() -> None:
    stages = MODULE.build_stages("smoke", python_executable="python3")

    assert [stage.name for stage in stages][-1] == "frontend-broad-smoke"
    broad = stages[-1]
    assert broad.failure_identity == "frontend-smoke::vitest_runner"
    assert broad.forward_causal_output is True
    assert "**/*.e2e.test.ts" in broad.command
    assert "**/ChatSidebar.test.tsx" in broad.command
    assert "scripts/revision-guardian.contract.test.cjs" in broad.command


def test_successful_stage_emits_only_bounded_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="23 passed in 1.2s\nraw diagnostic detail that must not be replayed\n",
            stderr="unrelated stderr detail",
        ),
    )
    stage = MODULE.GateStage(
        name="python-regressions",
        command=("python3", "-m", "pytest"),
        failure_identity="scripts/tests::frontend_python",
    )

    exit_code = MODULE.run_stage(stage, root=tmp_path, timeout_seconds=30)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "status=passed" in output
    assert "passed=23" in output
    assert "raw diagnostic detail" not in output
    assert "stderr detail" not in output
    assert "FAILED " not in output


def test_failed_non_causal_stage_preserves_exit_and_emits_fixed_identity(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=7,
            stdout="compiler rejected contract\n",
            stderr="bounded detail not projected",
        ),
    )
    stage = MODULE.GateStage(
        name="compiler",
        command=("python3", "compiler.py"),
        failure_identity="compiler.py::repository_contract",
    )

    exit_code = MODULE.run_stage(stage, root=tmp_path, timeout_seconds=30)

    output = capsys.readouterr().out
    assert exit_code == 7
    assert "status=failed exitCode=7" in output
    assert "FAILED compiler.py::repository_contract" in output
    assert '<testcase name="compiler.py::repository_contract">' in output
    assert '<failure message="bounded-stage-failure"/>' in output
    assert "compiler rejected contract" not in output


def test_pytest_stage_extracts_precise_failure_token_without_replaying_message(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=(
                "........F\n"
                "FAILED scripts/tests/test_frontend_endpoint_contracts.py::test_current_repository_has_no_active_frontend_backend_contract_gap - AssertionError: bounded detail\n"
                "1 failed, 30 passed in 1.0s\n"
            ),
            stderr="raw traceback must not be replayed",
        ),
    )
    stage = MODULE.GateStage(
        name="endpoint-python-regressions",
        command=("python3", "-m", "pytest"),
        failure_identity="scripts/tests::frontend_endpoint_python",
        forward_causal_output=True,
    )

    exit_code = MODULE.run_stage(stage, root=tmp_path, timeout_seconds=30)

    output = capsys.readouterr().out
    token = "scripts/tests/test_frontend_endpoint_contracts.py::test_current_repository_has_no_active_frontend_backend_contract_gap"
    assert exit_code == 1
    assert "failed=1 passed=30" in output
    assert f"FAILED {token}" in output
    assert f'<testcase name="{token}">' in output
    assert "FAILED scripts/tests::frontend_endpoint_python" not in output
    assert "AssertionError" not in output
    assert "traceback" not in output


def test_causal_stage_forwards_only_safe_summary_and_failed_identity(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=(
                "SOVEREIGN_VITEST_SUMMARY label=clients total=6 passed=5 failed=1 skipped=0 exitCode=1\n"
                "FAILED src/client.test.ts::blocks-unbound-write\n"
                "raw assertion body must not be forwarded\n"
            ),
            stderr="raw stack trace",
        ),
    )
    stage = MODULE.GateStage(
        name="client-vitest",
        command=("python3", "scripts/vitest_causal_runner.py"),
        failure_identity="clients::vitest_runner",
        forward_causal_output=True,
    )

    exit_code = MODULE.run_stage(stage, root=tmp_path, timeout_seconds=30)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "SOVEREIGN_VITEST_SUMMARY" in output
    assert "FAILED src/client.test.ts::blocks-unbound-write" in output
    assert '<testcase name="src/client.test.ts::blocks-unbound-write">' in output
    assert "FAILED clients::vitest_runner" not in output
    assert '<testcase name="clients::vitest_runner">' not in output
    assert "raw assertion body" not in output
    assert "stack trace" not in output


def test_causal_stage_forwards_multiple_bounded_failed_identities(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    identities = [f"src/feature-{index}.test.ts::case-{index}" for index in range(16)]
    stdout = "\n".join([
        "SOVEREIGN_VITEST_SUMMARY label=frontend total=32 passed=16 failed=16 skipped=0 exitCode=1",
        *(f"FAILED {identity}" for identity in identities),
        "raw assertion body must remain private",
    ])
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=stdout,
            stderr="raw stack trace",
        ),
    )
    stage = MODULE.GateStage(
        name="frontend-vitest",
        command=("python3", "scripts/vitest_causal_runner.py"),
        failure_identity="frontend::vitest_runner",
        forward_causal_output=True,
    )

    exit_code = MODULE.run_stage(stage, root=tmp_path, timeout_seconds=30)

    output = capsys.readouterr().out
    assert exit_code == 1
    for identity in identities:
        assert f"FAILED {identity}" in output
    assert "raw assertion body" not in output
    assert "raw stack trace" not in output


def test_main_stops_at_first_failed_stage(monkeypatch, capsys) -> None:
    stages = (
        MODULE.GateStage("one", ("one",), "one::failed"),
        MODULE.GateStage("two", ("two",), "two::failed"),
        MODULE.GateStage("three", ("three",), "three::failed"),
    )
    executed: list[str] = []
    monkeypatch.setattr(MODULE, "build_stages", lambda mode: stages)

    def fake_run_stage(stage, **kwargs):
        executed.append(stage.name)
        return 9 if stage.name == "two" else 0

    monkeypatch.setattr(MODULE, "run_stage", fake_run_stage)

    exit_code = MODULE.main(["--mode", "smoke"])

    assert exit_code == 9
    assert executed == ["one", "two"]
    assert "SOVEREIGN_FRONTEND_GATE_COMPLETE" not in capsys.readouterr().out


def test_gate_source_never_executes_through_a_shell() -> None:
    source = MODULE_PATH.read_text("utf-8")

    assert "shell=True" not in source
    assert "stdout=subprocess.PIPE" in source
    assert "stderr=subprocess.PIPE" in source
    assert "stdin=subprocess.DEVNULL" in source
    assert '<testsuite tests="1" failures="1"' in source
    assert 'bounded-stage-failure' in source
