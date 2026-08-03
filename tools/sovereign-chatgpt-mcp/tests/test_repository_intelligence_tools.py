from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import repository_intelligence_tools as tools


WORKSPACE_ID = "job-repository-intelligence-test"


class FakeRuntime:
    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == WORKSPACE_ID
        return self.repo


class FakeMCP:
    def __init__(self) -> None:
        self.tools: list[tuple[str, bool, bool]] = []

    def tool(self, *, annotations):
        def decorator(function):
            self.tools.append((function.__name__, bool(annotations.readOnlyHint), bool(annotations.destructiveHint)))
            return function
        return decorator


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


@pytest.fixture()
def repository(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Sovereign Test")
    _git(repo, "config", "user.email", "sovereign-test@example.invalid")
    (repo / "src").mkdir()
    (repo / "config").mkdir()
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "src" / "engine.py").write_text(
        "API_KEY = 'sk-proj-" + "x" * 24 + "'\n"
        "def repository_intelligence():\n"
        "    return 'deterministic evidence lane'\n",
        "utf-8",
    )
    (repo / "config" / "openapi.json").write_text(
        json.dumps({
            "openapi": "3.1.0",
            "components": {"schemas": {"Valid": {"type": "object", "properties": {"id": {"type": "string"}}}}},
        }) + "\n",
        "utf-8",
    )
    (repo / ".github" / "workflows" / "test.yml").write_text(
        "name: test\non: [push]\njobs:\n  verify:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n",
        "utf-8",
    )
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "fixture")
    monkeypatch.setattr(tools, "_RUNTIME", FakeRuntime(repo))
    monkeypatch.setattr(tools, "_REGISTERED", False)
    return repo


def _scope(repo: Path) -> dict:
    head = _git(repo, "rev-parse", "HEAD")
    return tools.repository_capability_scope_create(
        WORKSPACE_ID,
        head,
        "repository-intelligence-tests",
        [
            "repository_intelligence_index_build",
            "repository_hash_bound_replace",
            "repository_hash_bound_restore",
            "deployment_evidence_session_capture",
        ],
        ["@git/**", "src/**"],
        issued_at_epoch=1_700_000_000,
    )


def test_registers_read_side_channel_and_tracked_write_contracts(repository: Path) -> None:
    mcp = FakeMCP()
    tools.register(mcp, FakeRuntime(repository))
    names = [name for name, _, _ in mcp.tools]
    assert names == [
        "repository_intelligence_tool_inventory",
        "repository_intelligence_search",
        "managed_toolchain_verify",
        "repository_schema_diagnostics",
        "sovereign_resource_explorer",
        "repository_context_drift_watch",
        "repository_capability_scope_create",
        "repository_intelligence_index_build",
        "deployment_evidence_session_capture",
        "repository_hash_bound_replace",
        "repository_hash_bound_restore",
    ]
    contracts = {name: (read_only, destructive) for name, read_only, destructive in mcp.tools}
    assert contracts["repository_intelligence_search"] == (True, False)
    assert contracts["repository_intelligence_index_build"] == (False, False)
    assert contracts["repository_hash_bound_replace"] == (False, True)
    inventory = tools.repository_intelligence_tool_inventory()
    assert inventory["providerRoutes"] == []
    assert inventory["telemetryEnabled"] is False
    assert inventory["proprietaryBinaryDependency"] is False


def test_revision_bound_fts_and_local_embedding_index_redacts_secrets(repository: Path) -> None:
    head = _git(repository, "rev-parse", "HEAD")
    scope = _scope(repository)
    built = tools.repository_intelligence_index_build(
        WORKSPACE_ID,
        head,
        scope["scopeId"],
    )
    assert built["status"] == "REPOSITORY_INTELLIGENCE_INDEX_READY"
    assert built["secretLinesRedacted"] == 1
    assert built["neuralModelUsed"] is False
    assert built["repositoryWritten"] is False

    result = tools.repository_intelligence_search(
        WORKSPACE_ID,
        "repository intelligence deterministic evidence",
        head,
    )
    assert result["resultCount"] == 1
    assert result["results"][0]["path"] == "src/engine.py"
    rendered = json.dumps(result)
    assert "sk-proj" not in rendered
    assert "xxxxxxxx" not in rendered
    assert result["results"][0]["gitBlobSha"] == _git(repository, "hash-object", "--", "src/engine.py")


