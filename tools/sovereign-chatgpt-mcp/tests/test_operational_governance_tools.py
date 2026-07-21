from __future__ import annotations

from pathlib import Path
import subprocess

import pytest
from mcp.server.fastmcp import FastMCP

import operational_governance_tools as tools


class FakeRuntime:
    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == "job-operational-test"
        return self.repo


class FakeDatabase:
    def __init__(self, tables: list[tuple[str, str]]) -> None:
        self.tables = tables

    def schema_inventory(self) -> dict:
        return {
            "ok": True,
            "status": "POSTGRES_SCHEMA_INVENTORY",
            "tables": [
                {"table_schema": schema, "table_name": table}
                for schema, table in self.tables
            ],
            "rowDataReturned": False,
        }


class FakeBroker:
    def __init__(self, revision: str = "a" * 40) -> None:
        self.revision = revision

    def status(self) -> dict:
        return {"ok": True, "status": "BROKER_READY"}

    def call(self, action: str, arguments: dict, timeout: int = 30) -> dict:
        if action == "litellm_provider_model_inventory":
            return {
                "ok": True,
                "status": "PROVIDER_MODEL_INVENTORY",
                "modelIds": ["gpt-5.5", "gpt-5.5-pro"],
                "modelCount": 2,
                "inventorySha256": "b" * 64,
                "secretValuesExposed": False,
            }
        if action == "mcp_self_update_status":
            return {
                "ok": True,
                "status": "UPDATED",
                "revision": self.revision,
                "image": "ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp@sha256:" + "c" * 64,
                "container_healthy": True,
                "mcp_protocol_ready": True,
                "broker_rpc_ready": True,
            }
        raise AssertionError(action)


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
def repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Sovereign Test")
    _git(repo, "config", "user.email", "sovereign-test@example.invalid")
    (repo / "backend" / "migrations").mkdir(parents=True)
    (repo / "scripts" / "sovereign-backend" / "migrations").mkdir(parents=True)
    (repo / ".github").mkdir()
    (repo / "backend" / "migrations" / "001_users.sql").write_text(
        "CREATE TABLE public.users (id text primary key);\n",
        "utf-8",
    )
    (repo / "scripts" / "sovereign-backend" / "migrations" / "002_jobs.sql").write_text(
        "CREATE TABLE jobs (id text primary key);\n",
        "utf-8",
    )
    (repo / "scripts" / "sovereign-backend" / "migrations" / "003_users_mirror.sql").write_text(
        (repo / "backend" / "migrations" / "001_users.sql").read_text("utf-8"),
        "utf-8",
    )
    (repo / ".github" / "CODEOWNERS").write_text(
        "tools/sovereign-chatgpt-mcp/** @ouroboroscollective\n"
        "backend/migrations/** @ouroboroscollective\n",
        "utf-8",
    )
    (repo / "runtime_candidate.py").write_text(
        "def route(text):\n    return 'python' if 'python' in text.lower() else 'other'\n",
        "utf-8",
    )
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "fixture")
    revision = _git(repo, "rev-parse", "HEAD")
    _git(repo, "remote", "add", "origin", "https://github.com/OuroborosCollective/Sovereign-Studio-ato.git")
    _git(repo, "update-ref", "refs/remotes/origin/main", revision)
    return repo, revision


@pytest.fixture()
def registered(repository, monkeypatch):
    repo, revision = repository
    monkeypatch.setattr(tools, "_REGISTERED", False)
    monkeypatch.setattr(tools, "_MCP", None)
    monkeypatch.setattr(tools, "_RUNTIME", None)
    monkeypatch.setattr(tools, "_DATABASE", None)
    monkeypatch.setattr(tools, "_BROKER", None)
    mcp = FastMCP("operational-governance-test")

    @mcp.tool(annotations=tools.LOCAL_READ_ONLY)
    def repository_revision_probe(workspace_id: str) -> dict:
        """Use this when repository and CI revision evidence must be read before work."""
        return {"ok": True, "workspace_id": workspace_id}

    tools.register(
        mcp,
        FakeRuntime(repo),
        FakeDatabase([("public", "users"), ("public", "live_only")]),
        FakeBroker(revision),
    )
    return mcp, repo, revision


