from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL_NAMES = (
    "aurion_account_role_readback",
    "aurion_account_role_plan",
    "aurion_account_role_apply",
)
OIDC_OPEN_ID = "0123456789abcdef" * 4
VALID_OPEN_IDS = (
    "local:a",
    "local:" + "a" * 28 + "A9_-",
    "local:Fixture_9.-",
    OIDC_OPEN_ID,
)
INVALID_OPEN_IDS = (
    "",
    OIDC_OPEN_ID.upper(),
    OIDC_OPEN_ID[:32] + OIDC_OPEN_ID[32:].upper(),
    OIDC_OPEN_ID[:-1],
    OIDC_OPEN_ID + "0",
    OIDC_OPEN_ID[:-1] + "g",
    "oauth:fixture",
    "oidc:" + OIDC_OPEN_ID,
    " " + OIDC_OPEN_ID,
    OIDC_OPEN_ID + " ",
    "local:",
    "local:" + "a" * 33,
    "local:a b",
    "local:a/b",
    "local:a:b",
    "local:ä",
)


def _arguments(tool_name: str, open_id: str) -> dict[str, object]:
    arguments: dict[str, object] = {
        "open_id": open_id,
        "expected_revision": "4" * 40,
    }
    if tool_name != "aurion_account_role_readback":
        arguments["role"] = "admin"
    if tool_name == "aurion_account_role_apply":
        arguments["confirmation_sha256"] = "e" * 64
        arguments["owner_approved"] = True
    return arguments


@pytest.fixture(scope="module")
def registered_contracts(tmp_path_factory: pytest.TempPathFactory) -> dict:
    state_root = tmp_path_factory.mktemp("aurion-schema-registry")
    program = textwrap.dedent(
        """
        import json
        import sys

        from pydantic import ValidationError
        import launcher
        import server

        assert launcher.mcp is server.mcp
        contracts = {}
        for tool_name, cases in json.load(sys.stdin).items():
            tool = launcher.mcp._tool_manager.get_tool(tool_name)
            assert tool is not None, tool_name
            results = {}
            for arguments in cases:
                open_id = arguments["open_id"]
                try:
                    validated = tool.fn_metadata.arg_model.model_validate(arguments)
                except ValidationError as error:
                    results[open_id] = {
                        "accepted": False,
                        "errorLocations": [list(item["loc"]) for item in error.errors()],
                    }
                else:
                    results[open_id] = {
                        "accepted": True,
                        "validatedOpenId": validated.open_id,
                    }
            contracts[tool_name] = {"parameters": tool.parameters, "results": results}
        print(json.dumps(contracts, sort_keys=True))
        """
    )
    cases = {
        tool_name: [_arguments(tool_name, open_id) for open_id in VALID_OPEN_IDS + INVALID_OPEN_IDS]
        for tool_name in TOOL_NAMES
    }
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=ROOT,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "SOVEREIGN_MCP_PRIVATE_OWNER_MODE": "1",
            "SOVEREIGN_MCP_ENABLE_AURION_OPERATOR": "1",
            "SOVEREIGN_MCP_ENABLE_AURION_WRITE": "1",
            "SOVEREIGN_MCP_ENABLE_AURION_ADMIN_MCP": "0",
            "SOVEREIGN_MCP_WORKSPACE_ROOT": str(state_root / "workspaces"),
            "SOVEREIGN_TOOL_RANKING_STATE_ROOT": str(state_root / "ranking"),
            "SOVEREIGN_NEURO_RUNTIME_STATE_ROOT": str(state_root / "neuro"),
            "SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED": "0",
        },
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    contracts = json.loads(completed.stdout.strip().splitlines()[-1])
    assert set(contracts) == set(TOOL_NAMES)
    return contracts


@pytest.mark.parametrize("tool_name", TOOL_NAMES)
@pytest.mark.parametrize("open_id", VALID_OPEN_IDS)
def test_registered_account_role_contract_accepts_bounded_identity(
    registered_contracts: dict, tool_name: str, open_id: str,
) -> None:
    contract = registered_contracts[tool_name]
    validator = Draft202012Validator(contract["parameters"])
    assert validator.is_valid(_arguments(tool_name, open_id))
    assert contract["results"][open_id] == {"accepted": True, "validatedOpenId": open_id}


@pytest.mark.parametrize("tool_name", TOOL_NAMES)
@pytest.mark.parametrize("open_id", INVALID_OPEN_IDS)
def test_registered_account_role_contract_rejects_unbounded_identity(
    registered_contracts: dict, tool_name: str, open_id: str,
) -> None:
    contract = registered_contracts[tool_name]
    validator = Draft202012Validator(contract["parameters"])
    assert not validator.is_valid(_arguments(tool_name, open_id))
    result = contract["results"][open_id]
    assert result["accepted"] is False
    assert ["open_id"] in result["errorLocations"]
