from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from command_contract import is_mutating_action
from evidence_observatory_cag_runtime import (
    CAG_CASE_IDS,
    HF_REPO_ID,
    HF_REVISION,
    EvidenceObservatoryCagPublicationRuntime,
)


REVISION = "a" * 40
DIGEST = "sha256:" + "b" * 64
HASH = "c" * 64
COMMIT = "d" * 40
RECEIPT_ID = "11111111-1111-4111-8111-111111111111"


def published_payload() -> dict[str, object]:
    return {
        "ok": True,
        "status": "CAG_STAGING_PUBLICATION_VERIFIED",
        "sourceRevision": REVISION,
        "imageDigest": DIGEST,
        "repoId": HF_REPO_ID,
        "revision": HF_REVISION,
        "caseIds": list(CAG_CASE_IDS),
        "publisherStatus": "PUBLISHED_VERIFIED",
        "batchId": "22222222-2222-4222-8222-222222222222",
        "batchSha256": HASH,
        "dataPath": "staging/atlas-batches/batch.jsonl",
        "manifestPath": "staging/atlas-batches/batch.manifest.json",
        "dataSha256": HASH,
        "manifestSha256": HASH,
        "privacyScanHash": HASH,
        "licenseRightsHash": HASH,
        "publisherPolicyHash": HASH,
        "commitOid": COMMIT,
        "publicationReceiptSha256": HASH,
        "publicationReceiptPersisted": True,
        "persistenceVerified": True,
        "targetReadbackVerified": True,
        "rightsReceiptValidatedByPublisher": True,
        "duplicateSemanticPublishSkipped": False,
        "mutationPerformed": True,
        "secretValuesReturned": False,
        "protectedRightsValueReturned": False,
    }


def duplicate_payload() -> dict[str, object]:
    value = published_payload()
    value.update({
        "status": "CAG_STAGING_DUPLICATE_NOOP_VERIFIED",
        "publisherStatus": "DUPLICATE_NOOP",
        "commitOid": None,
        "publicationReceiptSha256": None,
        "publicationReceiptPersisted": False,
        "persistenceVerified": False,
        "targetReadbackVerified": False,
        "duplicateSemanticPublishSkipped": True,
        "mutationPerformed": False,
    })
    return value


def fake_completed(payload: dict[str, object], returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["docker"],
        returncode=returncode,
        stdout=json.dumps(payload, sort_keys=True) + "\n",
        stderr="",
    )


def test_cag_publish_is_a_mutating_host_queue_action():
    assert is_mutating_action("evidence_observatory_cag_staging_publish") is True


def test_cag_runtime_requires_owner_revision_and_digest():
    runtime = EvidenceObservatoryCagPublicationRuntime()
    with pytest.raises(ValueError, match="Owner-Freigabe"):
        runtime.publish_staging(expected_revision=REVISION, expected_image_digest=DIGEST, owner_approved=False)
    with pytest.raises(ValueError, match="Commit-SHA"):
        runtime.publish_staging(expected_revision="main", expected_image_digest=DIGEST, owner_approved=True)
    with pytest.raises(ValueError, match="sha256-Digest"):
        runtime.publish_staging(expected_revision=REVISION, expected_image_digest="latest", owner_approved=True)


@pytest.mark.parametrize("payload_factory", [published_payload, duplicate_payload])
def test_cag_runtime_accepts_only_fully_bounded_terminal_evidence(monkeypatch, payload_factory):
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = list(argv)
        observed["input"] = kwargs.get("input")
        return fake_completed(payload_factory())

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = EvidenceObservatoryCagPublicationRuntime().publish_staging(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        owner_approved=True,
    )
    assert result["ok"] is True
    assert result["repoId"] == HF_REPO_ID
    assert result["revision"] == HF_REVISION
    assert result["caseIds"] == list(CAG_CASE_IDS)
    assert result["rightsReceiptValidatedByPublisher"] is True
    assert result["secretValuesReturned"] is False
    assert result["protectedRightsValueReturned"] is False
    assert observed["argv"][-2:] == [REVISION, DIGEST]
    script = str(observed["input"])
    assert "/api/admin/evidence-observatory/v1/publish/huggingface/cag-benchmark" in script
    assert "hf_publication_rights" not in script
    assert "authorizationText" not in script


def test_cag_runtime_rejects_incomplete_publication_readback(monkeypatch):
    payload = published_payload()
    payload["targetReadbackVerified"] = False
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_completed(payload))
    result = EvidenceObservatoryCagPublicationRuntime().publish_staging(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        owner_approved=True,
    )
    assert result["ok"] is False
    assert result["status"] == "CAG_STAGING_PUBLICATION_FAILED"
    assert result["failureFamily"] == "CAG_STAGING_PUBLICATION_EVIDENCE_INCOMPLETE"
    assert result["secretValuesReturned"] is False
    assert result["protectedRightsValueReturned"] is False


def test_cag_runtime_preserves_unknown_mutation_state_after_publish_request(monkeypatch):
    payload = {
        "ok": False,
        "status": "CAG_STAGING_PUBLICATION_FAILED",
        "sourceRevision": REVISION,
        "imageDigest": DIGEST,
        "mutationState": "UNKNOWN_AFTER_PUBLISH_REQUEST",
        "secretValuesReturned": False,
        "protectedRightsValueReturned": False,
    }
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_completed(payload, returncode=1))
    result = EvidenceObservatoryCagPublicationRuntime().publish_staging(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        owner_approved=True,
    )
    assert result["ok"] is False
    assert result["mutationState"] == "UNKNOWN_AFTER_PUBLISH_REQUEST"
    assert "mutationPerformed" not in result


def test_server_tool_accepts_no_rights_case_or_target_payload():
    root = Path(__file__).resolve().parents[1]
    source = (root / "server.py").read_text("utf-8")
    start = source.index("def evidence_observatory_cag_staging_publish(")
    end = source.index("\n\n@mcp.tool", start)
    block = source[start:end]
    assert "expected_revision" in block
    assert "expected_image_digest" in block
    assert "owner_approved" in block
    for forbidden in ("license_rights", "authorizationText", "case_ids", "repo_id", "revision: str"):
        assert forbidden not in block
