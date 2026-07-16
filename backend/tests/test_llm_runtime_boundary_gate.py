from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "llm-runtime-boundary-gate.mjs"


def test_llm_runtime_boundary_gate_reports_no_contract_violation() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed in this local validation environment")

    result = subprocess.run(
        [node, str(GATE)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, (
        "LLM/runtime boundary gate failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