def test_hash_bound_replace_and_restore_require_scope_and_exact_blobs(repository: Path) -> None:
    head = _git(repository, "rev-parse", "HEAD")
    scope = _scope(repository)
    original_blob = _git(repository, "hash-object", "--", "src/engine.py")
    patched = tools.repository_hash_bound_replace(
        WORKSPACE_ID,
        "src/engine.py",
        head,
        original_blob,
        "deterministic evidence lane",
        "hash-bound evidence lane",
        scope["scopeId"],
    )
    assert patched["status"] == "HASH_BOUND_REPLACE_APPLIED"
    assert patched["beforeBlobSha"] == original_blob
    assert patched["afterBlobSha"] != original_blob
    assert patched["committed"] is False

    with pytest.raises(ValueError, match="blob mismatch"):
        tools.repository_hash_bound_replace(
            WORKSPACE_ID,
            "src/engine.py",
            head,
            original_blob,
            "hash-bound evidence lane",
            "invalid second write",
            scope["scopeId"],
        )

    restored = tools.repository_hash_bound_restore(
        WORKSPACE_ID,
        "src/engine.py",
        head,
        patched["afterBlobSha"],
        "HEAD",
        original_blob,
        scope["scopeId"],
    )
    assert restored["status"] == "HASH_BOUND_RESTORE_APPLIED"
    assert restored["restoredBlobSha"] == original_blob


def test_schema_diagnostics_detect_duplicate_and_openapi_contract_drift(repository: Path) -> None:
    head = _git(repository, "rev-parse", "HEAD")
    (repository / "config" / "duplicate.json").write_text('{"a":1,"a":2}\n', "utf-8")
    (repository / "config" / "broken-openapi.json").write_text(
        json.dumps({
            "openapi": "3.1.0",
            "components": {"schemas": {"Broken": {"type": "object", "required": ["missing"]}}},
        }) + "\n",
        "utf-8",
    )
    report = tools.repository_schema_diagnostics(
        WORKSPACE_ID,
        head,
        ["config/duplicate.json", "config/broken-openapi.json"],
    )
    families = {item["family"] for item in report["findings"]}
    assert report["status"] == "SCHEMA_DIAGNOSTICS_FINDINGS"
    assert "DUPLICATE_KEY" in families
    assert "OPENAPI_OBJECT_PROPERTIES_MISSING" in families
    assert "OPENAPI_REQUIRED_PROPERTY_UNDECLARED" in families


def test_toolchain_resource_graph_and_drift_are_evidence_bounded(repository: Path) -> None:
    head = _git(repository, "rev-parse", "HEAD")
    toolchain = tools.managed_toolchain_verify(WORKSPACE_ID, head, ["git", "python"])
    assert toolchain["status"] == "TOOLCHAIN_VERIFIED"
    assert all(item["executableSha256"] for item in toolchain["tools"])
    assert toolchain["installationPerformed"] is False

    graph = tools.sovereign_resource_explorer(WORKSPACE_ID, head, include_docker=False)
    assert graph["status"] == "RESOURCE_EXPLORER_READY"
    assert {node["id"] for node in graph["nodes"]} >= {"repo", "ci", "database", "mcp", "patchmon", "docker"}
    assert graph["databaseRowsRead"] is False

    drift = tools.repository_context_drift_watch(WORKSPACE_ID, head)
    assert drift["status"] == "CONTEXT_READBACK_MATCH"
    assert drift["mutationPerformed"] is False


def test_deployment_session_is_git_private_and_does_not_invent_docker_success(repository: Path) -> None:
    head = _git(repository, "rev-parse", "HEAD")
    scope = _scope(repository)
    captured = tools.deployment_evidence_session_capture(
        WORKSPACE_ID,
        head,
        scope["scopeId"],
        include_docker=False,
        session_label="pytest evidence",
    )
    assert captured["status"] == "DEPLOYMENT_EVIDENCE_SESSION_CAPTURED"
    assert captured["repositoryWritten"] is False
    assert captured["gitPrivateSideChannelWritten"] is True
    assert captured["evidence"]["docker"]["status"] == "DOCKER_READBACK_NOT_REQUESTED"
    assert captured["evidence"]["repoSha"] == head
