from __future__ import annotations

import copy
import sys
import types
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from evidence_observatory_contracts import canonical_json, sha256_text  # noqa: E402
from evidence_observatory_publisher import (  # noqa: E402
    PUBLISHER_POLICY,
    build_huggingface_publish_plan,
    publish_huggingface_batch,
    scan_public_payload,
)
from wolfram_cag_benchmark_publication import build_cag_benchmark_public_rows  # noqa: E402


REPO_ID = "Thorsu/sovereign-evidence-observatory"
REVISION = "staging-atlas"


def _rights(case_ids: list[str]) -> dict:
    text = (
        "One-time authorization for the Sovereign Evidence Observatory staging publisher to publish only the "
        "public-safe projections of the listed Wolfram CAG benchmark cases to the exact Hugging Face staging "
        "target. This does not authorize source-code publication or promotion to main."
    )
    return {
        "schemaVersion": "sovereign.hf-publication-rights.v1",
        "status": "AUTHORIZED",
        "rightsHolder": "Owner authorization receipt",
        "authorizedEntity": "Sovereign Evidence Observatory staging publisher",
        "purpose": "Publish the public-safe CAG benchmark projections for evidence evaluation.",
        "scope": "One exact staging batch only; no repository source code and no main promotion.",
        "licenseId": "other",
        "authorizedTarget": REPO_ID,
        "authorizedRevision": REVISION,
        "authorizedCaseIds": case_ids,
        "authorizationRef": "https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/1507",
        "authorizationText": text,
        "authorizationSha256": sha256_text(text),
        "conditions": [
            "staging branch only",
            "public-safe projections only",
            "no raw prompts, credentials, private records, or source code",
            "separate owner approval required for final public promotion",
        ],
    }


def test_cag_benchmark_builds_twelve_publishable_truth_bound_rows():
    rows = build_cag_benchmark_public_rows()
    assert len(rows) == 12
    assert [row["caseId"] for row in rows] == [f"cag-bench-{index:03d}" for index in range(1, 13)]
    assert all(row["workflowState"] == "PUBLISHABLE" for row in rows)
    assert all(row["gateReport"]["passed"] is True for row in rows)
    assert all(row["truthBoundary"]["liveCagResult"] is False for row in rows)
    verdicts = {row["caseId"]: row["verdict"] for row in rows}
    assert verdicts["cag-bench-002"] == "REFUTED"
    assert verdicts["cag-bench-007"] == "REFUTED"
    assert verdicts["cag-bench-011"] == "UNPROVEN"
    assert verdicts["cag-bench-012"] == "UNPROVEN"


def test_identical_cag_batch_has_deterministic_manifest_and_all_1507_hash_surfaces():
    rows = build_cag_benchmark_public_rows()
    rights = _rights([row["caseId"] for row in rows])
    first = build_huggingface_publish_plan(rows=rows, repo_id=REPO_ID, revision=REVISION, license_rights=rights)
    second = build_huggingface_publish_plan(rows=rows, repo_id=REPO_ID, revision=REVISION, license_rights=rights)
    assert first["batchId"] == second["batchId"]
    assert first["batchSha256"] == second["batchSha256"]
    assert first["manifestSha256"] == second["manifestSha256"]
    assert first["dataSha256"] == second["dataSha256"]
    manifest = first["manifest"]
    required = {
        "schema_version", "batch_id", "case_ids", "passport_hashes",
        "gate_receipt_hashes", "public_payload_hashes", "source_publication_refs",
        "license_rights_hash", "privacy_scan_hash", "publisher_policy_hash",
        "target_repo_identity", "batch_sha256",
    }
    assert required.issubset(manifest)
    assert len(manifest["case_ids"]) == 12
    assert len(manifest["passport_hashes"]) == 12
    assert len(manifest["gate_receipt_hashes"]) == 12
    assert len(manifest["public_payload_hashes"]) == 12
    assert len(manifest["source_publication_refs"]) == 12
    assert first["privacyScan"]["findingCount"] == 0
    assert PUBLISHER_POLICY["readbackBeforeRetry"] is True


