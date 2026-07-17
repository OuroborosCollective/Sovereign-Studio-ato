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
    (repo / "backend" / "knowledge.py").write_text(
        "from pgvector.sqlalchemy import Vector\n"
        "DATABASE_VECTOR_DIMENSION = 1536\n"
        "# Authorization: Bearer super-secret-value\n"
        "SECRET_ENDPOINT = '/api/knowledge/sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'\n"
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
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "fixture")

    monkeypatch.setattr(skill_tools, "_RUNTIME", FakeRuntime(repo))
    monkeypatch.setattr(skill_tools, "_REGISTERED", False)
    return repo


def test_inventory_registers_six_read_only_tools(repository: Path) -> None:
    mcp = FakeMCP()
    skill_tools.register(mcp, FakeRuntime(repository))

    assert mcp.names == [
        "repository_skill_tool_inventory",
        "repository_knowledge_surface_scan",
        "repository_product_logic_map",
        "repository_change_impact_manifest",
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
