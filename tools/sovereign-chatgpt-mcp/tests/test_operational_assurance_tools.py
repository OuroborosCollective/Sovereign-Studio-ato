from __future__ import annotations

from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

import operational_assurance_tools as tools


class FakeRuntime:
    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == "job-assurance-test"
        return self.repo


class FakeDatabase:
    def canary(self) -> dict:
        return {"ok": True, "status": "POSTGRES_CANARY_VERIFIED"}

    def vector_canary(self) -> dict:
        return {"ok": True, "status": "PGVECTOR_VERIFIED"}


class FakeBroker:
    def status(self) -> dict:
        return {"ok": True, "status": "BROKER_READY"}

    def call(self, action: str, arguments: dict, timeout: int = 30) -> dict:
        if action == "runtime_capacity_snapshot":
            return {
                "ok": True,
                "status": "RUNTIME_CAPACITY_SNAPSHOT_READY",
                "host": {
                    "cpuCount": 4,
                    "load1mMilli": 800,
                    "memory": {"totalBytes": 16_000, "usedBytes": 4_000},
                    "swap": {"totalBytes": 8_000, "usedBytes": 100},
                },
                "filesystems": [
                    {"path": "/", "usedPpm": 250_000, "inodeUsedPpm": 100_000},
                ],
                "containers": [
                    {"name": "sovereign-backend", "oomKilled": False},
                ],
                "hostCommandQueue": {"pending": 0, "oldestAgeSeconds": 0},
            }
        if action == "container_status":
            return {
                "ok": True,
                "status": "VERIFIED",
                "container": arguments["container"],
                "state": {"Running": True, "Status": "running"},
            }
        if action == "document_pipeline_live_canary":
            return {
                "ok": True,
                "status": "DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED",
                "sourcePersisted": False,
                "outputPersisted": False,
            }
        if action == "memory_gateway_collection_canary":
            return {
                "ok": True,
                "status": "MEMORY_COLLECTION_CANARY_VERIFIED",
                "collectionDropped": True,
            }
        raise AssertionError(action)


@pytest.fixture()
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "dynamic.py").write_text("def run(code):\n    return eval(code)\n", "utf-8")
    (repo / "src" / "config.py").write_text(
        "API_KEY = 'sk-proj-" + "x" * 30 + "'\n",
        "utf-8",
    )
    return repo


@pytest.fixture()
def registered(repository: Path, monkeypatch):
    monkeypatch.setattr(tools, "_REGISTERED", False)
    monkeypatch.setattr(tools, "_MCP", None)
    monkeypatch.setattr(tools, "_RUNTIME", None)
    monkeypatch.setattr(tools, "_DATABASE", None)
    monkeypatch.setattr(tools, "_BROKER", None)
    mcp = FastMCP("operational-assurance-test")
    tools.register(mcp, FakeRuntime(repository), FakeDatabase(), FakeBroker())
    return mcp


def test_registers_all_assurance_tools_with_bounded_annotations(registered) -> None:
    actual = {tool.name: tool for tool in registered._tool_manager.list_tools()}
    expected = {
        "operational_assurance_skill_inventory",
        "vps_capacity_resource_pressure_assess",
        "runtime_dependency_health_matrix",
        "outbox_queue_liveness_assess",
        "scheduled_maintenance_coordinate",
        "runtime_topology_change_audit",
        "postgres_query_index_performance_assess",
        "data_integrity_invariant_audit",
        "data_repair_plan_build",
        "vector_memory_consistency_assess",
        "memory_poisoning_provenance_guard",
        "learning_pattern_lifecycle_preview",
        "data_retention_privacy_audit",
        "multi_tenant_isolation_verify",
        "mcp_schema_compatibility_audit",
        "mcp_protocol_conformance_fuzz_plan",
        "tool_permission_minimize",
        "dynamic_execution_containment_audit",
        "skill_capability_coverage_map",
        "skill_lifecycle_deprecation_preview",
        "skill_regression_benchmark",
        "tool_idempotency_verify",
        "owner_approval_policy_evaluate",
        "secret_lifecycle_rotation_assess",
        "secret_literal_triage",
        "sbom_provenance_image_signing_verify",
        "dependency_vulnerability_remediation_plan",
        "authentication_chaos_negative_test_assess",
    }
    assert set(actual) == expected
    assert len(expected) == 28
    for name, tool in actual.items():
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.output_schema["type"] == "object"
        assert tool.description.startswith("Use this when")
        if name == "runtime_dependency_health_matrix":
            assert tool.annotations.readOnlyHint is False
            assert tool.annotations.openWorldHint is True
        else:
            assert tool.annotations.readOnlyHint is True
    assert actual["vps_capacity_resource_pressure_assess"].annotations.openWorldHint is True


