"""Contract tests for the Wolfram CAG developer quickstart (#1465).

These tests bind the quickstart documentation to the real implementation so
the quickstart stays revision-bound and fails on contract changes:

- every command documented in ``docs/WOLFRAM_CAG_QUICKSTART.md`` actually
  executes against the real runner/generator scripts;
- the three checked-in example receipts are byte-identical to a fresh
  deterministic regeneration (``--check`` gate);
- every example receipt is schema-valid, secret-free and honestly
  ``UNAVAILABLE`` on the transport path while carrying the comparison verdict
  its file name promises;
- every case id and receipt file referenced by the doc exists.

The tests run the real scripts as subprocesses; no logic is copied here.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_QUICKSTART_DOC = _REPO_ROOT / "docs" / "WOLFRAM_CAG_QUICKSTART.md"
_GENERATOR = _REPO_ROOT / "scripts" / "generate-wolfram-cag-quickstart-receipts.py"
_RUNNER = _REPO_ROOT / "scripts" / "run-wolfram-cag-benchmark.py"
_EXAMPLES_DIR = _REPO_ROOT / "docs" / "examples" / "wolfram-cag"
_ISSUE_TEMPLATE = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "wolfram-cag-public-case.md"

_SECRET_MARKERS = (
    "password", "passwd", "token", "authorization",
    "api_key", "apikey", "private_key", "client_secret", "cookie",
    "raw_prompt", "prompt_text", "file_content", "database_row",
)

# Real credential *value* shapes for prose scanning. Keyword markers are only
# applied to receipt JSON values; prose must be allowed to forbid "tokens".
_SECRET_VALUE_PATTERNS = (
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"sk-[A-Za-z0-9_-]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)

_EXPECTED_EXAMPLES = {
    "quickstart-supported.receipt.json": ("cag-bench-001", "SUPPORTED"),
    "quickstart-contradicted.receipt.json": ("cag-bench-002", "CONTRADICTED"),
    "quickstart-inconclusive.receipt.json": ("cag-bench-012", "INCONCLUSIVE"),
}


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env={**os.environ},
    )


def _walk_secret_markers(obj) -> list[str]:
    if isinstance(obj, str):
        folded = obj.casefold()
        return [m for m in _SECRET_MARKERS if m in folded]
    if isinstance(obj, dict):
        out: list[str] = []
        for value in obj.values():
            out.extend(_walk_secret_markers(value))
        return out
    if isinstance(obj, (list, tuple)):
        out = []
        for value in obj:
            out.extend(_walk_secret_markers(value))
        return out
    return []


class TestQuickstartDoc:
    def test_doc_exists(self) -> None:
        assert _QUICKSTART_DOC.is_file(), f"missing {_QUICKSTART_DOC}"

    def test_doc_references_real_files(self) -> None:
        text = _QUICKSTART_DOC.read_text(encoding="utf-8")
        for referenced in (
            "scripts/run-wolfram-cag-benchmark.py",
            "scripts/generate-wolfram-cag-quickstart-receipts.py",
            "backend/agent_runtime/wolfram_cag_benchmark_cases.py",
            ".github/ISSUE_TEMPLATE/wolfram-cag-public-case.md",
        ):
            assert referenced in text, f"doc missing reference to {referenced}"
            assert (_REPO_ROOT / referenced).is_file(), f"referenced file missing: {referenced}"

    def test_doc_references_all_example_receipts(self) -> None:
        text = _QUICKSTART_DOC.read_text(encoding="utf-8")
        for name in _EXPECTED_EXAMPLES:
            assert name in text, f"doc missing example receipt {name}"
            assert (_EXAMPLES_DIR / name).is_file(), f"example receipt missing: {name}"

    def test_doc_case_ids_exist_in_benchmark_fixtures(self) -> None:
        sys.path.insert(0, str(_REPO_ROOT / "backend"))
        try:
            from agent_runtime.wolfram_cag_benchmark_cases import BENCHMARK_CASES
        finally:
            sys.path.remove(str(_REPO_ROOT / "backend"))
        known = {case.case_id for case in BENCHMARK_CASES}
        text = _QUICKSTART_DOC.read_text(encoding="utf-8")
        for case_id in set(re.findall(r"cag-bench-\d{3}", text)):
            assert case_id in known, f"doc references unknown case {case_id}"

    def test_doc_has_no_secret_values(self) -> None:
        """Prose may forbid tokens/passwords; real credential values must not appear."""
        text = _QUICKSTART_DOC.read_text(encoding="utf-8")
        for pattern in _SECRET_VALUE_PATTERNS:
            assert not re.search(pattern, text), f"secret-shaped value in doc: {pattern}"


class TestDocumentedCommandsExecute:
    def test_single_case_command(self) -> None:
        proc = _run(_RUNNER, "--case", "cag-bench-001")
        assert proc.returncode == 0, proc.stderr

    def test_all_cases_command(self) -> None:
        proc = _run(_RUNNER)
        assert proc.returncode == 0, proc.stderr

    def test_json_command(self) -> None:
        proc = _run(_RUNNER, "--json")
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["caseCount"] >= 10

    def test_generator_check_command(self) -> None:
        proc = _run(_GENERATOR, "--check")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


class TestExampleReceipts:
    def test_exactly_three_checked_in_receipts(self) -> None:
        files = sorted(p.name for p in _EXAMPLES_DIR.glob("*.receipt.json"))
        assert files == sorted(_EXPECTED_EXAMPLES), files

    def test_receipts_are_in_sync_with_regeneration(self) -> None:
        proc = _run(_GENERATOR, "--check")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_receipt_shape_and_verdicts(self) -> None:
        for name, (case_id, comparison) in _EXPECTED_EXAMPLES.items():
            payload = json.loads((_EXAMPLES_DIR / name).read_text(encoding="utf-8"))
            assert payload["schemaVersion"] == "sovereign.wolfram-cag-quickstart-example.v1", name
            assert payload["case_id"] == case_id, name
            assert payload["comparison_verdict"] == comparison, name
            assert payload["transport_verdict"] == "UNAVAILABLE", name
            receipt = payload["transport_receipt"]
            assert receipt["schema_version"] == "sovereign.wolfram-cag-receipt.v1", name
            assert receipt["verdict"] == "UNAVAILABLE", name
            assert "unavailable_no_transport_receipt" in receipt["finding_codes"], name
            assert receipt["runtime_revision"] == "0" * 40, name
            assert receipt["recorded_at"] == "", name
            assert re.fullmatch(r"[0-9a-f]{64}", receipt["receipt_sha256"]), name

    def test_receipts_are_secret_free(self) -> None:
        for name in _EXPECTED_EXAMPLES:
            payload = json.loads((_EXAMPLES_DIR / name).read_text(encoding="utf-8"))
            leaked = _walk_secret_markers(payload)
            assert not leaked, f"secret markers in {name}: {leaked}"


class TestIssueTemplate:
    def test_template_exists_and_forbids_secrets(self) -> None:
        assert _ISSUE_TEMPLATE.is_file(), f"missing {_ISSUE_TEMPLATE}"
        text = _ISSUE_TEMPLATE.read_text(encoding="utf-8")
        assert "cag-bench-" in text
        assert "verdict" in text.casefold()