def test_registers_sixteen_read_only_operational_tools_with_fastmcp_contracts(registered) -> None:
    mcp, _, _ = registered
    registered_tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    expected = {
        "operational_skill_inventory",
        "mcp_tool_contract_registry",
        "tool_recommend_for_mission",
        "mcp_registry_snapshot_verify",
        "evidence_graph_build",
        "schema_migration_reconcile",
        "llm_route_reliability_assess",
        "agent_run_liveness_assess",
        "semantic_intent_boundary_audit",
        "cost_credit_settlement_reconcile",
        "backup_restore_evidence_verify",
        "slo_error_budget_assess",
        "configuration_drift_assess",
        "runtime_runbook_generate",
        "ownership_codeowners_guard",
        "compliance_evidence_export",
    }
    assert expected.issubset(registered_tools)
    assert len(expected) == 16
    for name in expected:
        tool = registered_tools[name]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.output_schema["type"] == "object"
        assert tool.description.startswith("Use this when")
    for name in {"schema_migration_reconcile", "llm_route_reliability_assess", "configuration_drift_assess"}:
        assert registered_tools[name].annotations.openWorldHint is True
    parameters = registered_tools["tool_recommend_for_mission"].parameters
    capability_items = parameters["properties"]["required_capabilities"]["items"]
    capability_enum = capability_items.get("enum") or parameters.get("$defs", {}).get("Capability", {}).get("enum", [])
    assert "mcp" in capability_enum
    assert "database" in capability_enum
    assert "privacy" in capability_enum
    assert "supply-chain" in capability_enum
    assert registered_tools["tool_recommend_for_mission"].parameters["properties"]["max_tools"]["maximum"] == 20


def test_inventory_and_router_use_live_registry_without_executing_tools(registered) -> None:
    _, _, _ = registered
    inventory = tools.operational_skill_inventory()
    assert inventory.status == "OPERATIONAL_SKILL_SUITE_READY"
    assert inventory.skillCount == 43
    assert inventory.toolCount == 48
    assert inventory.boundaries["naturalLanguageInterpretation"] == "model_only"
    assert inventory.boundaries["autoMerge"] is False

    result = tools.tool_recommend_for_mission(
        mission_summary="Resolve repository and CI identity before changing the MCP Docker.",
        required_capabilities=["repository", "ci"],
        allowed_effects=["read"],
        required_evidence=["revision", "workflow", "check"],
        max_tools=4,
    )
    selected = [item["name"] for item in result.evidence["selectedTools"]]
    assert result.status == "TOOL_ROUTE_READY"
    assert "repository_revision_probe" in selected
    assert result.mutationPerformed is False
    assert result.runtimeVerified is True


def test_registry_snapshot_hash_is_stable_and_detects_missing_expected_tool(registered) -> None:
    mcp, _, _ = registered
    registry = tools.mcp_tool_contract_registry(include_schemas=True)
    names = sorted(tool.name for tool in mcp._tool_manager.list_tools())
    assert registry.status == "MCP_TOOL_REGISTRY_READY"
    assert registry.toolCount == len(names)
    assert len(registry.registrySnapshotSha256) == 64

    matching = tools.mcp_registry_snapshot_verify(
        expected_snapshot_sha256=registry.registrySnapshotSha256,
        expected_tool_names=names,
    )
    assert matching.ok is True
    assert matching.status == "MCP_REGISTRY_SNAPSHOT_MATCH"

    drift = tools.mcp_registry_snapshot_verify(
        expected_snapshot_sha256=registry.registrySnapshotSha256,
        expected_tool_names=names + ["missing_future_tool"],
    )
    assert drift.ok is False
    assert any(item["family"] == "MCP_REGISTERED_TOOL_MISSING" for item in drift.findings)


