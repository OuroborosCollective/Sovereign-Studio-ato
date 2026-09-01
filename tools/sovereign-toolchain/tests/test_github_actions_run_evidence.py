from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sovereign-legacy-mcp-common"))
sys.path.insert(0, str(ROOT / "sovereign-toolchain" / "src"))

from sovereign_toolchain import core


HEAD = "a" * 40
ALLOWED = (
    "OuroborosCollective/Sovereign-Studio-ato,"
    "OuroborosCollective/Echoes_of_Aurion"
)


class FakeGitHub:
    def __init__(
        self,
        *,
        resolved_workflow_id: int = 123456,
        run_workflow_id: int | None = None,
        run_branch: str = "main",
    ) -> None:
        self.resolved_workflow_id = resolved_workflow_id
        self.run_workflow_id = run_workflow_id or resolved_workflow_id
        self.run_branch = run_branch
        self.calls: list[tuple[str, str]] = []

    def _request(self, method: str, path: str):
        self.calls.append((method, path))
        if "/actions/workflows/" in path and "/runs?" in path:
            return {
                "workflow_runs": [
                    {
                        "id": 77,
                        "workflow_id": self.run_workflow_id,
                        "head_branch": self.run_branch,
                        "head_sha": HEAD,
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }
        if "/actions/workflows/" in path:
            return {"id": self.resolved_workflow_id, "name": "Selected Workflow"}
        if path.endswith("/actions/runs/77"):
            return {
                "id": 77,
                "workflow_id": self.run_workflow_id,
                "head_branch": self.run_branch,
                "head_sha": HEAD,
                "status": "completed",
                "conclusion": "success",
            }
        if "/actions/runs/77/jobs" in path:
            return {"jobs": []}
        raise AssertionError(path)

    def branch_sha(self, owner: str, repo: str, branch: str) -> str:
        self.calls.append(("BRANCH_SHA", f"{owner}/{repo}@{branch}"))
        return HEAD


def test_workflow_filename_selects_only_that_workflow_and_server_branch_head(monkeypatch) -> None:
    fake = FakeGitHub()
    selected_repositories: list[str] = []
    monkeypatch.setenv("ALLOWED_REPOS", ALLOWED)
    monkeypatch.setattr(
        core,
        "GitHubClient",
        lambda repository: selected_repositories.append(repository) or fake,
    )

    receipt = core.github_actions_run_evidence(
        "OuroborosCollective",
        "Sovereign-Studio-ato",
        "sovereign-coordinated-release.yml",
    )

    assert receipt["workflowSelector"] == "sovereign-coordinated-release.yml"
    assert receipt["workflowId"] == 123456
    assert receipt["branchHeadSha"] == HEAD
    assert receipt["revisionMatches"] is True
    assert selected_repositories == ["OuroborosCollective/Sovereign-Studio-ato"]
    assert (
        "GET",
        "/repos/OuroborosCollective/Sovereign-Studio-ato/actions/workflows/"
        "sovereign-coordinated-release.yml/runs?branch=main&per_page=1",
    ) in fake.calls
    assert not any("/actions/runs?branch=" in path for _, path in fake.calls)


def test_numeric_aurion_workflow_selector_is_bound(monkeypatch) -> None:
    fake = FakeGitHub(resolved_workflow_id=340269357)
    selected_repositories: list[str] = []
    monkeypatch.setenv("ALLOWED_REPOS", ALLOWED)
    monkeypatch.setattr(
        core,
        "GitHubClient",
        lambda repository: selected_repositories.append(repository) or fake,
    )

    receipt = core.github_actions_run_evidence(
        "OuroborosCollective",
        "Echoes_of_Aurion",
        340269357,
    )

    assert receipt["repository"] == "OuroborosCollective/Echoes_of_Aurion"
    assert receipt["workflowSelector"] == "340269357"
    assert receipt["workflowId"] == 340269357
    assert selected_repositories == ["OuroborosCollective/Echoes_of_Aurion"]
    assert (
        "GET",
        "/repos/OuroborosCollective/Echoes_of_Aurion/actions/workflows/"
        "340269357/runs?branch=main&per_page=1",
    ) in fake.calls


def test_explicit_run_from_another_workflow_is_rejected(monkeypatch) -> None:
    fake = FakeGitHub(resolved_workflow_id=123456, run_workflow_id=999999)
    monkeypatch.setenv("ALLOWED_REPOS", ALLOWED)
    monkeypatch.setattr(core, "GitHubClient", lambda _repository: fake)

    with pytest.raises(RuntimeError, match="does not belong to the selected workflow"):
        core.github_actions_run_evidence(
            "OuroborosCollective",
            "Sovereign-Studio-ato",
            "sovereign-coordinated-release.yml",
            run_id=77,
        )


def test_explicit_run_from_another_branch_is_rejected(monkeypatch) -> None:
    fake = FakeGitHub(run_branch="release")
    monkeypatch.setenv("ALLOWED_REPOS", ALLOWED)
    monkeypatch.setattr(core, "GitHubClient", lambda _repository: fake)

    with pytest.raises(RuntimeError, match="does not belong to the selected branch"):
        core.github_actions_run_evidence(
            "OuroborosCollective",
            "Sovereign-Studio-ato",
            "sovereign-coordinated-release.yml",
            run_id=77,
        )


@pytest.mark.parametrize("selector", ["../unsafe.yml", "folder/workflow.yml", "workflow.txt", 0, True])
def test_unsafe_workflow_selectors_are_rejected(selector) -> None:
    with pytest.raises(ValueError, match="workflow_id"):
        core._workflow_selector(selector)


def test_allowlist_accepts_only_sovereign_and_aurion(monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_REPOS", ALLOWED)

    core.allowed_repo("OuroborosCollective", "Sovereign-Studio-ato")
    core.allowed_repo("OuroborosCollective", "Echoes_of_Aurion")
    with pytest.raises(PermissionError):
        core.allowed_repo("OuroborosCollective", "Wasd")