def test_rights_are_fail_closed_for_unknown_license_target_and_case_scope():
    rows = build_cag_benchmark_public_rows()
    rights = _rights([row["caseId"] for row in rows])
    rights["licenseId"] = "UNKNOWN"
    with pytest.raises(RuntimeError, match="rights_license_unknown"):
        build_huggingface_publish_plan(rows=rows, repo_id=REPO_ID, revision=REVISION, license_rights=rights)

    rights = _rights([row["caseId"] for row in rows])
    rights["authorizedTarget"] = "someone/else"
    with pytest.raises(RuntimeError, match="rights_target_mismatch"):
        build_huggingface_publish_plan(rows=rows, repo_id=REPO_ID, revision=REVISION, license_rights=rights)

    rights = _rights([row["caseId"] for row in rows[:-1]])
    with pytest.raises(RuntimeError, match="rights_case_scope_mismatch"):
        build_huggingface_publish_plan(rows=rows, repo_id=REPO_ID, revision=REVISION, license_rights=rights)


def test_final_public_payload_scan_blocks_private_field_and_secret_shape():
    rows = build_cag_benchmark_public_rows()
    poisoned = copy.deepcopy(rows)
    poisoned[0]["method"]["token"] = "hf_abcdefghijklmnopqrstuvwxyz123456"
    report = scan_public_payload(poisoned)
    assert report["findingCount"] >= 1
    rights = _rights([row["caseId"] for row in poisoned])
    with pytest.raises(RuntimeError, match="huggingface_public_privacy_scan_blocked"):
        build_huggingface_publish_plan(
            rows=poisoned, repo_id=REPO_ID, revision=REVISION, license_rights=rights
        )


def test_stale_gate_or_passport_and_missing_provenance_block_before_hf_write():
    rows = build_cag_benchmark_public_rows()
    rights = _rights([row["caseId"] for row in rows])

    stale_gate = copy.deepcopy(rows)
    stale_gate[0]["gateReport"]["passed"] = False
    with pytest.raises(RuntimeError, match="huggingface_gate_receipt_invalid"):
        build_huggingface_publish_plan(
            rows=stale_gate, repo_id=REPO_ID, revision=REVISION, license_rights=rights
        )

    stale_passport = copy.deepcopy(rows)
    stale_passport[0]["passportSha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="huggingface_passport_binding_mismatch"):
        build_huggingface_publish_plan(
            rows=stale_passport, repo_id=REPO_ID, revision=REVISION, license_rights=rights
        )

    missing_source = copy.deepcopy(rows)
    missing_source[0]["sources"] = []
    with pytest.raises(RuntimeError, match="huggingface_source_provenance_missing"):
        build_huggingface_publish_plan(
            rows=missing_source, repo_id=REPO_ID, revision=REVISION, license_rights=rights
        )


def test_direct_main_is_forbidden_before_any_rights_or_transport_work():
    rows = build_cag_benchmark_public_rows()
    rights = _rights([row["caseId"] for row in rows])
    rights["authorizedRevision"] = "main"
    with pytest.raises(RuntimeError, match="huggingface_direct_main_publish_forbidden"):
        build_huggingface_publish_plan(rows=rows, repo_id=REPO_ID, revision="main", license_rights=rights)


def _install_fake_hub(monkeypatch, tmp_path, *, mode: str = "success", main_rows: list[dict] | None = None):
    main_sha = "a" * 40
    files: dict[str, dict[str, bytes]] = {"main": {}}
    if main_rows:
        files["main"]["data/casebook.jsonl"] = (
            "\n".join(canonical_json(row) for row in main_rows) + "\n"
        ).encode("utf-8")
    state = {
        "branch_shas": {"main": main_sha},
        "files": files,
        "commits": {main_sha: dict(files["main"])},
        "events": [],
        "write_attempts": 0,
        "branch_creates": 0,
    }

    def snapshot(revision: str) -> dict[str, bytes]:
        if revision in state["files"]:
            return state["files"][revision]
        if revision in state["commits"]:
            return state["commits"][revision]
        raise FileNotFoundError(revision)

    class CommitOperationAdd:
        def __init__(self, *, path_in_repo, path_or_fileobj):
            self.path_in_repo = path_in_repo
            self.path_or_fileobj = path_or_fileobj

    class HfApi:
        def repo_info(self, *, repo_id, repo_type, revision):
            if revision in state["branch_shas"]:
                return types.SimpleNamespace(sha=state["branch_shas"][revision])
            if revision in state["commits"]:
                return types.SimpleNamespace(sha=revision)
            raise RuntimeError("revision_missing")

        def list_repo_files(self, *, repo_id, repo_type, revision):
            return sorted(snapshot(revision))

        def create_branch(self, *, repo_id, repo_type, branch, exist_ok):
            state["branch_creates"] += 1
            if branch not in state["files"]:
                state["files"][branch] = dict(state["files"]["main"])
                state["branch_shas"][branch] = state["branch_shas"]["main"]

        def create_commit(self, *, repo_id, repo_type, revision, operations, commit_message):
            state["write_attempts"] += 1
            attempt = state["write_attempts"]
            state["events"].append(f"write:{attempt}")
            if mode == "outage":
                raise TimeoutError("simulated_hf_outage")
            target = dict(snapshot(revision))
            for operation in operations:
                value = operation.path_or_fileobj
                payload = value if isinstance(value, bytes) else bytes(value)
                if mode == "wrong_hash" and operation.path_in_repo.endswith(".jsonl"):
                    payload += b"corrupt"
                target[operation.path_in_repo] = payload
            oid = f"{attempt:040x}"
            state["files"][revision] = target
            state["branch_shas"][revision] = oid
            state["commits"][oid] = dict(target)
            if mode == "timeout_after_write":
                raise TimeoutError("simulated_timeout_after_accepted_write")
            return types.SimpleNamespace(oid=oid)

    def hf_hub_download(*, repo_id, filename, repo_type, revision):
        state["events"].append(f"read:{revision}:{filename}")
        content = snapshot(revision)[filename]
        local = tmp_path / f"{revision.replace('/', '_')}-{filename.replace('/', '_')}"
        local.write_bytes(content)
        return str(local)

    fake = types.ModuleType("huggingface_hub")
    fake.CommitOperationAdd = CommitOperationAdd
    fake.HfApi = HfApi
    fake.hf_hub_download = hf_hub_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)
    return state