def test_evidence_graph_fails_closed_on_revision_mismatch_and_missing_kind(registered) -> None:
    _, _, revision = registered
    result = tools.evidence_graph_build(
        revision=revision,
        evidence_records=[
            tools.EvidenceRecord(
                kind="ci",
                identity="workflow-1",
                status="success",
                producer="github-actions",
                revision=revision,
            ),
            tools.EvidenceRecord(
                kind="deployment",
                identity="deploy-1",
                status="success",
                producer="host-worker",
                revision="f" * 40,
                related_ids=["workflow-1"],
            ),
        ],
        required_kinds=["ci", "deployment", "runtime"],
    )
    assert result.ok is False
    families = {item["family"] for item in result.findings}
    assert "EVIDENCE_REVISION_MISMATCH" in families
    assert "REQUIRED_EVIDENCE_KIND_MISSING" in families
    assert result.evidence["releaseReady"] is False


def test_schema_reconciler_compares_migrations_with_live_names_without_rows(registered) -> None:
    _, _, _ = registered
    result = tools.schema_migration_reconcile("job-operational-test")
    assert result.status == "SCHEMA_OWNERSHIP_DRIFT"
    families = {item["family"] for item in result.findings}
    assert "DB_DRIFT_MISSING_LIVE_TABLE" in families
    assert "DB_DRIFT_UNMAPPED_LIVE_TABLE" in families
    assert "MIGRATION_TABLE_MULTIPLE_OWNERS" not in families
    assert result.evidence["byteEqualMigrationMirrors"] == [
        {
            "table": "public.users",
            "migrationFiles": [
                "backend/migrations/001_users.sql",
                "scripts/sovereign-backend/migrations/003_users_mirror.sql",
            ],
            "byteEqual": True,
        }
    ]
    assert result.evidence["rowDataReturned"] is False
    assert result.runtimeVerified is True


def test_llm_route_sre_requires_inventory_price_health_and_quota(registered) -> None:
    result = tools.llm_route_reliability_assess(
        routes=[
            tools.RouteEvidence(
                alias="sovereign-fast",
                provider_model="gpt-5.5",
                active=True,
                price_verified=True,
                health="healthy",
                quota="available",
            ),
            tools.RouteEvidence(
                alias="sovereign-balanced",
                provider_model="missing-model",
                active=True,
                price_verified=False,
                health="degraded",
                quota="exhausted",
            ),
        ],
        required_aliases=["sovereign-fast", "sovereign-balanced"],
    )
    assert result.ok is False
    families = {item["family"] for item in result.findings}
    assert "LLM_ROUTE_PRICE_UNVERIFIED" in families
    assert "LLM_ROUTE_QUOTA_NOT_READY" in families
    assert "LLM_PROVIDER_MODEL_NOT_IN_CURRENT_INVENTORY" in families
    assert result.evidence["secretValuesReturned"] is False