def test_inventory_reuses_existing_registry_and_capacity_reads_live_snapshot(registered) -> None:
    inventory = tools.operational_assurance_skill_inventory()
    assert inventory.status == "OPERATIONAL_ASSURANCE_SKILLS_READY"
    assert inventory.evidence["numberedSlots"] == 28
    assert inventory.evidence["newTools"] == 27
    assert inventory.evidence["existingReusedTools"] == ["mcp_tool_contract_registry"]

    capacity = tools.vps_capacity_resource_pressure_assess()
    assert capacity.ok is True
    assert capacity.runtimeVerified is True
    assert capacity.evidence["derived"]["memoryUsedPpm"] == 250_000
    assert capacity.mutationPerformed is False


def test_dependency_matrix_maps_failures_and_optional_canaries(registered) -> None:
    core = tools.runtime_dependency_health_matrix(include_ephemeral_canaries=False)
    assert core.ok is True
    assert core.mutationPerformed is False
    assert set(core.evidence["unknownDependencies"]) == {"document-pipeline", "milvus-memory-gateway"}

    full = tools.runtime_dependency_health_matrix(include_ephemeral_canaries=True)
    assert full.ok is True
    assert full.mutationPerformed is True
    by_name = {item["dependency"]: item for item in full.evidence["dependencies"]}
    assert by_name["postgresql"]["blockedFunctions"] == [
        "login",
        "credit verification",
        "agent runs",
        "knowledge source truth",
    ]
    assert by_name["document-pipeline"]["ok"] is True
    assert by_name["milvus-memory-gateway"]["ok"] is True


def test_queue_maintenance_and_topology_fail_closed(registered) -> None:
    queue = tools.outbox_queue_liveness_assess(
        [
            tools.QueueStreamEvidence(
                name="vector-index-outbox",
                pending=200,
                oldest_age_seconds=1_200,
                retries=5,
                dead_letters=1,
                processed_delta=0,
            )
        ]
    )
    assert queue.ok is False
    assert {item["family"] for item in queue.findings} >= {
        "QUEUE_NO_FORWARD_PROGRESS",
        "QUEUE_OLDEST_ITEM_STALE",
    }

    maintenance = tools.scheduled_maintenance_coordinate(
        tasks=[
            tools.MaintenanceTask(
                task_id="backup",
                category="backup",
                duration_seconds=100,
                earliest_start_epoch=1_000,
                latest_finish_epoch=2_000,
            ),
            tools.MaintenanceTask(
                task_id="deploy",
                category="deployment",
                duration_seconds=100,
                earliest_start_epoch=1_000,
                latest_finish_epoch=2_000,
                requires=["backup"],
                exclusive=True,
            ),
        ],
        window_start_epoch=1_000,
        window_end_epoch=2_000,
    )
    assert maintenance.ok is True
    assert [item["taskId"] for item in maintenance.evidence["schedule"]] == ["backup", "deploy"]

    topology = tools.runtime_topology_change_audit(
        tools.TopologySnapshot(
            revision="a" * 40,
            services={"backend": {"image": "one"}},
            networks={"internal": {"internal": True}},
            volumes={"data": {"driver": "local"}},
        ),
        tools.TopologySnapshot(
            revision="b" * 40,
            services={},
            networks={"internal": {"internal": False}},
            volumes={"data": {"driver": "local"}},
        ),
    )
    assert topology.ok is False
    assert any(item["family"] == "RUNTIME_TOPOLOGY_IDENTITY_REMOVED" for item in topology.findings)


