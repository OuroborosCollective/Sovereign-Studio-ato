from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

import skill_supply_chain_tools as tools


WORKSPACE_ID = "job-supply-test"


class FakeRuntime:
    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == WORKSPACE_ID
        return self.repo


class FakeMCP:
    def __init__(self) -> None:
        self.names: list[str] = []

    def tool(self, *, annotations):
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False

        def decorator(function):
            self.names.append(function.__name__)
            return function

        return decorator


@pytest.fixture()
def repository(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "Surface.tsx").write_text(
        "export const Surface = () => <div onClick={() => 1}><img src='x' /></div>;\n",
        "utf-8",
    )
    (repo / "report.md").write_text("# Evidence report\n", "utf-8")
    with zipfile.ZipFile(repo / "template-forge.zip", "w") as archive:
        archive.writestr(
            "nocode-llm-template-forge/SKILL.md",
            "---\nname: nocode-llm-template-forge\ndescription: Template forge\n---\n"
            "Run pip install danger and subprocess.Popen for /opt/project output.\n",
        )
        archive.writestr("nocode-llm-template-forge/scripts/generate.py", "import subprocess\n")
    monkeypatch.setattr(tools, "_RUNTIME", FakeRuntime(repo))
    monkeypatch.setattr(tools, "_REGISTERED", False)
    return repo


def test_registers_all_read_only_tools(repository: Path) -> None:
    mcp = FakeMCP()
    tools.register(mcp, FakeRuntime(repository))
    assert len(mcp.names) == 28
    assert "skill_archive_inspect" in mcp.names
    assert "template_generation_plan" in mcp.names
    assert "goal_transition_preview" in mcp.names
    inventory = tools.skill_supply_chain_inventory()
    assert inventory["toolCount"] == 30
    assert inventory["truthBoundary"]["originalScriptsExecuted"] is False


def test_archive_inspection_blocks_execution_risks(repository: Path) -> None:
    inspected = tools.skill_archive_inspect(WORKSPACE_ID, "template-forge.zip")
    families = {item["family"] for item in inspected["risk"]["findings"]}
    assert "GENERIC_SHELL_EXECUTION" in families
    assert "PACKAGE_INSTALLATION" in families
    assert inspected["risk"]["codeExecuted"] is False
    validated = tools.skill_validate(WORKSPACE_ID, "template-forge.zip")
    assert validated["status"] == "SKILL_VALIDATION_BLOCKED"
    assert validated["activationAllowed"] is False


def test_goal_completion_requires_real_evidence(repository: Path) -> None:
    preview = tools.goal_transition_preview(
        "active",
        "completed",
        "release",
        [{"goalId": "child", "required": True, "status": "active", "weight": 2}],
        ["runtime_canary", "pr_head_sha"],
        [{"type": "pr_head_sha", "verified": True}],
        [],
    )
    assert preview["status"] == "GOAL_TRANSITION_BLOCKED"
    assert "required_evidence_missing" in preview["reasons"]
    assert "required_children_incomplete" in preview["reasons"]
    assert preview["progress"]["freeProgressInputUsed"] is False


def test_curated_template_plan_is_deterministic_and_does_not_write(repository: Path) -> None:
    first = tools.template_generation_plan("react-typescript-surface", {"project_name": "Operator"})
    second = tools.template_generation_plan("react-typescript-surface", {"project_name": "Operator"})
    assert first["ok"] is True
    assert first["planSha256"] == second["planSha256"]
    assert first["filesWritten"] is False
    assert not (repository / ".sovereign-generated").exists()
    blocked = tools.template_contract_audit({"id": "unsafe-template", "files": ["../../etc/passwd"], "schema": {}})
    assert blocked["status"] == "TEMPLATE_CONTRACT_BLOCKED"


def test_document_android_analytics_and_content_plans_are_bounded(repository: Path) -> None:
    document = tools.document_plan(WORKSPACE_ID, "report.md", "audit", "Truth Report")
    assert document["renderer"] == "typst"
    assert document["mutationPerformed"] is False

    android = tools.android_ui_contract_audit(WORKSPACE_ID)
    families = {item["family"] for item in android["findings"]}
    assert "CLICKABLE_DIV_CANDIDATE" in families
    assert "IMAGE_WITHOUT_ALT_CANDIDATE" in families

    analytics = tools.domain_analytics_query_plan(
        "example.com", "2026-01", "2026-06", ["visits_total", "bounce_rate"]
    )
    assert analytics["ok"] is True
    assert analytics["creditsConsumed"] is False

    claims = tools.content_claim_audit(
        [{"claimId": "c1", "text": "The best tool costs €19.99", "sourceIds": [], "reviewClaim": True}],
        [],
    )
    families = {item["family"] for item in claims["findings"]}
    assert "UNSOURCED_CLAIM" in families
    assert "PRICE_DATE_MISSING" in families
    assert "FABRICATED_REVIEW_RISK" in families
