from __future__ import annotations

import re
from pathlib import Path

from agent_runtime import sovereign_local_runner


REPO_ROOT = Path(__file__).resolve().parents[3]
PASSWORD_CONNECT_RE = re.compile(
    r"client\.connect\([^\n)]*password\s*=\s*['\"][^'\"]+['\"][^\n)]*\)",
    re.IGNORECASE,
)


def test_runner_is_quarantined_and_cannot_execute() -> None:
    assert sovereign_local_runner.register_sovereign_runner() is None

    action, blocker = sovereign_local_runner.call_llm_for_next_action()
    assert action is None
    assert "quarantined" in blocker

    result = sovereign_local_runner.execute_tool_call()
    assert result["status"] == "blocked"
    assert "quarantined" in result["blocker"]


def test_repository_has_no_password_based_ssh_examples() -> None:
    documents = (
        "AGENTS_BEST_PRACTICES.md",
        "AGENTS_KNOWLEDGE.md",
        "AGENTS_SKILLS.md",
        "scripts/sovereign-backend/migrations/AGENTS_MIGRATION_SKILL.md",
    )
    for relative_path in documents:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert PASSWORD_CONNECT_RE.search(text) is None, relative_path


def test_automation_cannot_merge_or_push_main_directly() -> None:
    assert not (REPO_ROOT / ".github/workflows/dependabot-auto-merge.yml").exists()

    workflow = (REPO_ROOT / ".github/workflows/autonomous-cycle.yml").read_text(
        encoding="utf-8"
    )
    assert "git push origin main" not in workflow
    assert "gh pr create" in workflow
    assert "--draft" in workflow


def test_backend_is_bound_to_localhost() -> None:
    compose = (REPO_ROOT / "scripts/sovereign-backend/docker-compose.yml").read_text(
        encoding="utf-8"
    )
    deploy = (REPO_ROOT / ".github/workflows/sovereign-agent-backend.yml").read_text(
        encoding="utf-8"
    )
    assert '127.0.0.1:8788:8787' in compose
    assert '-p 127.0.0.1:8788:8787' in deploy


def test_workspace_clone_creates_repo_directory_before_iteration() -> None:
    for relative_path in (
        "backend/agent_runtime/git_workspace.py",
        "scripts/sovereign-backend/agent_runtime/git_workspace.py",
    ):
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        mkdir_position = text.index("repo_path.mkdir(parents=True, exist_ok=True)")
        iteration_position = text.index("if any(repo_path.iterdir()):")
        assert mkdir_position < iteration_position