def test_postgres_invariants_repair_and_vector_memory_contracts(registered) -> None:
    performance = tools.postgres_query_index_performance_assess(
        [
            tools.QueryFamilyEvidence(
                family="credit-ledger",
                calls=100,
                mean_ms=200,
                p95_ms=900,
                rows_read=10_000,
                rows_returned=10,
                sequential_scans=100,
                index_scans=1,
                lock_wait_ms=700,
            )
        ]
    )
    assert performance.ok is False
    assert any(item["family"] == "POSTGRES_LOCK_PRESSURE" for item in performance.findings)

    integrity = tools.data_integrity_invariant_audit(
        [
            tools.InvariantEvidence(
                invariant_id="CREDIT.LEDGER",
                description="Ledger sum equals credit cache.",
                expected=100,
                observed=90,
                scope_identity="user-1",
                revision="a" * 40,
            )
        ]
    )
    assert integrity.ok is False

    repair = tools.data_repair_plan_build(
        [
            tools.RepairCandidate(
                repair_id="credit-cache-user-1",
                target="credit-cache",
                predicate="tenant=user-1 and cache_version=4",
                desired_state={"balance_micros": 100},
                current_identity_hash="1" * 64,
                estimated_rows=2_501,
            )
        ],
        max_rows_per_batch=1_000,
    )
    plan = repair.evidence["plans"][0]
    assert plan["batches"] == 3
    assert len(plan["confirmationSha256"]) == 64
    assert repair.mutationPerformed is False

    vectors = tools.vector_memory_consistency_assess(
        [
            tools.VectorRecordEvidence(
                source_id="source-1",
                block_id="block-1",
                source_content_hash="2" * 64,
                vector_content_hash="3" * 64,
                embedding_model="old-model",
                expected_embedding_model="new-model",
                outbox_state="failed",
                vector_count=2,
                duplicate_vector_ids=1,
            )
        ]
    )
    assert vectors.ok is False
    assert {item["family"] for item in vectors.findings} >= {
        "VECTOR_DUPLICATE",
        "VECTOR_CONTENT_HASH_STALE",
        "VECTOR_OUTBOX_NOT_DELIVERABLE",
    }


def test_learning_privacy_and_tenant_isolation_controls(registered) -> None:
    poisoning = tools.memory_poisoning_provenance_guard(
        candidates=[
            tools.LearningCandidateEvidence(
                candidate_id="candidate-1",
                source_kind="runtime-fix",
                source_identity="pr-883",
                revision="a" * 40,
                test_evidence_count=0,
                scope="all repositories",
                created_epoch=1_000,
                expires_epoch=1_100,
                conflicts=["pattern-old"],
                outcome_count=1,
            )
        ],
        accepted_source_kinds=["runtime-fix"],
        current_revision="a" * 40,
        now_epoch=2_000,
    )
    assert poisoning.ok is False
    assert poisoning.evidence["decisions"][0]["decision"] == "quarantine"

    lifecycle = tools.learning_pattern_lifecycle_preview(
        records=[
            tools.PatternLifecycleRecord(
                pattern_id="pattern-1",
                version=2,
                state="active",
                content_hash="4" * 64,
            )
        ],
        action="remove",
        target_ids=["pattern-1"],
    )
    assert lifecycle.ok is False
    assert any(item["family"] == "ACTIVE_PATTERN_REMOVAL_BLOCKED" for item in lifecycle.findings)

    privacy = tools.data_retention_privacy_audit(
        [
            tools.RetentionRule(
                dataset="agent-runs",
                retention_days=90,
                deletion_verified=False,
                pseudonymization="required",
                export_supported=True,
                tenant_key_present=False,
            )
        ]
    )
    assert privacy.ok is False

    isolation = tools.multi_tenant_isolation_verify(
        tests=[
            tools.IsolationTestResult(
                surface=surface,
                test_id=f"negative-{surface}",
                negative_access_denied=True,
                cross_tenant_identifier_redacted=True,
                budget_isolated=True,
                evidence_identity=f"evidence-{surface}",
            )
            for surface in ("user", "project", "repository", "credit", "memory", "agent-run")
        ]
    )
    assert isolation.ok is True


def test_mcp_governance_permission_and_static_containment(registered) -> None:
    schema = {"tool": {"input": {"type": "object"}, "output": {"type": "object"}}}
    compatibility = tools.mcp_schema_compatibility_audit(
        tools.SchemaSurface(version="1", tools=schema),
        tools.SchemaSurface(version="1", tools=schema),
        tools.SchemaSurface(version="1", tools=schema),
        tools.SchemaSurface(version="1", tools=schema),
    )
    assert compatibility.ok is True

    fuzz = tools.mcp_protocol_conformance_fuzz_plan(max_payload_bytes=10_000, timeout_seconds=5)
    assert fuzz.ok is True
    assert fuzz.evidence["executed"] is False
    assert len(fuzz.evidence["cases"]) == 9

    permissions = tools.tool_permission_minimize(
        [
            tools.ToolPermissionRequirement(
                tool_name="example_tool",
                declared=["filesystem-read", "host-root"],
                observed=["filesystem-read"],
                required=["filesystem-read"],
            )
        ]
    )
    assert permissions.ok is True
    assert any(item["family"] == "TOOL_PERMISSION_OVERBROAD" for item in permissions.findings)

    dynamic = tools.dynamic_execution_containment_audit(
        "job-assurance-test",
        roots=["src"],
    )
    assert dynamic.ok is False
    assert any(item["family"] == "PYTHON_EVAL" for item in dynamic.findings)

    triage = tools.secret_literal_triage(
        "job-assurance-test",
        roots=["src"],
    )
    assert triage.ok is False
    assert triage.evidence["rotationCandidates"] == 1
    assert "sk-proj" not in str(triage.evidence)
    assert all(item["literalReturned"] is False for item in triage.findings)


