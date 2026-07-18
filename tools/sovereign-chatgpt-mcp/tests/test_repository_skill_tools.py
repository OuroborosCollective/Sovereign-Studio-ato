from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import repository_skill_tools as skill_tools


WORKSPACE_ID = "job-skill-tools-test"


class FakeRuntime:
    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == WORKSPACE_ID
        return self.repo


class FakeDatabase:
    def schema_inventory(self):
        return {
            "ok": True,
            "status": "POSTGRES_SCHEMA_INVENTORY",
            "tables": [
                {"table_schema": "public", "table_name": "live_only_table"},
            ],
            "rowDataReturned": False,
            "secretValuesExposed": False,
        }

    def vector_canary(self):
        return {
            "ok": True,
            "extension_version": "0.8.0",
            "vector_columns": [],
        }


class FakeMCP:
    def __init__(self) -> None:
        self.names: list[str] = []

    def tool(self, *, annotations):
        assert annotations.readOnlyHint is True

        def decorator(function):
            self.names.append(function.__name__)
            return function

        return decorator


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )


@pytest.fixture()
def repository(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Sovereign Test")
    _git(repo, "config", "user.email", "sovereign-test@example.invalid")

    (repo / "backend").mkdir()
    (repo / "src").mkdir()
    (repo / "tools" / "sovereign-chatgpt-mcp").mkdir(parents=True)
    (repo / "backend" / "agent_runtime").mkdir()
    (repo / "scripts" / "sovereign-backend" / "migrations").mkdir(parents=True)
    (repo / "src" / "runtime").mkdir()
    (repo / ".github" / "workflows").mkdir(parents=True)
    secret_like = "sk-" + "proj-" + "x" * 30
    (repo / "backend" / "knowledge.py").write_text(
        "from pgvector.sqlalchemy import Vector\n"
        "DATABASE_VECTOR_DIMENSION = 1536\n"
        "# Authorization: Bearer super-secret-value\n"
        f"SECRET_ENDPOINT = '/api/knowledge/{secret_like}'\n"
        "def search_memory():\n"
        "    return '/api/knowledge/search?token=not-returned'\n",
        "utf-8",
    )
    (repo / "src" / "helper.ts").write_text(
        "export function helper() { return 'ok'; }\n",
        "utf-8",
    )
    (repo / "src" / "main.ts").write_text(
        "import { helper } from './helper';\n"
        "app.get('/api/knowledge/search', () => helper());\n",
        "utf-8",
    )
    (repo / "tools" / "sovereign-chatgpt-mcp" / "server.py").write_text(
        "def tool_contract():\n    return 'ready'\n",
        "utf-8",
    )
    (repo / "backend" / "app.py").write_text(
        "@app.get('/api/legacy-only')\n"
        "def legacy_only():\n    return 'not deployed'\n",
        "utf-8",
    )
    (repo / "scripts" / "sovereign-backend" / "app.py").write_text(
        "@app.route('/api/items/<item_id>', methods=['GET'])\n"
        "def item(item_id):\n    return item_id\n\n"
        "@app.post('/api/orders')\n"
        "def order():\n    return 'ok'\n",
        "utf-8",
    )
    (repo / "src" / "contracts.ts").write_text(
        "fetch(`/api/items/${itemId}`);\n"
        "api.post('/api/orders');\n"
        "api.post(`/api/items/${itemId}`);\n"
        "api.delete('/api/missing');\n",
        "utf-8",
    )
    (repo / "src" / "legacy.ts").write_text(
        "// sovereign-endpoint-surface: legacy-unreferenced\n"
        "fetch('/api/legacy-client');\n",
        "utf-8",
    )
    (repo / "scripts" / "sovereign-backend" / "migrations" / "001_create.sql").write_text(
        "-- CREATE TABLE IF NOT EXISTS does not create a table.\n"
        "/* CREATE TABLE block_comment_only (id bigint primary key); */\n"
        "CREATE TABLE IF NOT EXISTS architecture_events (id bigint primary key);\n",
        "utf-8",
    )
    (repo / ".github" / "workflows" / "dead.workflow").write_text(
        "name: ignored\njobs:\n  noop:\n    runs-on: ubuntu-latest\n    steps: []\n",
        "utf-8",
    )
    (repo / ".github" / "workflows" / "valid.yml").write_text(
        "name: valid\non: [push]\njobs:\n  validate:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n",
        "utf-8",
    )
    (repo / "backend" / "broken.py").write_text("def unsupported(:\n    pass\n", "utf-8")
    (repo / "src" / "runtime" / "keywordRouter.ts").write_text(
        "export const route = (text: string) => text.toLowerCase().includes('create');\n",
        "utf-8",
    )
    (repo / "backend" / "mirror.py").write_text("VALUE = 'canonical'\n", "utf-8")
    (repo / "scripts" / "sovereign-backend" / "mirror.py").write_text("VALUE = 'deployment'\n", "utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "fixture")

    monkeypatch.setattr(skill_tools, "_RUNTIME", FakeRuntime(repo))
    monkeypatch.setattr(skill_tools, "_DATABASE", None)
    monkeypatch.setattr(skill_tools, "_REGISTERED", False)
    return repo


def test_inventory_registers_eleven_read_only_tools(repository: Path) -> None:
    mcp = FakeMCP()
    skill_tools.register(mcp, FakeRuntime(repository))

    assert mcp.names == [
        "repository_skill_tool_inventory",
        "repository_knowledge_surface_scan",
        "repository_product_logic_map",
        "repository_change_impact_manifest",
        "repository_architecture_snapshot",
        "repository_architecture_drift_report",
        "repository_architecture_runtime_drift_evidence",
        "repository_mirror_diff_report",
        "repository_endpoint_reference",
        "repository_learning_records_normalize_preview",
        "repository_release_hunt_manifest",
    ]
    inventory = skill_tools.repository_skill_tool_inventory()
    assert inventory["status"] == "REPOSITORY_SKILL_TOOLS_READY"
    assert all(tool["mutates"] is False for tool in inventory["tools"])


def test_knowledge_and_logic_maps_are_secret_safe(repository: Path) -> None:
    knowledge = skill_tools.repository_knowledge_surface_scan(WORKSPACE_ID)
    logic = skill_tools.repository_product_logic_map(WORKSPACE_ID)

    assert knowledge["knowledgeEvidence"]["pgvector"]
    assert knowledge["summary"]["sensitiveMarkerCount"] == 2
    assert knowledge["sensitiveValuesReturned"] is False
    assert knowledge["databaseAccessed"] is False
    assert any(item["endpoint"].endswith("?<redacted>") for item in knowledge["knowledgeEndpointCandidates"])
    assert any(item["endpoint"] == "<redacted-endpoint>" for item in knowledge["knowledgeEndpointCandidates"])
    assert any(item["path"] == "backend/knowledge.py" for item in knowledge["knowledgeFiles"])

    rendered = json.dumps({"knowledge": knowledge, "logic": logic}, ensure_ascii=False)
    assert "super-secret-value" not in rendered
    assert "not-returned" not in rendered
    assert any(item["path"] == "/api/knowledge/search" for item in logic["logic"]["routes"])
    assert any(item["target"] == "src/helper.ts" for item in logic["logic"]["importEdges"])
    assert logic["truthNotice"].startswith("Static discovery")


def test_change_impact_and_release_hunt_remain_candidates(repository: Path) -> None:
    paths = [
        "backend/agent_runtime/cognitive_swarm_agents.py",
        "tools/sovereign-chatgpt-mcp/server.py",
    ]
    impact = skill_tools.repository_change_impact_manifest(WORKSPACE_ID, paths=paths)
    release = skill_tools.repository_release_hunt_manifest(WORKSPACE_ID, paths=paths)

    assert {"agents_sdk", "backend", "mcp_broker"}.issubset(set(impact["domains"]))
    assert "targeted MCP Pytest" in impact["requiredGates"]
    assert impact["headSha"]
    assert release["persistedOutcome"] is None
    assert release["nullfindCounterChanged"] is False
    assert all(item["status"] == "CANDIDATE_NOT_EXECUTED" for item in release["rankedFailureFamilies"])
    families = {item["failureFamily"] for item in release["rankedFailureFamilies"]}
    assert "AGENTS_SDK_RUN_PERSISTENCE" in families
    assert "MCP_BROKER_PROTOCOL_BOUNDARY" in families


def test_architecture_guardian_detects_cross_layer_drift_without_claiming_runtime_truth(repository: Path) -> None:
    snapshot = skill_tools.repository_architecture_snapshot(WORKSPACE_ID)
    repeated = skill_tools.repository_architecture_snapshot(WORKSPACE_ID)
    drift = skill_tools.repository_architecture_drift_report(WORKSPACE_ID)

    assert snapshot["snapshotSha256"] == repeated["snapshotSha256"]
    assert any(item["path"] == "/api/items/<p>" and item["methods"] == ["GET"] for item in snapshot["backendContracts"])
    assert any(item["path"] == "/api/orders" and item["methods"] == ["POST"] for item in snapshot["backendContracts"])
    assert any(item["path"] == "/api/items/<p>" and item["method"] == "POST" for item in snapshot["frontendCalls"])
    assert any(item["table"] == "architecture_events" for item in snapshot["sqlTables"])
    assert {item["table"] for item in snapshot["sqlTables"]} == {"architecture_events"}
    assert any(item["path"] == "backend/broken.py" for item in snapshot["parserFindings"])
    valid_workflow = next(item for item in snapshot["workflows"] if item["path"] == ".github/workflows/valid.yml")
    assert valid_workflow["validYaml"] is True if valid_workflow["parserAvailable"] else valid_workflow["validYaml"] is None
    assert snapshot["truthBoundary"]["liveDatabaseAccessed"] is False
    assert snapshot["truthBoundary"]["vpsAccessed"] is False
    assert snapshot["canonicalOwnership"] == [
        {
            "canonicalPath": "scripts/sovereign-backend/app.py",
            "nonCanonicalPath": "backend/app.py",
            "role": "production_backend_application",
            "reason": "The immutable backend image builds exclusively from scripts/sovereign-backend.",
            "byteEqualityRequired": False,
            "endpointTruthSource": "canonical_only",
        }
    ]
    assert not any(item["path"] == "/api/legacy-only" for item in snapshot["backendContracts"])

    families = {item["family"] for item in drift["findings"]}
    assert "CONTRACT_DRIFT" in families
    assert "CONTRACT_METHOD_DRIFT" in families
    assert "CI_DEAD_CHECK" in families
    assert "LLM_TOOL_BOUNDARY" in families
    assert "PYTHON_GRAMMAR_VERSION_DRIFT_OR_INVALID_SOURCE" in families
    assert "CANONICAL_DEPLOYMENT_MIRROR_DRIFT" in families
    assert drift["persistedOutcome"] is None
    assert drift["mutationPerformed"] is False
    assert "Static candidates" in drift["truthNotice"]


def test_mirror_diff_and_endpoint_reference_are_precise_and_read_only(repository: Path) -> None:
    mirror = skill_tools.repository_mirror_diff_report(
        WORKSPACE_ID,
        paths=["backend/mirror.py"],
    )
    endpoints = skill_tools.repository_endpoint_reference(WORKSPACE_ID)

    assert mirror["mismatchCount"] == 1
    assert mirror["reports"][0]["source"] == "backend/mirror.py"
    assert mirror["reports"][0]["mirror"] == "scripts/sovereign-backend/mirror.py"
    assert mirror["reports"][0]["changedLineCount"] == 2
    assert mirror["mutationPerformed"] is False
    assert mirror["secretValuesReturned"] is False

    contracts = {(item["method"], item["path"]) for item in endpoints["endpoints"]}
    unmatched = {(item["method"], item["path"]) for item in endpoints["unmatchedFrontendCalls"]}
    non_active = {(item["method"], item["path"], item["surfaceStatus"]) for item in endpoints["nonActiveFrontendCalls"]}
    assert ("GET", "/api/items/<p>") in contracts
    assert ("POST", "/api/orders") in contracts
    assert ("POST", "/api/items/<p>") in unmatched
    assert ("DELETE", "/api/missing") in unmatched
    assert ("GET", "/api/legacy-client", "legacy-unreferenced") in non_active
    assert endpoints["nonActiveFrontendCallCount"] == 1
    assert endpoints["generatedFromCurrentRepository"] is True
    assert endpoints["runtimeReachabilityProven"] is False
    assert endpoints["mutationPerformed"] is False


def test_architecture_runtime_drift_uses_only_schema_metadata(repository: Path, monkeypatch) -> None:
    monkeypatch.setattr(skill_tools, "_DATABASE", FakeDatabase())

    result = skill_tools.repository_architecture_runtime_drift_evidence(WORKSPACE_ID)

    families = {item["family"] for item in result["findings"]}
    assert result["status"] == "ARCHITECTURE_RUNTIME_DRIFT_EVIDENCE_READY"
    assert "DB_DRIFT_MISSING_LIVE_TABLE" in families
    assert "DB_DRIFT_UNMAPPED_LIVE_TABLE" in families
    assert result["schemaInventory"]["rowDataReturned"] is False
    assert result["mutationPerformed"] is False
    assert result["rowDataReturned"] is False
    assert result["secretValuesExposed"] is False


def test_normalization_preview_deduplicates_without_writing(repository: Path) -> None:
    record = {
        "title": " Evidence gate ",
        "problem": "Model output was treated as runtime success.",
        "context": "Agent execution",
        "solution": "Require a real tool result and persisted evidence.",
        "applicability": "Runtime truth paths",
        "validation": ["Run the real-path regression test"],
        "tags": ["Runtime Truth", "runtime truth"],
        "source_refs": [
            {
                "repository": "OuroborosCollective/Sovereign-Studio-ato",
                "revision": "a" * 40,
                "path": "backend/agent_runtime/evidence_gate.py",
                "lines": "1-20",
                "license": "project-owned",
            }
        ],
        "confidence": 0.9,
    }
    input_path = repository / "patterns.json"
    input_path.write_text(json.dumps([record, record]), "utf-8")

    result = skill_tools.repository_learning_records_normalize_preview(
        WORKSPACE_ID,
        "patterns.json",
        max_records=10,
    )

    assert result["status"] == "NORMALIZATION_PREVIEW_READY"
    assert result["inputRecords"] == 2
    assert result["outputRecords"] == 1
    assert result["duplicatesRemoved"] == 1
    assert result["databaseAccessed"] is False
    assert result["embeddingsGenerated"] is False
    assert result["repositoryWritten"] is False
    assert result["records"][0]["tags"] == ["runtime-truth"]
    assert result["records"][0]["content_hash"].startswith("sha256:")
    assert not (repository / "patterns.normalized.jsonl").exists()


def test_real_repository_architecture_snapshot_is_bounded_and_read_only() -> None:
    repo = Path(__file__).resolve().parents[3]
    result = skill_tools._architecture_snapshot(repo)
    rendered = json.dumps(result, ensure_ascii=False)

    assert len(result["revision"]) == 40
    assert result["backendContracts"]
    assert result["workflows"]
    assert result["truthBoundary"]["staticEvidenceOnly"] is True
    assert result["truthBoundary"]["liveDatabaseAccessed"] is False
    assert result["truthBoundary"]["vpsAccessed"] is False
    assert len(rendered.encode("utf-8")) < 1_000_000


def test_real_repository_knowledge_scan_is_bounded_and_read_only() -> None:
    repo = Path(__file__).resolve().parents[3]
    result = skill_tools._scan(repo, include_logic=False)
    rendered = json.dumps(result, ensure_ascii=False)

    assert len(result["revision"]) == 40
    assert result["summary"]["trackedFiles"] > 100
    assert result["summary"]["knowledgeTechnologies"] >= 1
    assert result["databaseAccessed"] is False
    assert result["sensitiveValuesReturned"] is False
    assert len(rendered.encode("utf-8")) < 1_000_000


def test_normalization_blocks_secret_markers_and_unsafe_paths(repository: Path) -> None:
    unsafe_record = {
        "title": "Unsafe",
        "problem": "Secret included",
        "solution": "Keep the identifier free of secrets.",
        "pattern_id": "sk-proj-" + "x" * 30,
        "applicability": "none",
        "validation": ["blocked"],
        "source_refs": [
            {
                "repository": "example/repo",
                "revision": "b" * 40,
                "path": "file.py",
                "lines": "1",
                "license": "MIT",
            }
        ],
        "confidence": 0.1,
    }
    (repository / "unsafe.json").write_text(json.dumps([unsafe_record]), "utf-8")

    blocked = skill_tools.repository_learning_records_normalize_preview(
        WORKSPACE_ID,
        "unsafe.json",
    )
    assert blocked["status"] == "NORMALIZATION_PREVIEW_BLOCKED"
    assert blocked["records"] == []
    assert "pattern_id" in blocked["errors"][0]["error"]

    with pytest.raises(ValueError, match="unsafe"):
        skill_tools.repository_change_impact_manifest(
            WORKSPACE_ID,
            paths=["../../etc/passwd"],
        )
