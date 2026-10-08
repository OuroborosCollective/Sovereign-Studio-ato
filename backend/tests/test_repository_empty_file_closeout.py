"""Real Git regressions for the server-owned empty-file closeout."""
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/sovereign-backend"))
sys.path.insert(0, str(ROOT))
from backend.agent_runtime import repository_execution as execution
from backend.agent_runtime.git_workspace import git_diff_full
from backend.agent_runtime.tool_runner import run_agent_job_tool


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "agent-empty" / "repo"
    repo.mkdir(parents=True)
    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout
    git("init", "-b", "main")
    git("config", "user.name", "Repository Test")
    git("config", "user.email", "repository@example.invalid")
    (repo / "README.md").write_text("# Baseline\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-m", "baseline")
    job = SimpleNamespace(job_id="agent-empty", workspace_id="agent-empty")
    return tmp_path, repo, job, git


def test_empty_untracked_file_has_real_patch_and_readonly_route_diff(workspace):
    root, repo, job, git = workspace
    (repo / "Tester").touch()
    before = git("status", "--porcelain")
    patch, receipt = git_diff_full(job.workspace_id, root)
    assert receipt.status == "done"
    assert b"new file mode 100644" in patch
    assert b"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391" in patch
    result = run_agent_job_tool(job, "diff", {"staged": False, "stat": False}, root)
    assert result.status == "done"
    assert "new file mode 100644" in result.diff_summary
    assert result.changed_files == ("Tester",)
    assert git("status", "--porcelain") == before
    assert git("diff", "--cached") == ""


def test_shared_patch_capture_supports_bound_git_worktrees(workspace):
    from backend.agent_runtime.tools.git_tool import GitDiffTool
    root, _, _, git = workspace
    worktree = root / "attempt"
    git("worktree", "add", "--detach", str(worktree))
    (worktree / "Tester").touch()
    result = GitDiffTool().execute({}, str(worktree))
    assert result.status == "done", result.blocker
    assert "new file mode 100644" in result.output
    assert result.changed_files == ("Tester",)


def test_empty_addition_regression_verifies_actual_git_and_bytes(workspace):
    root, repo, job, _ = workspace
    (repo / "Tester").touch()
    passed, summary = execution._empty_file_addition_regression(job, ("Tester",), root)
    assert passed
    assert "Tester" in summary
    assert "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391" in summary


@pytest.mark.parametrize("name", ["module.py", "package.json", "Dockerfile", "Makefile", ".npmrc", "src/Tester"])
def test_empty_runtime_or_configuration_file_requires_existing_regression(workspace, name):
    root, repo, job, _ = workspace
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    assert execution._empty_file_addition_regression(job, (name,), root) is None


@pytest.mark.parametrize("kind", ["nonempty", "executable", "tracked", "mixed", "symlink"])
def test_empty_regression_never_exempts_other_effects(workspace, kind):
    root, repo, job, git = workspace
    target = repo / "Tester"
    target.touch()
    paths = ("Tester",)
    if kind == "nonempty":
        target.write_text("changed", encoding="utf-8")
    elif kind == "executable":
        target.chmod(0o755)
    elif kind == "tracked":
        git("add", "Tester")
        git("commit", "-m", "track")
        target.unlink()
    elif kind == "mixed":
        (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
        paths = ("Tester", "README.md")
    else:
        target.unlink()
        target.symlink_to(repo / "README.md")
    assert execution._empty_file_addition_regression(job, paths, root) is None


@pytest.mark.parametrize("name,content,ready", [("Tester", "", True), ("module.py", "", False), ("Tester", "not empty", False)])
def test_real_closeout_prepares_draft_without_node_bootstrap(workspace, monkeypatch, name, content, ready):
    from dataclasses import replace
    from backend.agent_runtime.job_store import StoredSovereignAgentJob
    root, repo, _, _ = workspace
    (repo / name).write_text(content, encoding="utf-8")
    state = SimpleNamespace(job=StoredSovereignAgentJob(
        job_id="agent-empty", workspace_id="agent-empty", user_id="owner-empty",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main", mission="Add an empty Tester file and prepare a draft PR.",
        executor="sovereign-local-runner", status="running",
        external_ref="sovereign-local-runner:claim:closeout:fixture",
    ), prepared=[], events=[])
    def update(_conn, **kw):
        fields = {key: value for key, value in kw.items() if key in {
            "status", "changed_files", "diff_summary", "test_summary", "blocker"
        }}
        if kw.get("clear_blocker"):
            fields["blocker"] = None
        state.job = replace(state.job, **fields)
    monkeypatch.setattr(execution, "update_agent_job_state", update)
    monkeypatch.setattr(execution, "read_agent_job", lambda *a, **kw: state.job)
    monkeypatch.setattr(execution, "append_agent_event", lambda *a: state.events.append(a[-1]))
    monkeypatch.setattr(execution, "mark_draft_pr_prepared", lambda *a, **kw: state.prepared.append(kw))
    monkeypatch.setattr(execution, "compare_and_swap_agent_job_external_ref", lambda *a, **kw: True)
    result = execution._closeout_repository_job(
        object(), job=state.job, claim_ref=state.job.external_ref,
        bound_ref="sovereign-local-runner:agent-empty", workspace_root=root,
    )
    if not ready:
        assert result.status == "blocked"
        assert not state.prepared
        assert state.events[-1].stage == "repository_closeout_regression_blocked"
        return
    assert result.status != "blocked", result.blocker
    assert state.prepared
    assert result.changed_files == ("Tester",)
    assert "new file mode 100644" in result.diff_summary
    assert "empty-file-addition-regression:" in result.test_summary
    assert "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391" in result.test_summary
    assert state.events[-1].stage == "repository_ready_for_draft_pr"
    assert not (repo / "node_modules").exists()





def test_shipping_owners_are_byte_equal():
    for name in ("repository_execution.py", "tool_runner.py", "git_workspace.py", "tools/git_tool.py", "tools/test_tool.py", "cognitive_repository_tools.py", "cognitive_swarm_agents.py"):
        assert (ROOT / "backend/agent_runtime" / name).read_bytes() == (
            ROOT / "scripts/sovereign-backend/agent_runtime" / name
        ).read_bytes()