def test_duplicate_target_content_is_idempotent_noop_without_hf_mutation(monkeypatch, tmp_path):
    rows = build_cag_benchmark_public_rows()
    rights = _rights([row["caseId"] for row in rows])
    state = _install_fake_hub(monkeypatch, tmp_path, main_rows=rows)
    result = publish_huggingface_batch(
        rows=rows, repo_id=REPO_ID, revision=REVISION, license_rights=rights
    )
    assert result["status"] == "DUPLICATE_NOOP"
    assert result["idempotent"] is True
    assert result["duplicateSemanticPublishSkipped"] is True
    assert result["readbackVerified"] is False
    assert state["write_attempts"] == 0
    assert state["branch_creates"] == 0


def test_timeout_after_accepted_write_is_recovered_by_readback_before_retry(monkeypatch, tmp_path):
    rows = build_cag_benchmark_public_rows()
    rights = _rights([row["caseId"] for row in rows])
    state = _install_fake_hub(monkeypatch, tmp_path, mode="timeout_after_write")
    result = publish_huggingface_batch(
        rows=rows, repo_id=REPO_ID, revision=REVISION, license_rights=rights
    )
    assert result["status"] == "PUBLISHED_VERIFIED"
    assert result["readbackVerified"] is True
    assert state["write_attempts"] == 1
    write_index = state["events"].index("write:1")
    assert any(event.startswith(f"read:{REVISION}:") for event in state["events"][write_index + 1:])


def test_api_success_with_wrong_target_hash_is_never_promoted(monkeypatch, tmp_path):
    rows = build_cag_benchmark_public_rows()
    rights = _rights([row["caseId"] for row in rows])
    state = _install_fake_hub(monkeypatch, tmp_path, mode="wrong_hash")
    with pytest.raises(RuntimeError, match="huggingface_publish_readback_mismatch"):
        publish_huggingface_batch(
            rows=rows, repo_id=REPO_ID, revision=REVISION, license_rights=rights
        )
    assert state["write_attempts"] == 1


def test_hf_outage_rechecks_target_before_retry_and_preserves_case_truth(monkeypatch, tmp_path):
    rows = build_cag_benchmark_public_rows()
    original = copy.deepcopy(rows)
    rights = _rights([row["caseId"] for row in rows])
    state = _install_fake_hub(monkeypatch, tmp_path, mode="outage")
    with pytest.raises(RuntimeError, match="huggingface_publish_write_failed_after_readback"):
        publish_huggingface_batch(
            rows=rows, repo_id=REPO_ID, revision=REVISION, license_rights=rights
        )
    assert state["write_attempts"] == 2
    first_write = state["events"].index("write:1")
    second_write = state["events"].index("write:2")
    assert any(event.startswith(f"read:{REVISION}:") for event in state["events"][first_write + 1:second_write])
    assert rows == original
    assert all(row["workflowState"] == "PUBLISHABLE" for row in rows)
