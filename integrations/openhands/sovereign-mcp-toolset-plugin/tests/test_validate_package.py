from __future__ import annotations

import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_package.py"
SPEC = importlib.util.spec_from_file_location("validate_openhands_plugin_package", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def test_repository_only_package_contract(capsys) -> None:
    assert VALIDATOR.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["state"] == "repository-only-inactive-preview"
    assert payload["toolCount"] == 231
    assert payload["operationalSkillCount"] == 44
    assert payload["guidanceSkillCount"] == 8
    assert payload["activeMcpConfig"] is False
    assert payload["executableHooks"] is False


def test_active_mcp_configuration_is_absent() -> None:
    assert not (VALIDATOR.ROOT / ".mcp.json").exists()
    assert (VALIDATOR.ROOT / ".mcp.json.example").is_file()


def test_hooks_are_structurally_empty() -> None:
    hooks = VALIDATOR.load_json("hooks/hooks.json")
    assert hooks == {"hooks": {}}
