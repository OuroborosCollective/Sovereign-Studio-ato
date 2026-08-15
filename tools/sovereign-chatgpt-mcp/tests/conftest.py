from __future__ import annotations

from contextlib import contextmanager
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from github_installation_auth import GitHubAppInstallationConfig
from runtime import OperatorRuntime, RuntimeConfig


class FixtureInstallationAuth:
    @contextmanager
    def token(self):
        yield "test-installation-token"

    @contextmanager
    def headers(self):
        with self.token() as token:
            yield {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }


@pytest.fixture()
def repo_runtime(tmp_path: Path):
    workspace_root = tmp_path / "workspaces"
    runtime = OperatorRuntime(
        RuntimeConfig(
            repository="OuroborosCollective/Sovereign-Studio-ato",
            workspace_root=workspace_root,
            github_app=GitHubAppInstallationConfig(
                app_id="123456",
                installation_id=153170343,
                private_key_file=tmp_path / "not-read-in-fixture.pem",
                repository="OuroborosCollective/Sovereign-Studio-ato",
            ),
            allowed_base_branches=("main",),
            allowed_containers=("sovereign-backend",),
            command_timeout=30,
        ),
        github_auth=FixtureInstallationAuth(),
    )
    workspace_id = "job-abcdef123456"
    workspace = workspace_root / workspace_id
    repo = workspace / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    (repo / "src").mkdir()
    (repo / "src" / "menu.tsx").write_text("export const label = 'Old';\n", "utf-8")
    (repo / "README.md").write_text("Sovereign runtime truth\n", "utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    runtime._write_metadata(
        workspace_id,
        {
            "workspace_id": workspace_id,
            "repository": runtime.config.repository,
            "base_branch": "main",
            "branch": "sovereign/chatgpt/test-change",
            "created_at": 1,
            "checks": {},
        },
    )
    return runtime, workspace_id, repo
