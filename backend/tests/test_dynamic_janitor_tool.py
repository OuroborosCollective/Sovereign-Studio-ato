"""Focused tests for the deterministic Dynamic Janitor tool."""

from __future__ import annotations

import hashlib
from pathlib import Path

from agent_runtime.tools.janitor_tool import DynamicJanitorTool


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_registry_exposes_janitor_tool():
    from agent_runtime.tools.base import get_tool_registry

    names = {item["name"] for item in get_tool_registry().list_tools()}
    assert "janitor" in names


def test_scan_uses_ast_and_text_rules_without_writing(tmp_path: Path):
    python_source = """import subprocess\n\ndef run(command):\n    return subprocess.run(command, shell=True)\n"""
    workflow_source = "git push origin main\n"
    (tmp_path / "worker.py").write_text(python_source, encoding="utf-8")
    (tmp_path / "deploy.sh").write_text(workflow_source, encoding="utf-8")

    result = DynamicJanitorTool().execute(
        {"mode": "scan", "maxFindings": 10, "paths": ["worker.py", "deploy.sh"]},
        str(tmp_path),
    )

    assert result.status == "done"
    assert result.changed_files == ()
    assert result.metadata["writeAction"] is False
    rules = {item["ruleId"] for item in result.metadata["findings"]}
    assert "PY-UNSAFE-SHELL" in rules
    assert "GIT-DIRECT-MAIN-PUSH" in rules
    assert (tmp_path / "worker.py").read_text(encoding="utf-8") == python_source


def test_scan_masks_secret_like_source_values(tmp_path: Path):
    fake_token = 'ghp_' + '1234567890abcdefghijklmnopqrstuvwxyz'
    source = f"const token = '{fake_token}';\n"
    (tmp_path / "secret.ts").write_text(source, encoding="utf-8")

    result = DynamicJanitorTool().execute({"mode": "scan"}, str(tmp_path))

    findings = result.metadata["findings"]
    assert any(item["ruleId"] == "SOURCE-SECRET-LIKE-VALUE" for item in findings)
    assert fake_token not in str(findings)


def test_scan_suggests_but_does_not_apply_safe_known_fix(tmp_path: Path):
    source = "client.set_missing_host_key_policy(paramiko.AutoAddPolicy())\n"
    (tmp_path / "ssh.py").write_text(source, encoding="utf-8")

    result = DynamicJanitorTool().execute({"mode": "scan"}, str(tmp_path))

    finding = next(item for item in result.metadata["findings"] if item["ruleId"] == "PY-SSH-AUTOADD-HOSTKEY")
    assert finding["fixAvailable"] is True
    assert "RejectPolicy" in finding["suggestedReplacementText"]
    assert (tmp_path / "ssh.py").read_text(encoding="utf-8") == source


def test_apply_requires_confirmation_and_current_hash(tmp_path: Path):
    target = tmp_path / "module.ts"
    original = "export const value = 1;\n"
    target.write_text(original, encoding="utf-8")
    tool = DynamicJanitorTool()

    try:
        tool.validate({
            "mode": "apply", "path": "module.ts", "searchText": "1",
            "replacementText": "2", "expectedSha256": _sha(original), "confirm": False,
        })
    except Exception as exc:
        assert "confirmation" in str(exc).lower()
    else:
        raise AssertionError("apply without confirmation must be blocked")

    blocked = tool.execute({
        "mode": "apply", "path": "module.ts", "searchText": "1",
        "replacementText": "2", "expectedSha256": "0" * 64, "confirm": True,
    }, str(tmp_path))
    assert blocked.status == "blocked"
    assert target.read_text(encoding="utf-8") == original


def test_apply_exact_search_replace_returns_diff_evidence(tmp_path: Path):
    target = tmp_path / "module.ts"
    original = "export const value = 1;\n"
    target.write_text(original, encoding="utf-8")

    result = DynamicJanitorTool().execute({
        "mode": "apply", "path": "module.ts", "searchText": "value = 1",
        "replacementText": "value = 2", "expectedSha256": _sha(original), "confirm": True,
    }, str(tmp_path))

    assert result.status == "done"
    assert result.changed_files == ("module.ts",)
    assert "-export const value = 1" in (result.diff_summary or "")
    assert "+export const value = 2" in (result.diff_summary or "")
    assert target.read_text(encoding="utf-8") == "export const value = 2;\n"
    assert result.metadata["requiresConfirm"] is True


def test_apply_blocks_duplicate_search_and_forbidden_replacement(tmp_path: Path):
    target = tmp_path / "module.ts"
    original = "const a = 1;\nconst b = 1;\n"
    target.write_text(original, encoding="utf-8")
    tool = DynamicJanitorTool()

    duplicate = tool.execute({
        "mode": "apply", "path": "module.ts", "searchText": "1",
        "replacementText": "2", "expectedSha256": _sha(original), "confirm": True,
    }, str(tmp_path))
    assert duplicate.status == "blocked"

    forbidden = tool.execute({
        "mode": "apply", "path": "module.ts", "searchText": "const a = 1;",
        "replacementText": "git push origin main", "expectedSha256": _sha(original), "confirm": True,
    }, str(tmp_path))
    assert forbidden.status == "blocked"
    assert target.read_text(encoding="utf-8") == original


def test_apply_blocks_workspace_escape(tmp_path: Path):
    outside = tmp_path.parent / "outside.ts"
    outside.write_text("const outside = true;\n", encoding="utf-8")

    result = DynamicJanitorTool().execute({
        "mode": "apply", "path": "../outside.ts", "searchText": "true",
        "replacementText": "false", "expectedSha256": _sha("const outside = true;\n"), "confirm": True,
    }, str(tmp_path))

    assert result.status == "blocked"
    assert outside.read_text(encoding="utf-8") == "const outside = true;\n"


def test_scan_does_not_flag_environment_references_or_type_annotations(tmp_path: Path):
    source = """const token: string | undefined = process.env.GITHUB_TOKEN;\nexport const createHub = (token: string): Hub => new Hub(token);\n"""
    (tmp_path / "safe.ts").write_text(source, encoding="utf-8")

    result = DynamicJanitorTool().execute({"mode": "scan"}, str(tmp_path))

    assert not any(item["ruleId"] == "SOURCE-SECRET-LIKE-VALUE" for item in result.metadata["findings"])


def test_validate_blocks_unsafe_scan_paths():
    tool = DynamicJanitorTool()
    try:
        tool.validate({"mode": "scan", "paths": ["../outside.py"]})
    except Exception as exc:
        assert "safe relative paths" in str(exc)
    else:
        raise AssertionError("unsafe scan path must be blocked")


def test_local_model_request_is_truthfully_blocked(tmp_path: Path):
    (tmp_path / "safe.py").write_text("value = 1\n", encoding="utf-8")
    result = DynamicJanitorTool().execute(
        {"mode": "scan", "explainWithLocalModel": True}, str(tmp_path),
    )
    assert result.status == "done"
    assert result.metadata["localModelExplanation"] is None
    assert "disabled" in result.metadata["localModelBlocker"].lower()
