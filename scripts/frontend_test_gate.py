#!/usr/bin/env python3
"""Shell-free frontend contract, regression and smoke-test orchestrator.

The existing release workflow invokes the package scripts and captures their stdout
in a bounded artifact. This orchestrator replaces nested npm/shell chains with a
fixed sequence of subprocess argument vectors. Every failed stage preserves its
original exit code and emits either a causal ``FAILED file::test`` line supplied by
the bounded Vitest runner or a fixed stage identity understood by Sovereign's
revision-bound workflow failure extractor.

Raw compiler, Pytest and Vitest stderr/stdout are never replayed. This module is
test evidence only; it grants no product, consent, deployment or runtime authority.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence

SCHEMA_VERSION = "sovereign.frontend-test-gate.v1"
DEFAULT_TIMEOUT_SECONDS = 900
_MAX_SAFE_LINE = 420
_MAX_FORWARDED_CAUSAL_LINES = 32
_COUNT_LABELS = ("failed", "passed", "skipped")
_FAILURE_IDENTITY_RE = re.compile(r"^[A-Za-z0-9._/:-]{1,320}$")
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)


@dataclass(frozen=True)
class GateStage:
    name: str
    command: tuple[str, ...]
    failure_identity: str
    forward_causal_output: bool = False


def _redact(value: object) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:_MAX_SAFE_LINE]


def _last_count(text: str, label: str) -> int:
    matches = re.findall(rf"(?<![A-Za-z0-9_=])(\d+)\s+{re.escape(label)}\b", text, re.I)
    return int(matches[-1]) if matches else 0


def _structured_vitest_count(text: str, label: str) -> int | None:
    matches = re.findall(
        rf"^SOVEREIGN_VITEST_SUMMARY\s+[^\r\n]*\b{re.escape(label)}=(\d+)\b",
        text,
        re.I | re.M,
    )
    return int(matches[-1]) if matches else None


def _count_summary(text: str) -> tuple[int, int, int]:
    counts: list[int] = []
    for label in _COUNT_LABELS:
        structured = _structured_vitest_count(text, label)
        counts.append(structured if structured is not None else _last_count(text, label))
    return tuple(counts)  # type: ignore[return-value]


def _causal_lines(text: str) -> tuple[str, ...]:
    output: list[str] = []
    for raw in str(text or "").splitlines():
        line = _redact(raw)
        if line.startswith("SOVEREIGN_VITEST_SUMMARY "):
            output.append(line)
            continue
        match = re.match(r"^(?:FAILED|ERROR)\s+([^\s]+)", line)
        if match:
            token = match.group(1)
            if _FAILURE_IDENTITY_RE.fullmatch(token):
                output.append(f"FAILED {token}")
    return tuple(output[:_MAX_FORWARDED_CAUSAL_LINES])


def _emit_failure(identity: str) -> None:
    token = _redact(identity)
    if not _FAILURE_IDENTITY_RE.fullmatch(token):
        token = "frontend-test-gate::invalid-failure-identity"
    print(f"FAILED {token}")
    print(
        '<testsuite tests="1" failures="1" errors="0" skipped="0">'
        f'<testcase name="{token}"><failure message="bounded-stage-failure"/></testcase>'
        '</testsuite>'
    )


def _python_stage_command(python: str, *args: str) -> tuple[str, ...]:
    return (python, *args)


def build_stages(mode: str, *, python_executable: str | None = None) -> tuple[GateStage, ...]:
    python = python_executable or sys.executable
    endpoint_test_files = (
        "scripts/tests/test_frontend_endpoint_contracts.py",
        "scripts/tests/test_vitest_causal_runner.py",
        "scripts/tests/test_frontend_test_gate.py",
    )
    client_test_files = (
        "src/features/admin/api/adminApiClient.ownerInput.test.ts",
        "src/features/billing/billingSlice.test.ts",
        "src/features/knowledge/knowledgeApi.test.ts",
        "src/features/rescue/rescueClient.test.ts",
        "src/features/toolchain/toolchainApi.test.ts",
        "src/features/toolchain/skillsApi.test.ts",
    )
    python_regression_stage = GateStage(
        name="endpoint-python-regressions",
        command=_python_stage_command(
            python,
            "-m",
            "pytest",
            *endpoint_test_files,
            "-q",
        ),
        failure_identity="scripts/tests::frontend_endpoint_python",
        forward_causal_output=True,
    )
    if mode == "python":
        return (python_regression_stage,)

    stages: list[GateStage] = [
        GateStage(
            name="endpoint-contract-compiler",
            command=_python_stage_command(
                python,
                "scripts/frontend_endpoint_contracts.py",
                "--check",
            ),
            failure_identity="scripts/frontend_endpoint_contracts.py::repository_contract",
        ),
        GateStage(
            name="endpoint-client-vitest",
            command=_python_stage_command(
                python,
                "scripts/vitest_causal_runner.py",
                "--label",
                "frontend-endpoint-clients",
                "--",
                *client_test_files,
            ),
            failure_identity="frontend-endpoint-clients::vitest_runner",
            forward_causal_output=True,
        ),
    ]
    if mode == "smoke":
        stages.append(
            GateStage(
                name="frontend-broad-smoke",
                command=_python_stage_command(
                    python,
                    "scripts/vitest_causal_runner.py",
                    "--label",
                    "frontend-smoke",
                    "--",
                    "--exclude",
                    "**/*.chat.test.ts",
                    "--exclude",
                    "**/*.integration.test.ts",
                    "--exclude",
                    "**/*.e2e.test.ts",
                    "--exclude",
                    "**/*.spec.ts",
                    "--exclude",
                    "**/*.sequential.test.ts",
                    "--exclude",
                    "**/ChatSidebar.test.tsx",
                    "--exclude",
                    "**/e2e/**",
                    "--exclude",
                    "**/api-fallback/**",
                    "--exclude",
                    "scripts/sovereign-agent-release-gate.test.mjs",
                    "--exclude",
                    "scripts/required-gate-priority.contract.test.cjs",
                    "--exclude",
                    "scripts/revision-guardian.contract.test.cjs",
                    "--exclude",
                    "scripts/neuro-architecture-graph.test.mjs",
                ),
                failure_identity="frontend-smoke::vitest_runner",
                forward_causal_output=True,
            )
        )
    return tuple(stages)


def run_stage(stage: GateStage, *, root: Path, timeout_seconds: int) -> int:
    try:
        completed = subprocess.run(
            list(stage.command),
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        exit_code = int(completed.returncode)
    except FileNotFoundError:
        print(
            f"SOVEREIGN_FRONTEND_GATE_STAGE schema={SCHEMA_VERSION} "
            f"stage={stage.name} status=failed exitCode=127"
        )
        _emit_failure(stage.failure_identity)
        return 127
    except subprocess.TimeoutExpired:
        print(
            f"SOVEREIGN_FRONTEND_GATE_STAGE schema={SCHEMA_VERSION} "
            f"stage={stage.name} status=failed exitCode=124"
        )
        _emit_failure(stage.failure_identity)
        return 124

    combined = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    failed, passed, skipped = _count_summary(combined)
    status = "passed" if exit_code == 0 else "failed"
    print(
        f"SOVEREIGN_FRONTEND_GATE_STAGE schema={SCHEMA_VERSION} "
        f"stage={stage.name} status={status} exitCode={exit_code} "
        f"failed={failed} passed={passed} skipped={skipped}"
    )

    forwarded = _causal_lines(combined) if stage.forward_causal_output else ()
    failure_emitted = False
    for line in forwarded:
        if line.startswith("FAILED "):
            _emit_failure(line.split(None, 1)[1])
            failure_emitted = True
        else:
            print(line)
    if exit_code != 0 and not failure_emitted:
        _emit_failure(stage.failure_identity)
    return exit_code


def _arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("endpoint", "smoke", "python"), required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(list(argv))
    if not 1 <= args.timeout_seconds <= 1800:
        parser.error("--timeout-seconds must be in 1..1800")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv if argv is not None else sys.argv[1:])
    root = Path.cwd().resolve()
    for stage in build_stages(args.mode):
        exit_code = run_stage(stage, root=root, timeout_seconds=args.timeout_seconds)
        if exit_code != 0:
            return exit_code
    print(
        f"SOVEREIGN_FRONTEND_GATE_COMPLETE schema={SCHEMA_VERSION} "
        f"mode={args.mode} status=passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
