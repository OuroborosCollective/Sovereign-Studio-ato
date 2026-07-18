from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import deterministic_architecture_tools as tools


WORKSPACE_ID = "job-deterministic-tools-test"


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
        assert annotations.destructiveHint is False

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

    (repo / "src" / "runtime").mkdir(parents=True)
    (repo / "src" / "components").mkdir(parents=True)
    (repo / "backend" / "agent_runtime").mkdir(parents=True)
    (repo / "scripts" / "sovereign-backend" / "migrations").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "legacy").mkdir()

    (repo / "src" / "runtime" / "simulation.ts").write_text(
        "const KAPPA = 1000000;\n"
        "export function evolve(value: number) {\n"
        "  const drift = Math.random() * 0.5;\n"
        "  return Math.floor((value * value) / KAPPA) + Date.now() + drift;\n"
        "}\n",
        "utf-8",
    )
    (repo / "src" / "runtime" / "goodKappa.ts").write_text(
        "export const KAPPA_SCALE = 1_000_000n;\n"
        "export type KappaPos = bigint;\n",
        "utf-8",
    )
    (repo / "src" / "components" / "Particles.tsx").write_text(
        "export const Particle = () => Math.random();\n",
        "utf-8",
    )
    (repo / "backend" / "agent_runtime" / "legacy_logic.py").write_text(
        "import datetime\nimport random\nimport requests\n\n"
        "balance = 100.0\n\n"
        "def update():\n"
        "    global balance\n"
        "    balance += random.random()\n"
        "    requests.get('https://example.invalid')\n"
        "    return datetime.datetime.now(), balance\n",
        "utf-8",
    )
    (repo / "backend" / "agent_runtime" / "deterministic_math.py").write_text(
        "KAPPA = 1000000\n"
        "def to_fixed(value: float) -> int:\n"
        "    return int(round(value * KAPPA))\n"
        "def from_fixed(value: int) -> float:\n"
        "    return value / KAPPA\n",
        "utf-8",
    )
    (repo / "scripts" / "sovereign-backend" / "migrations" / "001_state.sql").write_text(
        "CREATE TABLE states (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);\n"
        "INSERT INTO states VALUES (1, CURRENT_TIMESTAMP);\n"
        "SELECT * FROM states LIMIT 10;\n",
        "utf-8",
    )
    (repo / "tests" / "test_fixture.py").write_text(
        "import random\n\ndef test_random_fixture():\n    assert random.random() >= 0\n",
        "utf-8",
    )
    (repo / "legacy" / "old.py").write_text("VALUE = 1\n", "utf-8")

    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "fixture")

    monkeypatch.setattr(tools, "_RUNTIME", FakeRuntime(repo))
    monkeypatch.setattr(tools, "_REGISTERED", False)
    return repo


