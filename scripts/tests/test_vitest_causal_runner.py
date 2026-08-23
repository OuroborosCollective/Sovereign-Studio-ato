from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "vitest_causal_runner.py"
SPEC = importlib.util.spec_from_file_location("vitest_causal_runner", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_extracts_first_failed_vitest_identity_without_failure_message(tmp_path: Path) -> None:
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
                    }
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
        "causalTest": "src/feature.test.ts::endpoint contract > rejects an unbound mutation",
    }
    assert "raw provider output" not in str(result)


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
    assert result["causalTest"] == "tests/runtime.test.ts::blocks drift"


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
    assert "[REDACTED]" in str(result)


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


def test_runner_source_does_not_emit_raw_vitest_output() -> None:
    source = MODULE_PATH.read_text("utf-8")

    assert "stdout=subprocess.DEVNULL" in source
    assert "stderr=subprocess.DEVNULL" in source
    assert "shell=True" not in source
    assert "failureMessages" not in source