def test_agent_settlement_backup_and_slo_invariants_are_deterministic(registered) -> None:
    agent = tools.agent_run_liveness_assess(
        tools.AgentRunEvidence(
            run_id="run-1",
            status="BLOCKED",
            iteration_count=2,
            max_iterations=12,
            next_action="ACTIVATE_PRICE_VERIFIED_LITELLM_ROUTE",
            active_blocker="provider route inactive",
            provider_route_ready=False,
        )
    )
    assert agent.evidence["decision"] == "RESTORE_PROVIDER_ROUTE_BEFORE_RESUME"

    settlement = tools.cost_credit_settlement_reconcile(
        records=[
            tools.SettlementEvidence(
                usage_id="usage-1",
                provider_cost_micros=1_000_000,
                charged_cost_micros=1_100_000,
                credit_delta_micros=-1_000_000,
                settlement_status="settled",
                receipt_identity="receipt-1",
            )
        ],
        allowed_markup_ppm=50_000,
    )
    assert settlement.ok is False
    assert settlement.evidence["integerMathOnly"] is True

    backup = tools.backup_restore_evidence_verify(
        assets=[
            tools.BackupRestoreEvidence(
                asset="postgres",
                backup_digest="1" * 64,
                restored_digest="2" * 64,
                restore_status="passed",
                integrity_checks=["schema", "canary"],
                isolated_target=True,
            )
        ]
    )
    assert backup.ok is False
    assert any(item["family"] == "RESTORE_DIGEST_MISMATCH" for item in backup.findings)

    slo = tools.slo_error_budget_assess(
        slos=[
            tools.SloEvidence(
                service="mcp",
                objective_ppm=999_000,
                total_events=1_000,
                failed_events=10,
                latency_objective_ms=500,
                observed_p95_ms=700,
            )
        ]
    )
    assert slo.ok is False
    assert slo.evidence["integerMathOnly"] is True
    assert {item["family"] for item in slo.findings} >= {"SLO_AVAILABILITY_BREACHED", "SLO_LATENCY_BREACHED"}


def test_configuration_runbook_ownership_and_compliance_preserve_draft_pr_boundary(registered) -> None:
    _, _, revision = registered
    config = tools.configuration_drift_assess(
        "job-operational-test",
        expected_revision=revision,
    )
    assert config.ok is True
    assert config.evidence["installedRevision"] == revision
    assert config.evidence["mcpProtocolReady"] is True

    runbook = tools.runtime_runbook_generate(
        failure_family="MCP_REGISTRY_SNAPSHOT_MISMATCH",
        capabilities=["mcp", "runtime", "repository"],
        evidence_summary="Live registry differs from the approved snapshot.",
        mutation_allowed=True,
    )
    assert runbook.evidence["steps"][-2]["action"] == "end at one Draft PR; do not merge or deploy automatically"
    assert "exact revision cannot be resolved" in runbook.evidence["stopConditions"]

    ownership = tools.ownership_codeowners_guard(
        "job-operational-test",
        changed_paths=["tools/sovereign-chatgpt-mcp/operational_governance_tools.py"],
    )
    assert ownership.ok is True
    assert ownership.evidence["coverage"][0]["owners"] == ["@ouroboroscollective"]

    evidence = tools.EvidenceRecord(
        kind="deployment",
        identity="deploy-1",
        status="success",
        producer="host-worker",
        revision=revision,
    )
    control = tools.ComplianceControl(
        control_id="DEPLOY.1",
        description="Deployment evidence is revision bound.",
        required_evidence_kinds=["deployment"],
    )
    export = tools.compliance_evidence_export(
        revision=revision,
        evidence_records=[evidence],
        controls=[control],
    )
    assert export.ok is True
    assert export.evidence["artifactWritten"] is False
    assert export.evidence["export"]["claims"]["complianceCertified"] is False
    assert len(export.evidence["exportSha256"]) == 64


def test_evidence_payloads_redact_secret_shaped_values_and_require_real_backup_digest(registered) -> None:
    _, _, revision = registered
    secret_like = "sk-" + "proj-" + "x" * 24
    evidence = tools.EvidenceRecord(
        kind="approval",
        identity="approval-1",
        status="success",
        producer="owner-ui",
        revision=revision,
        summary=f"protected value {secret_like}",
    )
    control = tools.ComplianceControl(
        control_id="ACCESS.1",
        description="Protected values never enter evidence exports.",
        required_evidence_kinds=["approval"],
    )
    exported = tools.compliance_evidence_export(
        revision=revision,
        evidence_records=[evidence],
        controls=[control],
    )
    rendered = str(exported.evidence)
    assert secret_like not in rendered
    assert "[REDACTED_SECRET_SHAPED_VALUE]" in rendered
    assert exported.secretValuesReturned is False

    with pytest.raises(ValueError):
        tools.BackupRestoreEvidence(
            asset="postgres",
            backup_digest="",
            restored_digest="",
            restore_status="not-tested",
        )