def test_registers_eight_read_only_tools(repository: Path, monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_CROSS_RUNTIME_PARITY_PROVEN", raising=False)
    mcp = FakeMCP()
    tools.register(mcp, FakeRuntime(repository))

    assert mcp.names == [
        "deterministic_tool_inventory",
        "deterministic_architecture_inventory",
        "deterministic_nondeterminism_scan",
        "deterministic_kappa_contract_audit",
        "deterministic_sql_contract_audit",
        "deterministic_transition_validate",
        "deterministic_replay_verify",
        "deterministic_transformation_plan",
    ]
    inventory = tools.deterministic_tool_inventory()
    assert inventory["status"] == "DETERMINISTIC_ARCHITECTURE_TOOLS_READY"
    assert inventory["kappaScale"] == 1_000_000
    assert inventory["crossRuntimeParityProven"] is False
    assert inventory["parityEvidence"]["scope"] == "single_runtime_only"
    monkeypatch.setenv("SOVEREIGN_CROSS_RUNTIME_PARITY_PROVEN", "1")
    release_inventory = tools.deterministic_tool_inventory()
    assert release_inventory["crossRuntimeParityProven"] is True
    assert release_inventory["parityEvidence"]["scope"] == "installed_release"
    assert release_inventory["parityEvidence"]["singleReplayStillProvesParity"] is False
    assert inventory["boundaries"]["secondStateMachineCreated"] is False
    assert inventory["boundaries"]["sqliteTruthStoreCreated"] is False
    assert all(item["mutates"] is False for item in inventory["tools"])


def test_architecture_inventory_separates_truth_effect_projection_test_and_legacy(repository: Path) -> None:
    result = tools.deterministic_architecture_inventory(WORKSPACE_ID)
    surfaces = {item["path"]: item["surface"] for item in result["surfaces"]}

    assert surfaces["src/runtime/simulation.ts"] == "PURE_CORE_CANDIDATE"
    assert surfaces["src/components/Particles.tsx"] == "RUNTIME_PROJECTION"
    assert surfaces["backend/agent_runtime/legacy_logic.py"] == "LEGACY"
    assert surfaces["scripts/sovereign-backend/migrations/001_state.sql"] == "PERSISTED_TRUTH"
    assert surfaces["tests/test_fixture.py"] == "TEST_ONLY"
    assert result["mutationPerformed"] is False
    assert result["runtimeSuccessClaimed"] is False


def test_nondeterminism_scan_finds_uploaded_failure_families_without_promoting_runtime_truth(repository: Path) -> None:
    result = tools.deterministic_nondeterminism_scan(WORKSPACE_ID, max_findings=100)
    families = {item["family"] for item in result["findings"]}

    assert "RANDOMNESS_IN_TRUTH_PATH" in families
    assert "IMPLICIT_TIME_SOURCE" in families
    assert "IMPLICIT_MUTABLE_STATE" in families
    assert "EFFECT_INSIDE_LOGIC" in families
    assert "FLOAT_IN_TRUTH_PATH" in families
    assert "LIMIT_WITHOUT_ORDER_BY" in families
    assert result["runtimeSuccessClaimed"] is False
    assert all(item["status"] == "STATIC_CANDIDATE" for item in result["findings"])


def test_kappa_audit_rejects_float_first_demo_but_recognizes_bigint_surface(repository: Path) -> None:
    result = tools.deterministic_kappa_contract_audit(WORKSPACE_ID)
    families = {item["family"] for item in result["findings"]}
    surfaces = {item["path"]: item for item in result["contractSurfaces"]}

    assert result["contract"]["scale"] == 1_000_000
    assert result["contract"]["signedDivision"] == "TRUNCATE_TOWARD_ZERO"
    assert "FLOAT_KAPPA_BOUNDARY" in families
    assert "ROUND_BASED_KAPPA_CONVERSION" in families
    assert "FLOAT_KAPPA_OUTPUT" in families
    assert "JS_NUMBER_KAPPA_CONSTANT" in families
    assert surfaces["src/runtime/goodKappa.ts"]["hasBigInt"] is True


def test_sql_audit_requires_stable_order_explicit_columns_and_externalized_time(repository: Path) -> None:
    result = tools.deterministic_sql_contract_audit(WORKSPACE_ID)
    families = {item["family"] for item in result["findings"]}

    assert "LIMIT_WITHOUT_ORDER_BY" in families
    assert "SQL_IMPLICIT_TIME" in families
    assert "IMPLICIT_DATABASE_ID" in families
    assert "INSERT_WITHOUT_COLUMN_LIST" in families
    assert "idempotency_key" in result["requiredTruthColumns"]
    assert "chain_hash" in result["requiredTruthColumns"]
    assert result["mutationPerformed"] is False


def test_are_tool_wrappers_are_pure_and_replayable(repository: Path) -> None:
    table = {
        "RECEIVED": {"CLASSIFY": "SCOPING"},
        "SCOPING": {"PLAN": "PLANNED"},
    }
    state = {"status": "RECEIVED", "version": 0}
    action = {"type": "CLASSIFY", "patch": {"intent": "repository_execution"}}

    transition = tools.deterministic_transition_validate(state, action, table)
    replay = tools.deterministic_replay_verify(
        state,
        [action, {"type": "PLAN", "patch": {"planId": "plan-1"}}],
        table,
    )

    assert transition["status"] == "TRANSITION_VALIDATED"
    assert transition["mutationPerformed"] is False
    assert replay["status"] == "REPLAY_VERIFIED"
    assert replay["finalState"]["status"] == "PLANNED"
    assert replay["crossRuntimeParityProven"] is False


def test_transformation_plan_is_ordered_and_read_only(repository: Path) -> None:
    result = tools.deterministic_transformation_plan(WORKSPACE_ID, max_findings=40)

    assert [phase["phase"] for phase in result["phases"]] == [1, 2, 3, 4, 5]
    assert result["phases"][0]["name"] == "truth-boundary-classification"
    assert result["phases"][-1]["name"] == "deterministic-orchestration-cost-gates"
    assert result["rankedCandidates"]
    assert result["mutationPerformed"] is False
    assert result["runtimeSuccessClaimed"] is False


def test_real_repository_scans_are_bounded_and_read_only() -> None:
    repo = Path(__file__).resolve().parents[3]
    scan = tools._nondeterminism_scan(repo, 40)
    kappa = tools._kappa_audit(repo, 40)
    sql = tools._sql_audit(repo, 40)

    assert len(scan["revision"]) == 40
    assert scan["scannedFiles"] > 100
    assert scan["mutationPerformed"] is False
    assert scan["runtimeSuccessClaimed"] is False
    assert kappa["mutationPerformed"] is False
    assert kappa["runtimeSuccessClaimed"] is False
    assert sql["mutationPerformed"] is False
    assert sql["runtimeSuccessClaimed"] is False
    assert len(json.dumps({"scan": scan, "kappa": kappa, "sql": sql}).encode("utf-8")) < 1_000_000


def test_launcher_and_docker_image_include_deterministic_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "launcher.py").read_text("utf-8")
    dockerfile = (root / "Dockerfile").read_text("utf-8")

    assert "import deterministic_architecture_tools" in launcher
    assert "deterministic_architecture_tools.register(server.mcp, server.runtime)" in launcher
    assert "deterministic_contract.py" in dockerfile
    assert "deterministic_architecture_tools.py" in dockerfile
