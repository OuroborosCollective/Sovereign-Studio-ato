from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import enterprise_backend_tools as tools


WORKSPACE_ID = "job-enterprise-backend-test"


class FakeRuntime:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.config = SimpleNamespace(
            repository="OuroborosCollective/Sovereign-Studio-ato",
            github_token="",
            allowed_base_branches=("main",),
        )

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == WORKSPACE_ID
        return self.repo


class FakeBroker:
    def __init__(self, revision: str) -> None:
        self.revision = revision
        self.calls: list[tuple[str, dict, int]] = []

    def call(self, action: str, arguments: dict, timeout: int = 30) -> dict:
        self.calls.append((action, arguments, timeout))
        assert action == "mcp_self_update_status"
        return {
            "ok": True,
            "status": "UPDATED",
            "revision": self.revision,
            "image": "ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp@sha256:" + "b" * 64,
            "image_id": "sha256:" + "c" * 64,
            "evidence_sha256": "d" * 64,
            "kappa_pos": 1_000_000,
            "updated_at": 1_784_409_000,
            "revision_verified": True,
            "image_digest_verified": True,
            "container_healthy": True,
            "mcp_protocol_ready": True,
            "broker_rpc_ready": True,
        }


class FakeMCP:
    def __init__(self) -> None:
        self.tools: list[tuple[str, object, str]] = []

    def tool(self, *, annotations):
        def decorator(function):
            self.tools.append((function.__name__, annotations, function.__doc__ or ""))
            return function

        return decorator


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


@pytest.fixture()
def repository(tmp_path: Path, monkeypatch) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Sovereign Test")
    _git(repo, "config", "user.email", "sovereign-test@example.invalid")

    (repo / "src").mkdir()
    (repo / "server").mkdir()
    (repo / "migrations").mkdir()
    (repo / "tests").mkdir()
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "src" / "Admin.tsx").write_text(
        "import React from 'react';\nexport const Admin = () => <main>Admin</main>;\n",
        "utf-8",
    )
    secret_like = "sk-" + "proj-" + "x" * 24
    (repo / "server" / "app.ts").write_text(
        "import Fastify from 'fastify';\n"
        "import postgres from 'postgres';\n"
        "const app = Fastify();\n"
        "app.get('/api/users', async () => []);\n"
        "const auth = 'openid oauth jwt rbac rate limit opentelemetry prometheus';\n"
        f"const leaked = '{secret_like}';\n",
        "utf-8",
    )
    (repo / "server" / f"{secret_like}.ts").write_text("export const marker = true;\n", "utf-8")
    (repo / "migrations" / "001_users.sql").write_text(
        "CREATE TABLE users (id text primary key, tenant_id text not null);\n",
        "utf-8",
    )
    (repo / "tests" / "app.test.ts").write_text("test('api', () => expect(true).toBe(true));\n", "utf-8")
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: ci\non: [push]\n", "utf-8")
    (repo / "Dockerfile").write_text("FROM node:22\nCOPY . /app\n", "utf-8")
    (repo / "package.json").write_text('{"dependencies":{"fastify":"1","postgres":"1"}}\n', "utf-8")

    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "-c", "feature/backend-tools")
    (repo / "server" / "feature.ts").write_text("export const feature = true;\n", "utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "feature")
    head_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "remote", "add", "origin", "https://github.com/OuroborosCollective/Sovereign-Studio-ato.git")
    _git(repo, "update-ref", "refs/remotes/origin/main", base_sha)

    runtime = FakeRuntime(repo)
    monkeypatch.setattr(tools, "_RUNTIME", runtime)
    monkeypatch.setattr(tools, "_BROKER", FakeBroker(base_sha))
    monkeypatch.setattr(tools, "_REGISTERED", False)
    return repo, base_sha, head_sha


def test_registers_five_backend_tools_and_one_network_revision_tool(repository) -> None:
    repo, _, _ = repository
    mcp = FakeMCP()
    tools.register(mcp, FakeRuntime(repo), FakeBroker("a" * 40))

    assert [name for name, _, _ in mcp.tools] == [
        "backend_engineering_tool_inventory",
        "backend_architecture_assess",
        "backend_stack_select",
        "backend_delivery_plan",
        "backend_api_security_plan",
        "repository_revision_resolve",
    ]
    for name, annotations, description in mcp.tools:
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False
        assert annotations.idempotentHint is True
        assert description.startswith("Use this when")
        assert bool(annotations.openWorldHint) is (name == "repository_revision_resolve")

    inventory = tools.backend_engineering_tool_inventory()
    assert is_dataclass(inventory)
    assert inventory.status == "ENTERPRISE_BACKEND_TOOLS_READY"
    assert all(item["mutates"] is False for item in inventory.tools)


