from __future__ import annotations

from pathlib import Path
import sys

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import wolfram_cag_staging_publication as publication


def _verified_receipt() -> dict:
    artifact_a = "1" * 64
    artifact_b = "2" * 64
    publication_receipt = {
        "schemaVersion": "sovereign.evidence-hf-publication-receipt.v2",
        "batchSha256": "3" * 64,
        "expectedTarget": f"dataset:{publication.HF_REPO_ID}@{publication.HF_STAGING_REVISION}",
        "observedTarget": f"dataset:{publication.HF_REPO_ID}@{publication.HF_STAGING_REVISION}",
        "prewriteTargetRevision": "a" * 40,
        "observedTargetRevision": "b" * 40,
        "observedArtifactHashes": [artifact_a, artifact_b],
        "writeAttemptIdentity": "4" * 64,
        "readbackIdentity": "5" * 64,
        "status": "PUBLISHED_VERIFIED",
        "idempotent": False,
    }
    return {
        "ok": True,
        "status": "PUBLISHED_VERIFIED",
        "batchId": "11111111-2222-4333-8444-555555555555",
        "repoId": publication.HF_REPO_ID,
        "revision": publication.HF_STAGING_REVISION,
        "commitOid": "b" * 40,
        "dataPath": "staging/atlas-batches/batch.jsonl",
        "manifestPath": "staging/atlas-batches/batch.manifest.json",
        "dataSha256": artifact_a,
        "manifestSha256": artifact_b,
        "batchSha256": "3" * 64,
        "readbackVerified": True,
        "runtimeIdentityUsed": True,
        "idempotent": False,
        "privacyScanHash": "6" * 64,
        "licenseRightsHash": "7" * 64,
        "publisherPolicyHash": "8" * 64,
        "publicationReceipt": publication_receipt,
        "publicationReceiptSha256": "9" * 64,
        "dedup": {"allIdentical": False},
    }


def test_cag_staging_rows_are_exact_fixed_public_fixture_scope() -> None:
    rows = publication.build_cag_staging_rows()

    assert tuple(row["caseId"] for row in rows) == publication.EXPECTED_CASE_IDS
    assert len(rows) == 12
    assert all(row["projectId"] == "wolfram-cag-benchmark" for row in rows)
    assert all(row["workflowState"] == "PUBLISHABLE" for row in rows)
    assert all(row["truthBoundary"]["liveCagResult"] is False for row in rows)
    assert all(row["truthBoundary"]["fixtureReference"] is True for row in rows)


def test_duplicate_noop_never_opens_database_or_claims_publish(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_publish(*, rows, repo_id, revision):
        captured["rows"] = rows
        captured["repo_id"] = repo_id
        captured["revision"] = revision
        return {
            "ok": True,
            "status": "DUPLICATE_NOOP",
            "batchId": "11111111-2222-4333-8444-555555555555",
            "repoId": repo_id,
            "revision": revision,
            "batchSha256": "3" * 64,
            "readbackVerified": False,
            "duplicateSemanticPublishSkipped": True,
        }

    def forbidden_connection():
        raise AssertionError("duplicate no-op must not persist a publication receipt")

    monkeypatch.setattr(publication, "publish_huggingface_batch", fake_publish)

    result = publication.publish_wolfram_cag_benchmark_staging(
        get_connection=forbidden_connection,
        admin_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )

    assert captured["repo_id"] == publication.HF_REPO_ID
    assert captured["revision"] == publication.HF_STAGING_REVISION
    assert tuple(row["caseId"] for row in captured["rows"]) == publication.EXPECTED_CASE_IDS
    assert result["status"] == "DUPLICATE_NOOP"
    assert result["mutationPerformed"] is False
    assert result["persistencePerformed"] is False
    assert result["persistenceVerified"] is False
    assert result["publishedCaseIds"] == []
    assert result["skippedCaseIds"] == list(publication.EXPECTED_CASE_IDS)


class _FakeCursor:
    def __init__(self, selected: dict) -> None:
        self.selected = selected
        self.current = None
        self.executed: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params=None) -> None:
        self.executed.append((query, params))
        if "INSERT INTO evidence_observatory_publish_receipts" in query:
            self.current = {"id": "receipt-1"}
        elif "FROM evidence_observatory_publish_receipts" in query:
            self.current = self.selected
        else:
            raise AssertionError("unexpected SQL")

    def fetchone(self):
        return self.current


class _FakeConnection:
    def __init__(self, selected: dict) -> None:
        self.cursor_instance = _FakeCursor(selected)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def test_verified_publish_persists_and_reads_back_exact_publication_receipt(monkeypatch) -> None:
    receipt = _verified_receipt()
    case_ids = list(publication.EXPECTED_CASE_IDS)
    selected = {
        "id": "receipt-1",
        "batch_id": receipt["batchId"],
        "repo_id": publication.HF_REPO_ID,
        "revision": publication.HF_STAGING_REVISION,
        "commit_oid": receipt["commitOid"],
        "data_sha256": receipt["dataSha256"],
        "manifest_sha256": receipt["manifestSha256"],
        "case_ids": case_ids,
        "readback_verified": True,
        "batch_sha256": receipt["batchSha256"],
        "license_rights_sha256": receipt["licenseRightsHash"],
        "privacy_scan_sha256": receipt["privacyScanHash"],
        "publisher_policy_sha256": receipt["publisherPolicyHash"],
        "observed_target_revision": receipt["publicationReceipt"]["observedTargetRevision"],
        "publication_status": "PUBLISHED_VERIFIED",
        "publication_receipt_sha256": receipt["publicationReceiptSha256"],
    }
    connection = _FakeConnection(selected)
    monkeypatch.setattr(publication, "publish_huggingface_batch", lambda **kwargs: receipt)

    result = publication.publish_wolfram_cag_benchmark_staging(
        get_connection=lambda: connection,
        admin_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )

    assert result["status"] == "PUBLISHED_VERIFIED"
    assert result["readbackVerified"] is True
    assert result["persistenceVerified"] is True
    assert result["persistencePerformed"] is True
    assert result["publishedCaseIds"] == case_ids
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed is True
    assert len(connection.cursor_instance.executed) == 2


def test_unverified_publish_is_rejected_before_database(monkeypatch) -> None:
    monkeypatch.setattr(
        publication,
        "publish_huggingface_batch",
        lambda **kwargs: {"ok": False, "status": "PUBLISHED_CONTRADICTED", "readbackVerified": False},
    )

    with pytest.raises(RuntimeError, match="cag_staging_publish_not_verified"):
        publication.publish_wolfram_cag_benchmark_staging(
            get_connection=lambda: (_ for _ in ()).throw(AssertionError("database must not open")),
            admin_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )
