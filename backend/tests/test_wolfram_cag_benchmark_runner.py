"""Tests for the reproducible public Wolfram CAG benchmark runner (#1464).

These tests execute the *real* runner at ``scripts/run-wolfram-cag-benchmark.py``
as a subprocess and assert the documented truth boundary:

- every public benchmark case runs through the real verifier;
- the live transport path is honestly ``UNAVAILABLE`` (no fake SUPPORTED);
- the deterministic comparison verdict matches each case's expected verdict;
- emitted receipts are secret-free and carry the ``unavailable_no_transport_receipt``
  finding code;
- the runner exits non-zero on any verdict mismatch, secret leak or transport
  regression.

The runner imports the real live-path modules; no logic is copied here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _REPO_ROOT / "scripts" / "run-wolfram-cag-benchmark.py"


def _run_runner(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    run_env = {**os.environ, **(env or {})}
    run_env.setdefault("SOVEREIGN_CAG_RUN_ID", "pytest-benchmark-run")
    run_env.setdefault("SOVEREIGN_CAG_REVISION", "0" * 40)
    return subprocess.run(
        [sys.executable, str(_RUNNER), *args],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=run_env,
    )


def _parse_json(proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode == 0, f"runner failed: {proc.stderr}\n{proc.stdout}"
    return json.loads(proc.stdout)


class TestRunnerIsExecutable:
    def test_runner_path_exists(self) -> None:
        assert _RUNNER.is_file(), f"runner missing at {_RUNNER}"

    def test_all_cases_exit_zero(self) -> None:
        proc = _run_runner("--json")
        assert proc.returncode == 0, f"runner exited {proc.returncode}: {proc.stderr}"
        payload = json.loads(proc.stdout)
        assert payload["caseCount"] >= 10, payload["caseCount"]


class TestHonestUnavailableTransport:
    def test_transport_status_is_unavailable(self) -> None:
        payload = _parse_json(_run_runner("--json"))
        assert payload["transportProvisioned"] is False
        assert payload["transportStatus"] == "UNAVAILABLE"
        assert "#1458" in payload["provisioningBlocker"]

    def test_every_case_transport_verdict_unavailable(self) -> None:
        payload = _parse_json(_run_runner("--json"))
        for case in payload["cases"]:
            assert case["transport_verdict"] == "UNAVAILABLE", case["case_id"]
            receipt = case["transport_receipt"]
            assert receipt["verdict"] == "UNAVAILABLE", case["case_id"]
            assert "unavailable_no_transport_receipt" in receipt["finding_codes"], case["case_id"]

    def test_no_succeeded_or_contradicted_transport_verdict(self) -> None:
        """Without #1458 provisioning, no case may reach a SUPPORTED/CONTRADICTED
        transport verdict. Only the honest UNAVAILABLE path is permitted."""
        payload = _parse_json(_run_runner("--json"))
        for case in payload["cases"]:
            assert case["transport_verdict"] not in {"SUPPORTED", "CONTRADICTED"}, case["case_id"]


class TestDeterministicComparisonVerdict:
    def test_comparison_matches_expected(self) -> None:
        payload = _parse_json(_run_runner("--json"))
        assert payload["verdictMismatches"] == [], payload["verdictMismatches"]
        for case in payload["cases"]:
            assert case["comparison_verdict"] == case["expected_comparison_verdict"], case["case_id"]

    def test_at_least_one_supported_contradicted_inconclusive(self) -> None:
        payload = _parse_json(_run_runner("--json"))
        verdicts = {c["comparison_verdict"] for c in payload["cases"]}
        assert {"SUPPORTED", "CONTRADICTED", "INCONCLUSIVE"} <= verdicts, verdicts


class TestSecretFreeReceipts:
    def test_no_secret_markers_in_receipts(self) -> None:
        """Receipt values must not contain secret-shaped markers.

        Scans receipt *values* only (not structural key names), mirroring the
        runner's own ``_verify_no_secret_markers`` check.
        """
        secret_markers = (
            "password", "passwd", "token", "authorization",
            "api_key", "apikey", "private_key", "client_secret", "cookie",
            "raw_prompt", "prompt_text", "file_content", "database_row",
        )
        payload = _parse_json(_run_runner("--json"))
        assert payload["secretFindings"] == [], payload["secretFindings"]

        def _walk(obj):
            if isinstance(obj, str):
                folded = obj.casefold()
                return [m for m in secret_markers if m in folded]
            if isinstance(obj, dict):
                out = []
                for v in obj.values():
                    out.extend(_walk(v))
                return out
            if isinstance(obj, (list, tuple)):
                out = []
                for v in obj:
                    out.extend(_walk(v))
                return out
            return []

        leaked: list[str] = []
        for case in payload["cases"]:
            leaked.extend(_walk(case["transport_receipt"]))
        assert not leaked, f"secret markers leaked in receipts: {leaked}"


class TestSingleCaseMode:
    def test_case_flag_runs_one_case(self) -> None:
        proc = _run_runner("--json", "--case", "cag-bench-001")
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["caseCount"] == 1
        assert payload["cases"][0]["case_id"] == "cag-bench-001"

    def test_unknown_case_exits_non_zero(self) -> None:
        proc = _run_runner("--json", "--case", "does-not-exist")
        assert proc.returncode != 0
        err = json.loads(proc.stdout)
        assert "error" in err


class TestDeterministicReplay:
    def test_two_runs_produce_identical_receipts(self) -> None:
        env = {
            "SOVEREIGN_CAG_RUN_ID": "replay-fixed",
            "SOVEREIGN_CAG_REVISION": "0" * 40,
            "SOVEREIGN_CAG_RECORDED_AT": "",
        }
        first = _parse_json(_run_runner("--json", env=env))
        second = _parse_json(_run_runner("--json", env=env))
        for a, b in zip(first["cases"], second["cases"]):
            assert a["transport_receipt"]["receipt_sha256"] == b["transport_receipt"]["receipt_sha256"], a["case_id"]
