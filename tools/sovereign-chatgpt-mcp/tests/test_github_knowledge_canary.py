from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
MCP = ROOT / "tools" / "sovereign-chatgpt-mcp"
sys.path.insert(0, str(MCP))

import command_contract
import github_knowledge_canary


REVISION = "a" * 40
DIGEST = "sha256:" + "b" * 64


def test_embedded_backend_canary_script_is_valid_python() -> None:
    compile(github_knowledge_canary._BACKEND_CANARY_SCRIPT, "github-knowledge-canary", "exec")


def test_canary_source_is_fixed_public_github_file_without_query() -> None:
    assert github_knowledge_canary.PUBLIC_SOURCE_URL == (
        "https://github.com/octocat/Hello-World/blob/master/README"
    )
    assert "?" not in github_knowledge_canary.PUBLIC_SOURCE_URL
    assert "#" not in github_knowledge_canary.PUBLIC_SOURCE_URL


def test_canary_requires_exact_runtime_identity() -> None:
    runtime = github_knowledge_canary.GitHubKnowledgeCanaryRuntime()

    with pytest.raises(ValueError, match="Commit-SHA"):
        runtime.live_canary(expected_revision="main", expected_image_digest=DIGEST)
    with pytest.raises(ValueError, match="sha256-Digest"):
        runtime.live_canary(expected_revision=REVISION, expected_image_digest="latest")


def test_canary_success_requires_cleanup_and_secret_free_readback(monkeypatch) -> None:
    observed = {}
    payload = {
        "ok": True,
        "status": "GITHUB_KNOWLEDGE_LIVE_CANARY_VERIFIED",
        "sourceRevision": REVISION,
        "imageDigest": DIGEST,
        "evidence": {
            "source": {
                "status": "ready",
                "chunkCount": 2,
                "embeddedCount": 2,
                "candidateCount": 2,
                "outboxCount": 2,
                "publicReadWithoutCredential": True,
            },
            "transportFailure": {
                "blocker": "github_api_timeout",
                "httpStatus": 504,
                "auditRecorded": True,
                "rawUrlPersisted": False,
                "rawExceptionPersisted": False,
            },
        },
        "cleanup": {
            "sourceRows": 0,
            "linkRows": 0,
            "candidateRows": 0,
            "blockRows": 0,
            "outboxRows": 0,
            "auditRows": 0,
        },
        "cleanupVerified": True,
        "mutationPerformed": True,
        "secretValuesReturned": False,
        "documentContentReturned": False,
    }

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(github_knowledge_canary.subprocess, "run", fake_run)
    result = github_knowledge_canary.GitHubKnowledgeCanaryRuntime().live_canary(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
    )

    assert result == payload
    assert observed["argv"][-3:] == [REVISION, DIGEST, github_knowledge_canary.PUBLIC_SOURCE_URL]
    script = str(observed["input"])
    assert "public GitHub fetch was not credential-free" in script
    assert "knowledge_learning_candidates" in script
    assert "vector_index_outbox" in script
    assert "github_api_timeout" in script
    assert "DELETE FROM knowledge_sources" in script
    assert "secretValuesReturned" in script


def test_terminal_success_without_complete_evidence_is_rejected(monkeypatch) -> None:
    incomplete = {
        "ok": True,
        "status": "GITHUB_KNOWLEDGE_LIVE_CANARY_VERIFIED",
        "sourceRevision": REVISION,
        "imageDigest": DIGEST,
        "evidence": {
            "source": {
                "status": "ready",
                "chunkCount": 1,
                "embeddedCount": 1,
                "candidateCount": 1,
                "outboxCount": 1,
                "publicReadWithoutCredential": True,
            },
            "transportFailure": {
                "blocker": "github_api_timeout",
                "httpStatus": 504,
                "auditRecorded": False,
                "rawUrlPersisted": False,
                "rawExceptionPersisted": False,
            },
        },
        "cleanupVerified": True,
        "cleanup": {
            "sourceRows": 0,
            "linkRows": 0,
            "candidateRows": 0,
            "blockRows": 0,
            "outboxRows": 0,
            "auditRows": 0,
        },
        "secretValuesReturned": False,
        "documentContentReturned": False,
    }

    monkeypatch.setattr(
        github_knowledge_canary.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps(incomplete) + "\n", stderr=""
        ),
    )

    result = github_knowledge_canary.GitHubKnowledgeCanaryRuntime().live_canary(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
    )

    assert result["ok"] is False
    assert result["status"] == "GITHUB_KNOWLEDGE_LIVE_CANARY_FAILED"


def test_canary_failure_never_returns_stderr_or_document_content(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout='{"ok":false,"status":"GITHUB_KNOWLEDGE_LIVE_CANARY_FAILED"}\n',
            stderr="raw secret-shaped failure detail",
        )

    monkeypatch.setattr(github_knowledge_canary.subprocess, "run", fake_run)
    result = github_knowledge_canary.GitHubKnowledgeCanaryRuntime().live_canary(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
    )

    assert result["ok"] is False
    assert result["status"] == "GITHUB_KNOWLEDGE_LIVE_CANARY_FAILED"
    assert result["stderrType"] == "present"
    assert "raw secret-shaped" not in str(result)
    assert result["secretValuesReturned"] is False
    assert result["documentContentReturned"] is False


def test_canary_runs_only_through_host_worker_mutation_boundary() -> None:
    assert command_contract.is_mutating_action("github_knowledge_live_canary") is True


def test_canary_is_registered_and_packaged_for_mcp_and_host_broker() -> None:
    server = (MCP / "server.py").read_text("utf-8")
    broker = (MCP / "broker.py").read_text("utf-8")
    dockerfile = (MCP / "Dockerfile").read_text("utf-8")
    installer = (MCP / "deploy" / "install-on-vps.sh").read_text("utf-8")

    assert "def github_knowledge_live_canary(" in server
    assert '"github_knowledge_live_canary"' in broker
    assert "github_knowledge_canary.py" in dockerfile
    assert 'install -m 0640 "$SOURCE_DIR/github_knowledge_canary.py"' in installer
    assert "import github_knowledge_canary" in installer
    assert "callable(server.github_knowledge_live_canary)" in installer
