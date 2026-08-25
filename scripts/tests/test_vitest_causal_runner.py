from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


MODULE_PATH = Path(__file__).resolve().parents[1] / "vitest_causal_runner.py"
SPEC = importlib.util.spec_from_file_location("vitest_causal_runner", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_extracts_bounded_failed_vitest_identities_without_failure_messages(tmp_path: Path) -> None:
    test_file = tmp_path / "src" / "feature.test.ts"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("// fixture\n", encoding="utf-8")
    payload = {
        "numTotalTests": 3,
        "numPassedTests": 1,
        "numFailedTests": 1,
        "numPendingTests": 1,
        "testResults": [
            {
                "name": str(test_file),
                "assertionResults": [
                    {
                        "status": "failed",
                        "ancestorTitles": ["endpoint contract"],
                        "title": "rejects an unbound mutation",
                        "failureMessages": ["raw provider output must never be projected"],
                    },
                    {
                        "status": "failed",
                        "ancestorTitles": ["endpoint contract"],
                        "title": "keeps the executor typed",
                        "failureMessages": ["raw secret-shaped assertion detail must stay private"],
                    },
                ],
            }
        ],
    }

    result = MODULE.extract_causal_summary(payload, root=tmp_path, label="frontend smoke")

    assert result == {
        "schemaVersion": "sovereign.vitest-causal-runner.v1",
        "label": "frontend-smoke",
        "total": 3,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "causalTest": "src/feature.test.ts::endpoint-contract::rejects-an-unbound-mutation",
        "causalTests": [
            "src/feature.test.ts::endpoint-contract::rejects-an-unbound-mutation",
            "src/feature.test.ts::endpoint-contract::keeps-the-executor-typed",
        ],
    }
    assert "raw provider output" not in str(result)
    assert "raw secret-shaped assertion detail" not in str(result)


def test_derives_counts_when_top_level_counts_are_absent(tmp_path: Path) -> None:
    payload = {
        "testResults": [
            {
                "name": "tests/runtime.test.ts",
                "assertionResults": [
                    {"status": "passed", "title": "works"},
                    {"status": "failed", "title": "blocks drift"},
                    {"status": "pending", "title": "future"},
                ],
            }
        ]
    }

    result = MODULE.extract_causal_summary(payload, root=tmp_path, label="runtime")

    assert result["total"] == 3
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 1
    assert result["causalTest"] == "tests/runtime.test.ts::blocks-drift"
    assert result["causalTests"] == ["tests/runtime.test.ts::blocks-drift"]
    assert not any(character.isspace() for character in result["causalTest"])


def test_redacts_secret_shaped_test_names(tmp_path: Path) -> None:
    synthetic_secret_shape = "gh" + "p_" + ("1234567890" * 3)
    payload = {
        "numTotalTests": 1,
        "numFailedTests": 1,
        "testResults": [
            {
                "name": "tests/security.test.ts",
                "assertionResults": [
                    {
                        "status": "failed",
                        "title": f"never print {synthetic_secret_shape}",
                    }
                ],
            }
        ],
    }

    result = MODULE.extract_causal_summary(payload, root=tmp_path, label="security")

    assert synthetic_secret_shape not in str(result)
    assert "REDACTED" in str(result)
    assert " " not in str(result["causalTest"])
    assert result["causalTests"] == [result["causalTest"]]


def test_builds_shell_free_pnpm_vitest_command() -> None:
    command = MODULE.build_vitest_command(
        Path(".security-reports/vitest-frontend.json"),
        ["src/feature.test.ts", "--exclude", "**/*.e2e.test.ts"],
    )

    assert command == [
        "pnpm",
        "exec",
        "vitest",
        "run",
        "--reporter=json",
        "--outputFile=.security-reports/vitest-frontend.json",
        "src/feature.test.ts",
        "--exclude",
        "**/*.e2e.test.ts",
    ]
    assert all("&&" not in item and ";" not in item for item in command)


def test_main_emits_fallback_identity_for_nonzero_vitest_without_failed_assertion(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    raw_report_paths: list[Path] = []

    def fake_run(command, **kwargs):
        report_argument = next(item for item in command if item.startswith("--outputFile="))
        report_path = Path(report_argument.split("=", 1)[1])
        raw_report_paths.append(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({
            "numTotalTests": 5,
            "numPassedTests": 5,
            "numFailedTests": 0,
            "testResults": [],
        }), encoding="utf-8")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)

    exit_code = MODULE.main([
        "--label",
        "frontend-clients",
        "--",
        "src/client.test.ts",
    ])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "passed=5 failed=0" in output
    assert "FAILED frontend-clients::vitest_exit_1" in output
    summary = json.loads(
        (tmp_path / ".security-reports/vitest-frontend-clients-summary.json").read_text("utf-8")
    )
    assert summary == {
        "causalTest": None,
        "causalTests": [],
        "exitCode": 1,
        "failed": 0,
        "label": "frontend-clients",
        "passed": 5,
        "rawReportPersisted": False,
        "schemaVersion": "sovereign.vitest-causal-runner.v1",
        "skipped": 0,
        "status": "failed",
        "total": 5,
    }
    assert raw_report_paths and all(not path.exists() for path in raw_report_paths)


def test_main_emits_bounded_identity_when_vitest_report_is_missing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(returncode=2),
    )

    exit_code = MODULE.main([
        "--label",
        "frontend-smoke",
        "--",
        "src/smoke.test.ts",
    ])

    assert exit_code == 2
    assert capsys.readouterr().out.strip() == "FAILED frontend-smoke::vitest_report_unavailable"
    summary = json.loads(
        (tmp_path / ".security-reports/vitest-frontend-smoke-summary.json").read_text("utf-8")
    )
    assert summary["status"] == "report-unavailable"
    assert summary["exitCode"] == 2
    assert summary["rawReportPersisted"] is False


def test_runner_source_does_not_emit_raw_vitest_output() -> None:
    source = MODULE_PATH.read_text("utf-8")

    assert "stdout=subprocess.DEVNULL" in source
    assert "stderr=subprocess.DEVNULL" in source
    assert "shell=True" not in source
    assert "failureMessages" not in source
