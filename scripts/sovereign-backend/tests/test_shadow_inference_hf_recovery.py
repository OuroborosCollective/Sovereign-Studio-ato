from __future__ import annotations

import copy
import sys
import types
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from evidence_observatory_contracts import canonical_json, sha256_json  # noqa: E402
import shadow_inference_hf_recovery as recovery  # noqa: E402


def _receipt(*, source_revision: str, provider: str = "nscale", usage: dict | None = None) -> dict:
    body = {
        "schemaVersion": "sovereign.hf-shadow-receipt.v1",
        "recordType": "actual-inference",
        "observedAt": "2026-09-08T00:00:00Z",
        "actualInference": True,
        "primaryAuthority": "shadow-only",
        "provider": provider,
        "model": "model-a",
        "providerSurface": "hf-inference-providers",
        "requestCount": 1,
        "maxOutputTokens": 24,
        "seed": 1729,
        "temperature": 0,
        "promptSha256": "1" * 64,
        "outputSha256": "2" * 64,
        "planSha256": "3" * 64,
        "sourceRevision": source_revision,
        "automaticRetries": 0,
        "automaticFallback": False,
        "shadowOnly": True,
        "literalMatch": True,
        "secretValuesReturned": False,
        "truthVerdict": "NOT_ASSERTED",
        "finishReason": "stop",
        "latencyMs": 123,
        "credentialSource": "owner-managed-runtime",
        "promptClassification": "public-canary",
        "costClaim": "NOT_ASSERTED",
        "usage": usage or {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    body["receiptSha256"] = sha256_json(body)
    return body


def _bundle():
    sovereign = "a" * 40
    hf_misbound = "b" * 40
    good = _receipt(source_revision=sovereign)
    bad = _receipt(
        source_revision=hf_misbound,
        provider="groq",
        usage={
            "prompt_tokens": 5,
            "completion_tokens": 20,
            "total_tokens": 25,
            "queue_time": 0.01,
            "completion_tokens_details": {"reasoning_tokens": 18},
        },
    )
    return recovery.build_shadow_recovery_bundle(
        receipts=[good, bad],
        receipt_paths=["data/receipts/good.json", "data/receipts/bad.json"],
        sovereign_revisions={sovereign},
        hf_publication_revisions={hf_misbound},
        source_repository="OuroborosCollective/Sovereign-Studio-ato",
        candidate_revision=sovereign,
        hf_repo_id="Thorsu/sovereign-shadow-inference-bench",
        expected_hf_revision="c" * 40,
        existing_readme="# Existing research notes\n\nPreserve me.\n",
    )


def test_recovery_preserves_raw_receipts_and_separates_current_from_legacy_provenance():
    sovereign = "a" * 40
    hf_misbound = "b" * 40
    good = _receipt(source_revision=sovereign)
    bad = _receipt(source_revision=hf_misbound, provider="groq")
    original = copy.deepcopy([good, bad])

    bundle = recovery.build_shadow_recovery_bundle(
        receipts=[good, bad],
        receipt_paths=["data/receipts/good.json", "data/receipts/bad.json"],
        sovereign_revisions={sovereign},
        hf_publication_revisions={hf_misbound},
        source_repository="OuroborosCollective/Sovereign-Studio-ato",
        candidate_revision=sovereign,
        hf_repo_id="Thorsu/sovereign-shadow-inference-bench",
        expected_hf_revision="c" * 40,
        existing_readme="# Existing research notes\n",
    )

    assert [good, bad] == original
    assert bundle["manifest"]["canonicalReceiptsMutated"] is False
    assert bundle["manifest"]["verifiedViewerReceiptCount"] == 1
    assert bundle["manifest"]["legacyProvenanceCount"] == 1
    assert len(bundle["verifiedRows"]) == 1
    assert bundle["verifiedRows"][0]["sourceRevision"] == sovereign
    assert bundle["verifiedRows"][0]["sourceRevisionVerified"] is True
    assert len(bundle["supersessions"]) == 1
    assert bundle["supersessions"][0]["classification"] == "MISBOUND_HF_PUBLICATION_REVISION"
    assert bundle["supersessions"][0]["currentTruthEligible"] is False
    assert bundle["supersessions"][0]["canonicalReceiptMutated"] is False


def test_recovery_normalizes_provider_specific_usage_to_stable_json_text():
    bundle = _bundle()
    row = bundle["verifiedRows"][0]
    assert "usage" not in row
    assert isinstance(row["usageJson"], str)
    assert len(row["usageSha256"]) == 64

    artifacts = {artifact.path: artifact for artifact in bundle["artifacts"]}
    readme = artifacts["README.md"].content.decode("utf-8")
    assert "config_name: receipts_current" in readme
    assert "path: data/current/receipts-viewer.jsonl" in readme
    assert "config_name: provenance_legacy" in readme
    assert "path: data/provenance/supersessions.jsonl" in readme
    assert "data/receipts/*.json" not in readme
    assert "Preserve me." in readme


def test_recovery_rejects_duplicate_or_tampered_receipts():
    sovereign = "a" * 40
    receipt = _receipt(source_revision=sovereign)
    with pytest.raises(RuntimeError, match="shadow_duplicate_receipt"):
        recovery.build_shadow_recovery_bundle(
            receipts=[receipt, copy.deepcopy(receipt)],
            receipt_paths=["a.json", "b.json"],
            sovereign_revisions={sovereign},
            hf_publication_revisions=set(),
            source_repository="OuroborosCollective/Sovereign-Studio-ato",
            candidate_revision=sovereign,
            hf_repo_id="Thorsu/sovereign-shadow-inference-bench",
            expected_hf_revision="c" * 40,
            existing_readme="# Readme\n",
        )

    tampered = copy.deepcopy(receipt)
    tampered["latencyMs"] = 999
    with pytest.raises(RuntimeError, match="shadow_receipt_hash_mismatch"):
        recovery.build_shadow_recovery_bundle(
            receipts=[tampered],
            receipt_paths=["tampered.json"],
            sovereign_revisions={sovereign},
            hf_publication_revisions=set(),
            source_repository="OuroborosCollective/Sovereign-Studio-ato",
            candidate_revision=sovereign,
            hf_repo_id="Thorsu/sovereign-shadow-inference-bench",
            expected_hf_revision="c" * 40,
            existing_readme="# Readme\n",
        )


def test_recovery_blocks_secret_shapes_and_unverified_candidate_identity():
    sovereign = "a" * 40
    receipt = _receipt(source_revision=sovereign)
    receipt["note"] = "hf_" + "x" * 30
    receipt["receiptSha256"] = sha256_json({key: value for key, value in receipt.items() if key != "receiptSha256"})
    with pytest.raises(RuntimeError, match="shadow_public_secret_shape"):
        recovery.build_shadow_recovery_bundle(
            receipts=[receipt],
            receipt_paths=["secret.json"],
            sovereign_revisions={sovereign},
            hf_publication_revisions=set(),
            source_repository="OuroborosCollective/Sovereign-Studio-ato",
            candidate_revision=sovereign,
            hf_repo_id="Thorsu/sovereign-shadow-inference-bench",
            expected_hf_revision="c" * 40,
            existing_readme="# Readme\n",
        )

    clean = _receipt(source_revision=sovereign)
    with pytest.raises(RuntimeError, match="shadow_candidate_revision_not_verified"):
        recovery.build_shadow_recovery_bundle(
            receipts=[clean],
            receipt_paths=["clean.json"],
            sovereign_revisions={sovereign},
            hf_publication_revisions=set(),
            source_repository="OuroborosCollective/Sovereign-Studio-ato",
            candidate_revision="d" * 40,
            hf_repo_id="Thorsu/sovereign-shadow-inference-bench",
            expected_hf_revision="c" * 40,
            existing_readme="# Readme\n",
        )


def test_publish_requires_owner_and_exact_prewrite_revision(monkeypatch, tmp_path):
    bundle = _bundle()
    expected = "c" * 40

    with pytest.raises(RuntimeError, match="shadow_hf_owner_approval_required"):
        recovery.publish_shadow_recovery_bundle(
            bundle=bundle,
            repo_id="Thorsu/sovereign-shadow-inference-bench",
            expected_hf_revision=expected,
            owner_approved=False,
        )

    monkeypatch.setattr(recovery, "_load_huggingface_runtime_token", lambda: "hf_" + "x" * 40)
    state = {"head": "d" * 40, "files": {}}

    class HfApi:
        def __init__(self, token=None):
            assert token

        def repo_info(self, *, repo_id, repo_type, revision):
            return types.SimpleNamespace(sha=state["head"])

        def create_commit(self, **kwargs):
            raise AssertionError("write must not occur after prewrite mismatch")

    fake = types.ModuleType("huggingface_hub")
    fake.HfApi = HfApi
    fake.CommitOperationAdd = object
    fake.hf_hub_download = lambda **kwargs: ""
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)

    with pytest.raises(RuntimeError, match="shadow_hf_prewrite_revision_mismatch"):
        recovery.publish_shadow_recovery_bundle(
            bundle=bundle,
            repo_id="Thorsu/sovereign-shadow-inference-bench",
            expected_hf_revision=expected,
            owner_approved=True,
        )


def test_publish_reads_back_every_exact_artifact(monkeypatch, tmp_path):
    bundle = _bundle()
    expected = "c" * 40
    new_head = "e" * 40
    monkeypatch.setattr(recovery, "_load_huggingface_runtime_token", lambda: "hf_" + "x" * 40)
    state: dict[str, object] = {"head": expected, "files": {}}

    class CommitOperationAdd:
        def __init__(self, *, path_in_repo, path_or_fileobj):
            self.path_in_repo = path_in_repo
            self.path_or_fileobj = path_or_fileobj

    class HfApi:
        def __init__(self, token=None):
            assert token

        def repo_info(self, *, repo_id, repo_type, revision):
            return types.SimpleNamespace(sha=state["head"])

        def create_commit(self, *, operations, **kwargs):
            files = state["files"]
            assert isinstance(files, dict)
            for operation in operations:
                files[operation.path_in_repo] = operation.path_or_fileobj
            state["head"] = new_head
            return types.SimpleNamespace(oid=new_head)

    def hf_hub_download(*, filename, **kwargs):
        files = state["files"]
        assert isinstance(files, dict)
        local = tmp_path / filename.replace("/", "__")
        local.write_bytes(files[filename])
        return str(local)

    fake = types.ModuleType("huggingface_hub")
    fake.HfApi = HfApi
    fake.CommitOperationAdd = CommitOperationAdd
    fake.hf_hub_download = hf_hub_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)

    result = recovery.publish_shadow_recovery_bundle(
        bundle=bundle,
        repo_id="Thorsu/sovereign-shadow-inference-bench",
        expected_hf_revision=expected,
        owner_approved=True,
    )
    assert result["status"] == "PUBLISHED_VERIFIED"
    assert result["commitOid"] == new_head
    assert result["readbackVerified"] is True
    assert result["canonicalReceiptsMutated"] is False
    assert set(result["artifactHashes"]) == {artifact.path for artifact in bundle["artifacts"]}