def test_fastmcp_contract_exposes_bounded_inputs_structured_outputs_and_annotations(repository) -> None:
    from mcp.server.fastmcp import FastMCP

    repo, _, _ = repository
    mcp = FastMCP("enterprise-backend-contract-test")
    tools.register(mcp, FakeRuntime(repo), FakeBroker("a" * 40))
    registered = {
        tool.name: tool
        for tool in mcp._tool_manager.list_tools()
    }

    expected = {
        "backend_engineering_tool_inventory",
        "backend_architecture_assess",
        "backend_stack_select",
        "backend_delivery_plan",
        "backend_api_security_plan",
        "repository_revision_resolve",
    }
    assert set(registered) == expected
    for name in expected:
        tool = registered[name]
        assert tool.output_schema["type"] == "object"
        assert tool.output_schema["required"]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert bool(tool.annotations.openWorldHint) is (name == "repository_revision_resolve")

    architecture_parameters = registered["backend_architecture_assess"].parameters["properties"]
    assert architecture_parameters["focus"]["enum"] == [
        "full",
        "api",
        "data",
        "security",
        "operations",
        "prototype-modernization",
    ]
    assert architecture_parameters["max_evidence"]["minimum"] == 10
    assert architecture_parameters["max_evidence"]["maximum"] == 200

    revision_parameters = registered["repository_revision_resolve"].parameters["properties"]
    assert revision_parameters["pr_number"]["minimum"] == 0
    assert revision_parameters["pr_number"]["maximum"] == 10_000_000
    assert revision_parameters["expected_workspace_sha"]["maxLength"] == 40


def test_architecture_assessment_is_secret_safe_and_static_only(repository) -> None:
    result = tools.backend_architecture_assess(WORKSPACE_ID)
    payload = asdict(result)

    assert result.status == "BACKEND_ARCHITECTURE_STATIC_EVIDENCE_READY"
    assert result.runtimeVerified is False
    assert result.secretValuesReturned is False
    assert any(item["name"] == "typescript" for item in result.languages)
    assert any(item["name"] == "fastify" for item in result.capabilities["frameworks"])
    assert any(item["name"] == "postgresql" for item in result.capabilities["data"])
    families = {item["family"] for item in result.riskCandidates}
    assert "SECRET_LIKE_LITERAL" in families
    assert "CONTAINER_USER_NOT_DECLARED" in families
    rendered = str(payload)
    assert "sk-proj-" not in rendered
    assert "redacted-secret-shaped-path" in rendered
    assert all(item["status"] == "STATIC_CANDIDATE" for item in result.riskCandidates)


def test_stack_selector_prefers_existing_typescript_for_admin_platform(repository) -> None:
    result = tools.backend_stack_select(
        WORKSPACE_ID,
        workload="admin-platform",
        team_language="existing",
        data_model="relational",
        deployment_target="managed-container",
    )

    assert result.status == "BACKEND_STACK_RECOMMENDATION_READY"
    assert result.selectedStack["language"] == "typescript"
    assert result.selectedStack["framework"] == "NestJS"
    assert result.selectedStack["architecture"].startswith("modular monolith")
    assert "PostgreSQL" in result.selectedStack["primaryDatabase"]
    assert result.runtimeVerified is False
    assert result.candidateScores[0]["score"] >= result.candidateScores[1]["score"]


def test_delivery_plan_covers_tsx_tenancy_plugins_and_immutable_release(repository) -> None:
    result = tools.backend_delivery_plan(
        WORKSPACE_ID,
        target_outcome="prototype-to-platform",
        include_multi_tenancy=True,
        include_plugins=True,
    )

    names = [phase["name"] for phase in result.phases]
    assert "extract-tsx-contract" in names
    assert "tenant-isolation" in names
    assert "isolated-extension-host" in names
    assert names[-1] == "immutable-progressive-release"
    assert len(result.planSha256) == 64
    assert all(phase["status"] == "PLANNED_NOT_EXECUTED" for phase in result.phases)
    assert result.mutationPerformed is False


