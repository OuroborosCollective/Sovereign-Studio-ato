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
import issue_closure_canary


REVISION = "a" * 40
BASELINE = "b" * 40
DIGEST = "sha256:" + "c" * 64
RELEASE_SHA = "d" * 64
PATCHMON_SHA = "e" * 64


def _verified_payload() -> dict:
    return {
        "ok": True,
        "status": "ISSUE_CLOSURE_RUNTIME_CANARY_VERIFIED",
        "sourceRevision": REVISION,
        "imageDigest": DIGEST,
        "baselineRevision": BASELINE,
        "releaseEvidenceSha256": RELEASE_SHA,
        "patchmonEvidenceSha256": PATCHMON_SHA,
        "evidenceBundleSha256": "f" * 64,
        "evidence": {
            "schema": {
                "requiredTableCount": 11,
                "presentTableCount": 11,
                "complete": True,
            },
            "bugEvidence": {
                "status": "verified",
                "appendOnlyRejected": True,
            },
            "durableMemory": {
                "evidenceClass": "verified",
                "crossScopeCandidateExcluded": True,
                "appendOnlyRejected": True,
            },
            "environmentMcpExecution": {
                "publicHttpsStatus": 200,
                "loopbackBlocked": True,
                "metadataIpBlocked": True,
                "blockedExecutionBuilderRejected": True,
                "blockedExecutionDatabaseRejected": True,
                "appendOnlyRejected": True,
            },
        },
        "persistentEvidence": True,
        "negativeProbeWritesCommitted": False,
        "mutationPerformed": True,
        "secretValuesReturned": False,
        "rowPayloadsReturned": False,
    }


def test_embedded_canary_script_is_valid_python() -> None:
    compile(issue_closure_canary._BACKEND_CANARY_SCRIPT, "issue-closure-canary", "exec")


def test_canary_requires_owner_approval_and_exact_identities() -> None:
    runtime = issue_closure_canary.IssueClosureCanaryRuntime()

    with pytest.raises(ValueError, match="owner_approved"):
        runtime.live_canary(
            expected_revision=REVISION,
            expected_image_digest=DIGEST,
            baseline_revision=BASELINE,
            release_evidence_sha256=RELEASE_SHA,
            patchmon_evidence_sha256=PATCHMON_SHA,
            owner_approved=False,
        )
    with pytest.raises(ValueError, match="Commit-SHA"):
        runtime.live_canary(
            expected_revision="main",
            expected_image_digest=DIGEST,
            baseline_revision=BASELINE,
            release_evidence_sha256=RELEASE_SHA,
            patchmon_evidence_sha256=PATCHMON_SHA,
            owner_approved=True,
        )


def test_success_requires_complete_persistence_scope_and_egress_evidence(monkeypatch) -> None:
    observed = {}
    payload = _verified_payload()

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(issue_closure_canary.subprocess, "run", fake_run)
    result = issue_closure_canary.IssueClosureCanaryRuntime().live_canary(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        baseline_revision=BASELINE,
        release_evidence_sha256=RELEASE_SHA,
        patchmon_evidence_sha256=PATCHMON_SHA,
        owner_approved=True,
    )

    assert result == payload
    assert observed["argv"][-5:] == [
        REVISION,
        DIGEST,
        BASELINE,
        RELEASE_SHA,
        PATCHMON_SHA,
    ]
    assert "run_issue_closure_canary" in str(observed["input"])


def test_incomplete_terminal_payload_is_rejected(monkeypatch) -> None:
    payload = _verified_payload()
    payload["evidence"]["environmentMcpExecution"]["blockedExecutionDatabaseRejected"] = False

    monkeypatch.setattr(
        issue_closure_canary.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps(payload) + "\n", stderr=""
        ),
    )
    result = issue_closure_canary.IssueClosureCanaryRuntime().live_canary(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        baseline_revision=BASELINE,
        release_evidence_sha256=RELEASE_SHA,
        patchmon_evidence_sha256=PATCHMON_SHA,
        owner_approved=True,
    )

    assert result["ok"] is False
    assert result["status"] == "ISSUE_CLOSURE_RUNTIME_CANARY_FAILED"
    assert result["secretValuesReturned"] is False
    assert result["rowPayloadsReturned"] is False


def test_canary_runs_only_through_host_worker_mutation_boundary() -> None:
    assert command_contract.is_mutating_action("issue_closure_runtime_canary") is True


def test_canary_is_registered_and_packaged_for_mcp_and_broker() -> None:
    server = (MCP / "server.py").read_text("utf-8")
    broker = (MCP / "broker.py").read_text("utf-8")
    dockerfile = (MCP / "Dockerfile").read_text("utf-8")
    installer = (MCP / "deploy" / "install-on-vps.sh").read_text("utf-8")
    broker_copy_loop = installer.split("for file in broker.py", 1)[1].split("\ndone", 1)[0]

    assert "def issue_closure_runtime_canary(" in server
    assert '"issue_closure_runtime_canary"' in broker
    assert "issue_closure_canary.py" in dockerfile
    assert "issue_closure_canary.py" in broker_copy_loop
    assert 'install_managed_control_plane_file 0640 "$SOURCE_DIR/$file" "$BROKER_DIR/$file" "broker/$file"' in broker_copy_loop
    assert "import issue_closure_canary" in installer
    assert "callable(server.issue_closure_runtime_canary)" in installer
