#!/usr/bin/env python3
"""Run Vitest with bounded, machine-readable causal failure evidence.

The wrapper never returns raw test stdout/stderr. Vitest writes its raw JSON
reporter into an automatically deleted temporary directory; this script persists
only a redacted aggregate summary and emits the first failed ``file::test``
identity in the Pytest-compatible form already understood by Sovereign's
revision-bound workflow failure extractor.

This is test evidence only. It grants no runtime, consent or effect authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "sovereign.vitest-causal-runner.v1"
DEFAULT_TIMEOUT_SECONDS = 900
_MAX_IDENTITY = 320
_SAFE_LABEL_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_IDENTITY_RE = re.compile(r"[^A-Za-z0-9._/:-]+")
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)


def _bounded_text(value: object, maximum: int = _MAX_IDENTITY) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:maximum] or "unknown"


def _safe_label(value: object) -> str:
    label = _SAFE_LABEL_RE.sub("-", str(value or "").strip()).strip("-._")
    return label[:80] or "vitest"


def _identity_token(value: object, maximum: int = _MAX_IDENTITY) -> str:
    redacted = _bounded_text(value, maximum)
    token = _SAFE_IDENTITY_RE.sub("-", redacted).strip("-._:")
    return token[:maximum] or "unknown"


def _integer(value: object) -> int:
    return int(value) if isinstance(value, int) and value >= 0 else 0


def _relative_test_path(value: object, root: Path) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "vitest"
    path = Path(raw)
    try:
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        relative = resolved.relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        relative = path.name or "vitest"
    return _identity_token(relative, 240)


def _assertions(test_result: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    values = test_result.get("assertionResults")
    if not isinstance(values, list):
        return ()
    return tuple(item for item in values if isinstance(item, Mapping))


def extract_causal_summary(payload: Mapping[str, Any], *, root: Path, label: str) -> dict[str, Any]:
    """Return bounded counts and the first failed test identity from Vitest JSON."""

    total = _integer(payload.get("numTotalTests"))
    passed = _integer(payload.get("numPassedTests"))
    failed = _integer(payload.get("numFailedTests"))
    skipped = _integer(payload.get("numPendingTests")) + _integer(payload.get("numTodoTests"))
    causal: str | None = None

    raw_results = payload.get("testResults")
    results = raw_results if isinstance(raw_results, list) else []
    if not total:
        assertions = [
            assertion
            for result in results
            if isinstance(result, Mapping)
            for assertion in _assertions(result)
        ]
        total = len(assertions)
        failed = sum(str(item.get("status") or "").casefold() == "failed" for item in assertions)
        skipped = sum(str(item.get("status") or "").casefold() in {"pending", "skipped", "todo", "disabled"} for item in assertions)
        passed = max(0, total - failed - skipped)

    for result in results:
        if not isinstance(result, Mapping):
            continue
        file_name = _relative_test_path(result.get("name") or result.get("testFilePath"), root)
        for assertion in _assertions(result):
            if str(assertion.get("status") or "").casefold() != "failed":
                continue
            ancestor = assertion.get("ancestorTitles")
            parts = [
                _identity_token(item, 120)
                for item in ancestor
                if str(item or "").strip()
            ] if isinstance(ancestor, list) else []
            title = _identity_token(
                assertion.get("title") or assertion.get("fullName") or assertion.get("name"),
                180,
            )
            causal = "::".join([file_name, *parts, title])[:_MAX_IDENTITY]
            break
        if causal:
            break

    return {
        "schemaVersion": SCHEMA_VERSION,
        "label": _safe_label(label),
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "causalTest": causal,
    }


def build_vitest_command(report_path: Path, vitest_args: Sequence[str]) -> list[str]:
    """Build a shell-free command vector; user input never becomes shell syntax."""

    return [
        "pnpm",
        "exec",
        "vitest",
        "run",
        "--reporter=json",
        f"--outputFile={report_path.as_posix()}",
        *vitest_args,
    ]


def _arguments(argv: Sequence[str]) -> tuple[argparse.Namespace, list[str]]:
    values = list(argv)
    separator = values.index("--") if "--" in values else len(values)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parsed = parser.parse_args(values[:separator])
    vitest_args = values[separator + 1 :] if separator < len(values) else []
    if not vitest_args:
        parser.error("Vitest arguments are required after --")
    if not 1 <= parsed.timeout_seconds <= 1800:
        parser.error("--timeout-seconds must be in 1..1800")
    return parsed, vitest_args


def _write_summary(path: Path, summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(summary), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args, vitest_args = _arguments(argv if argv is not None else sys.argv[1:])
    root = Path.cwd().resolve()
    label = _safe_label(args.label)
    summary_path = (
        Path(args.report)
        if args.report
        else Path(".security-reports") / f"vitest-{label}-summary.json"
    )
    if not summary_path.is_absolute():
        summary_path = root / summary_path
    summary_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"sovereign-vitest-{label}-") as temporary:
        raw_report_path = Path(temporary) / "vitest-raw.json"
        command = build_vitest_command(raw_report_path, vitest_args)
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=args.timeout_seconds,
            )
            exit_code = int(completed.returncode)
        except FileNotFoundError:
            print(f"FAILED {label}::vitest_runner_unavailable")
            return 127
        except subprocess.TimeoutExpired:
            print(f"FAILED {label}::vitest_timeout")
            return 124

        try:
            raw = json.loads(raw_report_path.read_text("utf-8"))
            if not isinstance(raw, Mapping):
                raise ValueError("Vitest JSON report must be an object")
            summary = extract_causal_summary(raw, root=root, label=label)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            failure_summary = {
                "schemaVersion": SCHEMA_VERSION,
                "label": label,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "causalTest": None,
                "exitCode": exit_code,
                "status": "report-unavailable",
                "rawReportPersisted": False,
            }
            _write_summary(summary_path, failure_summary)
            print(f"FAILED {label}::vitest_report_unavailable")
            return exit_code or 1

    persisted_summary = {
        **summary,
        "exitCode": exit_code,
        "status": "passed" if exit_code == 0 and int(summary["failed"]) == 0 else "failed",
        "rawReportPersisted": False,
    }
    _write_summary(summary_path, persisted_summary)

    print(
        "SOVEREIGN_VITEST_SUMMARY "
        f"label={summary['label']} total={summary['total']} passed={summary['passed']} "
        f"failed={summary['failed']} skipped={summary['skipped']} exitCode={exit_code}"
    )
    causal = summary.get("causalTest")
    if causal:
        print(f"FAILED {causal}")
    elif exit_code != 0 or int(summary["failed"]) > 0:
        print(f"FAILED {label}::vitest_exit_{exit_code}")

    return exit_code if exit_code != 0 else (1 if int(summary["failed"]) > 0 else 0)


if __name__ == "__main__":
    raise SystemExit(main())
