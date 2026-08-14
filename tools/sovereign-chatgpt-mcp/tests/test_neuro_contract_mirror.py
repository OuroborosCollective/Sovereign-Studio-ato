from __future__ import annotations

import hashlib
from pathlib import Path


def test_all_neuro_contract_deployment_mirrors_are_byte_identical() -> None:
    repository = Path(__file__).resolve().parents[3]
    paths = (
        repository / "backend" / "agent_runtime" / "neuro_architecture_contract.py",
        repository / "scripts" / "sovereign-backend" / "agent_runtime" / "neuro_architecture_contract.py",
        repository / "tools" / "sovereign-chatgpt-mcp" / "neuro_architecture_contract.py",
    )
    contents = [path.read_bytes() for path in paths]

    assert len(set(contents)) == 1
    assert {
        hashlib.sha256(content).hexdigest()
        for content in contents
    } == {"a0100124767fba2718ee967ce208941f10abbe915db9f452aae87cbad4ede625"}
