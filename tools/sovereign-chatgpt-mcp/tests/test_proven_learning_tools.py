from __future__ import annotations

import json
from pathlib import Path
import subprocess

import proven_learning_tools as tools


WORKSPACE_ID = "job-proven-learning-test"


class FakeRuntime:
    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == WORKSPACE_ID
        return self.repo


class FakeOwnerInput:
    def __init__(self, plan: dict) -> None:
        self.plan = plan
        self.created: dict | None = None
        self.applied: dict | None = None

    def plan_proven_learning(self, record):
        assert record["title"] == "Evidence gate"
        return self.plan

    def create_request(self, **kwargs):
        self.created = kwargs
        return {"ok": True, "request": {"id": "request-id"}}

    def apply_proven_learning(self, **kwargs):
        self.applied = kwargs
        return {"ok": True, "status": "PROVEN_LEARNING_PATTERN_STORED"}


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *, annotations):
        def decorator(function):
            self.tools[function.__name__] = annotations
            return function
        return decorator


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _plan() -> dict:
    digest = "d" * 64
    return {
        "ok": True,
        "status": "PROVEN_LEARNING_PLAN_READY",
        "confirmationSha256": digest,
        "record": {
            "title": "Evidence gate",
            "problem": "Unproven output entered memory.",
            "solution": "Require exact receipts.",
            "applicability": "Verified fixes",
            "content_hash": f"sha256:{digest}",
            "source_refs": [{
                "repository": "example/repo",
                "revision": "a" * 40,
                "path": "src/fix.py",
            }],
            "evidence": {
                "operation_type": "fix",
                "revision": "a" * 40,
                "completed_at": "2026-07-19T12:00:00Z",
                "changed_paths": ["src/fix.py"],
                "checks": [{
                    "name": "pytest",
                    "source": "repository_check",
                    "evidence_sha256": "b" * 64,
                    "summary": "All real-path tests passed.",
                }],
            },
        },
    }


def test_tools_have_truthful_annotations_and_forward_exact_plan(tmp_path: Path, monkeypatch) -> None:
    plan = _plan()
    owner = FakeOwnerInput(plan)
    mcp = FakeMCP()
    monkeypatch.setattr(tools, "_REGISTERED", False)
    tools.register(mcp, FakeRuntime(tmp_path), owner)

    assert mcp.tools["proven_learning_pattern_plan"].readOnlyHint is True
    assert mcp.tools["proven_learning_pattern_apply"].readOnlyHint is False
    assert mcp.tools["proven_learning_pattern_apply"].idempotentHint is True
    assert mcp.tools["proven_learning_owner_approval_request"].idempotentHint is False
    assert mcp.tools["repository_learning_logbook_update"].idempotentHint is True
    assert tools.proven_learning_pattern_plan({"title": "Evidence gate"}) == plan

    requested = tools.proven_learning_owner_approval_request(
        plan["confirmationSha256"],
        "Approve pattern",
        "Verified integration",
    )
    assert requested["ok"] is True
    assert owner.created["target_id"] == "proven_learning_confirmation"
    assert plan["confirmationSha256"] in owner.created["reason"]

    applied = tools.proven_learning_pattern_apply(
        "00000000-0000-0000-0000-000000000001",
        plan["confirmationSha256"],
        plan["record"],
    )
    assert applied["status"] == "PROVEN_LEARNING_PATTERN_STORED"
    assert owner.applied["confirmation_sha256"] == plan["confirmationSha256"]


def test_logbook_and_manifest_are_idempotent(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Sovereign Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    (repo / "src").mkdir()
    (repo / "src" / "fix.py").write_text("VALUE = 1\n", "utf-8")
    (repo / "package.json").write_text('{"name":"fixture"}\n', "utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "fixture")

    monkeypatch.setattr(tools, "_RUNTIME", FakeRuntime(repo))
    first = tools.repository_learning_logbook_update(WORKSPACE_ID, _plan())
    second = tools.repository_learning_logbook_update(WORKSPACE_ID, _plan())

    assert first["status"] == "REPOSITORY_LEARNING_LOGBOOK_UPDATED"
    assert second["status"] == "REPOSITORY_LEARNING_LOGBOOK_ALREADY_CURRENT"
    logbook = (repo / "docs" / "SOVEREIGN_LEARNING_LOGBOOK.md").read_text("utf-8")
    assert logbook.count("<!-- proven-learning:" + "d" * 64 + " -->") == 1
    manifest = json.loads((repo / ".sovereign" / "proven-learning-manifest.json").read_text("utf-8"))
    assert manifest["latestPatternSha256"] == "d" * 64
    assert manifest["learningPatternSha256"] == ["d" * 64]
    assert any(item["path"] == "package.json" for item in manifest["importantManifestFiles"])
    assert manifest["selfHashExcluded"] is True