def test_security_plan_is_threat_driven_and_does_not_claim_compliance(repository) -> None:
    result = tools.backend_api_security_plan(
        WORKSPACE_ID,
        exposure="admin",
        auth_mode="oidc",
        data_sensitivity="regulated",
        multi_tenant=True,
        dynamic_endpoints=True,
        plugin_runtime=True,
    )

    families = {item["family"] for item in result.threatControls}
    assert "tenant-isolation" in families
    assert "metadata-driven-endpoints" in families
    assert "plugin-isolation-and-supply-chain" in families
    assert result.complianceVerified is False
    assert result.secretValuesReturned is False
    assert any("SAST" in gate for gate in result.verificationGates)


def test_revision_resolver_binds_workspace_pr_ci_base_and_deployed_revision(repository, monkeypatch) -> None:
    _, base_sha, head_sha = repository
    monkeypatch.setattr(tools, "_fetch_refs", lambda _repo, _base, _pr: (True, None))

    def fake_github(url: str):
        if "/pulls/824" in url:
            return ({
                "state": "open",
                "draft": True,
                "merged_at": None,
                "merge_commit_sha": None,
                "mergeable": True,
                "head": {"sha": head_sha, "ref": "feature/backend-tools"},
                "base": {"sha": base_sha, "ref": "main"},
            }, None)
        if "/check-runs" in url:
            return ({
                "check_runs": [
                    {"name": "unit", "status": "completed", "conclusion": "success", "head_sha": head_sha},
                    {"name": "security", "status": "completed", "conclusion": "success", "head_sha": head_sha},
                ]
            }, None)
        raise AssertionError(url)

    monkeypatch.setattr(tools, "_github_json", fake_github)
    _git(repository[0], "update-ref", "refs/remotes/origin/pull/824/head", head_sha)

    result = tools.repository_revision_resolve(
        WORKSPACE_ID,
        pr_number=824,
        expected_workspace_sha=head_sha,
        expected_base_sha=base_sha,
        expected_pr_head_sha=head_sha,
    )

    assert result.ok is True
    assert result.status == "REVISION_RESOLVED"
    assert result.workspaceHeadSha == head_sha
    assert result.currentBaseHeadSha == base_sha
    assert result.prHeadSha == head_sha
    assert result.prBaseSha == base_sha
    assert result.authoritativeNextRevision == head_sha
    assert result.ciEvidence["status"] == "TERMINAL_NO_FAILURES"
    assert result.ciEvidence["relevantChecksGreenClaimed"] is False
    assert result.deployedMcpEvidence["revision"] == base_sha
    assert result.deployedMcpEvidence["imageDigest"] == "sha256:" + "b" * 64
    assert result.deployedMcpEvidence["digestVerified"] is True
    assert "DEPLOYED_MCP_DIGEST_UNAVAILABLE" not in result.evidenceGaps
    assert result.revisionConflicts == []


def test_revision_resolver_fails_closed_on_dirty_or_mismatched_workspace(repository, monkeypatch) -> None:
    repo, base_sha, _ = repository
    monkeypatch.setattr(tools, "_fetch_refs", lambda _repo, _base, _pr: (True, None))
    secret_like = "sk-" + "proj-" + "y" * 24
    (repo / f"{secret_like}.txt").write_text("dirty\n", "utf-8")

    result = tools.repository_revision_resolve(
        WORKSPACE_ID,
        expected_workspace_sha="f" * 40,
        expected_base_sha=base_sha,
        include_ci=False,
        include_deployed_mcp=False,
    )

    assert result.ok is False
    assert result.status == "REVISION_CONFLICT"
    assert result.authoritativeNextRevision is None
    assert "WORKTREE_DIRTY" in result.revisionConflicts
    assert "EXPECTED_WORKSPACE_SHA_MISMATCH" in result.revisionConflicts
    assert result.nextAllowedAction == "stop_and_resolve_revision_conflicts"
    assert secret_like not in str(asdict(result))
    assert any("redacted-secret-shaped-path" in entry for entry in result.dirtyEntries)
