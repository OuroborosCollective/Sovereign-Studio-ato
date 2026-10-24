"""MIHA pre-execution is real, read-only, revision-bound and fail-closed."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import hashlib
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/sovereign-backend"))
sys.path.insert(0, str(ROOT))
from backend.agent_runtime import repository_miha_hunt as miha
from backend.agent_runtime import repository_execution as execution
from backend.agent_runtime.tools.base import ToolResult


def test_preexecution_gate_precedes_permission_and_durable_enqueue():
    content = (ROOT / "backend/agent_runtime/repository_execution.py").read_text()
    start = content.split("def start_repository_execution(", 1)[1].split(
        "def _submit_pending_repository_job(", 1)[0]
    assert start.index("run_repository_miha_code_hunt(") < start.index("_bind_repository_execution_permission(")
    assert start.index("persist_repository_miha_code_hunt(") < start.index("_pending_submit_ref(")
    assert '"miha_preexecution_blocked"' in start
    assert "except Exception as exc:" in start


def test_miha_scan_real_repository_readback_and_neighbor_source(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    repo = root / "agent-1" / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "example.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "example.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.invalid",
                    "-c", "user.name=Test", "commit", "-qm", "base"], check=True)
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    digest = hashlib.sha256((repo / "example.py").read_bytes()).hexdigest()
    scans = []
    def scan(_job, action, params, _root):
        scans.append((action, params))
        return ToolResult(status="done", metadata={
            "mode": "scan", "writeAction": False, "scannedFiles": 1,
            "findings": [{"path": "example.py", "line": 1, "ruleId": "PY-BARE-EXCEPT",
                          "severity": "medium", "contentSha256": digest}],
        })
    monkeypatch.setattr(miha, "run_agent_job_tool", scan)
    job = SimpleNamespace(job_id="agent-1", user_id="owner", workspace_id="agent-1",
                          repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
                          branch="main", mission="Inspect this repo")
    receipt = miha.run_repository_miha_code_hunt(job, workspace_root=root, expected_head_sha=head)
    assert receipt["nodes"][1]["contentSha256"] == digest
    assert receipt["expectedHeadSha"] == head
    assert receipt["datasetExport"] == "PRIVATE_BLOCKED"
    assert receipt["scanReadOnly"] is True
    assert len(receipt["nodes"]) <= 6
    assert scans[0][0] == "janitor"
    assert scans[0][1]["mode"] == "scan"
    assert scans[0][1]["explainWithLocalModel"] is False
    assert not subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"])


def test_miha_rejects_missing_revision_before_scan(monkeypatch, tmp_path):
    root = tmp_path
    repo = root / "agent-1" / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(miha, "run_agent_job_tool", lambda *a, **k: pytest.fail("scan must not run"))
    job = SimpleNamespace(job_id="agent-1", workspace_id="agent-1")
    with pytest.raises(miha.MihaCodeHuntError, match="MIHA_EXPECTED_REVISION_INVALID"):
        miha.run_repository_miha_code_hunt(job, workspace_root=root, expected_head_sha="invalid")


def test_miha_rejects_tampered_source_digest(tmp_path):
    path = tmp_path / "main.py"
    path.write_text("print(1)\n", encoding="utf-8")
    with pytest.raises(miha.MihaCodeHuntError, match="MIHA_SOURCE_HASH_MISMATCH"):
        miha._verified_source(tmp_path, {"path": "main.py", "line": 1,
            "ruleId": "PY-SYNTAX-ERROR", "severity": "critical", "contentSha256": "0" * 64})


def test_miha_receipt_is_persisted_and_read_back_by_exact_job():
    class Cursor:
        def __init__(self, parent): self.parent = parent
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, args):
            self.parent.sql.append(sql)
            self.parent.args.append(args)
        def fetchone(self):
            if len(self.parent.sql) == 1: return {"id": 42}
            return {"payload": self.parent.args[0][-1]}

    class Conn:
        def __init__(self): self.sql, self.args, self.commits = [], [], 0
        def cursor(self): return Cursor(self)
        def commit(self): self.commits += 1

    conn = Conn()
    graph = {"schemaVersion": miha.MIHA_SCHEMA, "jobId": "agent-1", "nodes": []}
    receipt = {**graph, "receiptSha256": miha._hash(graph)}
    assert miha.persist_repository_miha_code_hunt(conn, job_id="agent-1", receipt=receipt) == receipt["receiptSha256"]
    assert conn.commits == 1
    assert "RETURNING id" in conn.sql[0]
    assert "WHERE id = %s AND job_id = %s" in conn.sql[1]
    assert conn.args[1] == (42, "agent-1")


def test_miha_receipt_rejects_tampering_before_persistence():
    with pytest.raises(miha.MihaCodeHuntError, match="MIHA_RECEIPT_HASH_INVALID"):
        miha.persist_repository_miha_code_hunt(
            object(), job_id="agent-1",
            receipt={"schemaVersion": miha.MIHA_SCHEMA, "jobId": "agent-1", "receiptSha256": "0" * 64})


def test_miha_canonical_mirror_parity():
    a = (ROOT / "backend/agent_runtime/repository_miha_hunt.py").read_bytes()
    b = (ROOT / "scripts/sovereign-backend/agent_runtime/repository_miha_hunt.py").read_bytes()
    assert a == b


@pytest.mark.parametrize("source, expected_findings", [
    ("print('ok')\n", 0),
    ("try:\n    print('ok')\nexcept:\n    pass\n", 2),
])
def test_miha_accepts_real_provider_neutral_scan(tmp_path, source, expected_findings):
    root = tmp_path / "workspaces"
    repo = root / "agent-real-scan" / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "example.py").write_text(source, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "example.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.invalid",
                    "-c", "user.name=Test", "commit", "-qm", "base"], check=True)
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    job = SimpleNamespace(job_id="agent-real-scan", user_id="owner", workspace_id="agent-real-scan",
                          repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
                          branch="main", mission="Inspect this repo")

    # Exercise the registered Janitor through the real immutable-result kernel.
    result = miha.run_agent_job_tool(job, "janitor", {
        "mode": "scan", "maxFindings": 20, "maxFiles": 200,
        "includeDocs": True, "explainWithLocalModel": False,
    }, root)
    assert result.status == "done"
    assert isinstance(result.metadata["findings"], tuple)
    assert len(result.metadata["findings"]) == expected_findings
    receipt = miha.run_repository_miha_code_hunt(job, workspace_root=root, expected_head_sha=head)
    assert receipt["totalStaticCandidates"] == expected_findings
    assert receipt["scannedFiles"] == 1
    assert receipt["observedHeadSha"] == head
    assert receipt["scanReadOnly"] is True
    for finding in receipt["nodes"][1:]:
        assert finding["contentSha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert not subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"])