def test_skill_idempotency_approval_secret_supply_chain_and_auth(registered) -> None:
    coverage = tools.skill_capability_coverage_map(
        [tools.CapabilityRequirement(task_id="capacity", required_capabilities=["capacity", "resource", "pressure"])]
    )
    assert coverage.runtimeVerified is True
    assert coverage.evidence["registeredToolCount"] == 28

    lifecycle = tools.skill_lifecycle_deprecation_preview(
        records=[
            tools.SkillLifecycleRecord(
                name="legacy-skill",
                state="active",
                replacement="",
                active_callers=2,
            )
        ],
        transitions=[tools.SkillTransitionRequest(name="legacy-skill", target_state="deprecated")],
    )
    assert lifecycle.ok is False

    benchmark = tools.skill_regression_benchmark(
        [
            tools.RegressionMission(
                mission_id="route-capacity",
                expected_tools=["vps_capacity_resource_pressure_assess"],
                actual_tools=["vps_capacity_resource_pressure_assess"],
                allowed_effects=["read"],
                observed_effects=["read"],
                required_evidence=["capacity"],
                observed_evidence=["capacity"],
            )
        ]
    )
    assert benchmark.ok is True

    idempotency = tools.tool_idempotency_verify(
        [
            tools.IdempotencyObservation(
                tool_name="repository_create_draft_pr",
                request_hash="5" * 64,
                invocation_count=2,
                unique_side_effect_ids=2,
                terminal_result_hashes=["6" * 64, "7" * 64],
            )
        ]
    )
    assert idempotency.ok is False

    approval = tools.owner_approval_policy_evaluate(
        rules=[tools.ApprovalRule(action_pattern="deploy-*", approval_required=True, ttl_seconds=900)],
        context=tools.ApprovalContext(
            action="deploy-mcp",
            revision="a" * 40,
            payload_hash="8" * 64,
            approval_created_epoch=1_000,
            approved_revision="a" * 40,
            approved_payload_hash="8" * 64,
            approval_status="approved",
        ),
        now_epoch=1_500,
    )
    assert approval.ok is True

    secrets = tools.secret_lifecycle_rotation_assess(
        references=[
            tools.SecretReference(
                secret_id="github-package-token",
                owner="platform-owner",
                target_system="ghcr",
                created_epoch=0,
                rotated_epoch=1_000,
                rotation_interval_days=90,
                last_canary_epoch=1_500,
                last_canary_ok=True,
            )
        ],
        now_epoch=2_000,
    )
    assert secrets.ok is True
    assert secrets.evidence["rawValuesRead"] is False

    supply = tools.sbom_provenance_image_signing_verify(
        tools.SupplyChainEvidence(
            revision="a" * 40,
            image_digest="sha256:" + "9" * 64,
            revision_label="a" * 40,
            sbom_digest="a" * 64,
            provenance_digest="b" * 64,
            signature_verified=True,
            attestation_verified=True,
            dependencies_pinned=True,
        )
    )
    assert supply.ok is True

    vulnerabilities = tools.dependency_vulnerability_remediation_plan(
        [
            tools.VulnerabilityEvidence(
                vulnerability_id="CVE-2026-0001",
                package="example",
                current_version="1.0.0",
                fixed_version="1.0.1",
                severity="high",
                reachable_production_path=True,
            )
        ]
    )
    assert vulnerabilities.ok is False

    auth = tools.authentication_chaos_negative_test_assess(
        tests=[
            tools.AuthNegativeTest(
                case=case,
                test_id=f"auth-{case}",
                denied_as_expected=True,
                state_unchanged=True,
                evidence_identity=f"evidence-{case}",
            )
            for case in (
                "oauth-state",
                "pkce",
                "passkey",
                "session-expiry",
                "step-up",
                "replay",
                "wrong-audience",
                "revoked-token",
                "parallel-access",
            )
        ]
    )
    assert auth.ok is True
