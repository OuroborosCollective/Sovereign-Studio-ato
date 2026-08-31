import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sovereign-legacy-mcp-common"))
sys.path.insert(0, str(ROOT / "sovereign-toolchain" / "src"))

from sovereign_toolchain.ci_evidence import (
    CIEvidenceError,
    build_ci_evidence_receipt,
    build_revision_guardian_receipt,
)
from sovereign_toolchain.core import dispatch_tool


HEAD = "a" * 40
OTHER_HEAD = "b" * 40


def observation(*, head_sha: str = HEAD, status: str = "completed", conclusion: str | None = "failure") -> dict:
    return {
        "repository": "OuroborosCollective/Sovereign-Studio-ato",
        "run_id": 33430350888,
        "head_sha": head_sha,
        "expected_head_sha": HEAD,
        "status": status,
        "conclusion": conclusion,
        "jobs": [
            {
                "id": 20,
                "name": "release",
                "status": "completed",
                "conclusion": "skipped",
                "steps": [],
            },
            {
                "id": 10,
                "name": "backend",
                "status": "completed",
                "conclusion": "failure",
                "steps": [
                    {"number": 2, "name": "Tests", "status": "completed", "conclusion": "failure"},
                    {"number": 1, "name": "Checkout", "status": "completed", "conclusion": "success"},
                ],
            },
        ],
    }


def test_receipt_is_deterministic_and_normalizes_job_and_step_order() -> None:
    first = observation()
    second = observation()
    second["jobs"] = list(reversed(second["jobs"]))
    second["jobs"][1]["steps"] = list(reversed(second["jobs"][1]["steps"]))

    receipt_a = build_ci_evidence_receipt(first)
    receipt_b = build_ci_evidence_receipt(second)

    assert receipt_a == receipt_b
    assert receipt_a["authority"] == "OBSERVATION_ONLY"
    assert receipt_a["requiresIndependentReadback"] is True
    assert receipt_a["firstFailure"] == {
        "jobId": 10,
        "jobName": "backend",
        "stepNumber": 2,
        "stepName": "Tests",
        "conclusion": "failure",
    }
    assert receipt_a["verdict"] == "COMPLETED_NON_SUCCESS"
    assert receipt_a["shouldNotify"] is True


def test_previous_fingerprint_suppresses_duplicate_delivery_not_truth() -> None:
    receipt = build_ci_evidence_receipt(observation())
    repeated = observation()
    repeated["previous_fingerprint"] = receipt["stateFingerprint"]

    duplicate = build_ci_evidence_receipt(repeated)

    assert duplicate["stateChanged"] is False
    assert duplicate["shouldNotify"] is False
    assert duplicate["verdict"] == "COMPLETED_NON_SUCCESS"
    assert duplicate["requiresIndependentReadback"] is True


def test_revision_drift_notifies_even_while_workflow_is_running() -> None:
    running = observation(head_sha=OTHER_HEAD, status="in_progress", conclusion=None)
    running["jobs"] = [
        {
            "id": 1,
            "name": "backend",
            "status": "in_progress",
            "conclusion": None,
            "steps": [{"number": 1, "name": "Build", "status": "in_progress", "conclusion": None}],
        }
    ]

    receipt = build_ci_evidence_receipt(running)

    assert receipt["revisionMatches"] is False
    assert receipt["verdict"] == "REVISION_DRIFT"
    assert receipt["shouldNotify"] is True


def test_completed_success_is_observed_but_still_not_verified_runtime_truth() -> None:
    success = observation(status="completed", conclusion="success")
    success["jobs"] = [
        {
            "id": 1,
            "name": "backend",
            "status": "completed",
            "conclusion": "success",
            "steps": [{"number": 1, "name": "Tests", "status": "completed", "conclusion": "success"}],
        }
    ]

    receipt = build_ci_evidence_receipt(success)

    assert receipt["verdict"] == "SUCCESS"
    assert receipt["requiresIndependentReadback"] is True
    assert "VERIFIED" not in receipt.values()


def test_toolchain_dispatch_exposes_read_only_ci_receipt() -> None:
    response = dispatch_tool("sovereign_ci_evidence_receipt", observation())

    assert response["ok"] is True
    assert response["tool"] == "sovereign_ci_evidence_receipt"
    assert response["result"]["receiptSha256"]


def test_secret_shaped_job_name_is_rejected() -> None:
    unsafe = observation()
    unsafe["jobs"][0]["name"] = "Bearer " + ("x" * 12)

    with pytest.raises(CIEvidenceError, match="secret-shaped"):
        build_ci_evidence_receipt(unsafe)


def test_revision_guardian_requires_all_bound_identities_to_match() -> None:
    image = "sha256:" + ("c" * 64)
    receipt = build_revision_guardian_receipt(
        {
            "repository": "OuroborosCollective/Sovereign-Studio-ato",
            "expected_revision": HEAD,
            "git_revision": HEAD,
            "build_revision": HEAD,
            "deploy_revision": HEAD,
            "health_revision": HEAD,
            "expected_image_digest": image,
            "image_digest": image,
            "health_status": "ok",
            "schema_readback": "PRESENT_SCHEMA_MATCH",
        }
    )

    assert receipt["verdict"] == "PASS"
    assert receipt["drift"] == []
    assert receipt["requiresIndependentReadback"] is True


def test_revision_guardian_reports_causal_drift_dimensions() -> None:
    expected_image = "sha256:" + ("c" * 64)
    observed_image = "sha256:" + ("d" * 64)
    receipt = build_revision_guardian_receipt(
        {
            "repository": "OuroborosCollective/Sovereign-Studio-ato",
            "expected_revision": HEAD,
            "git_revision": HEAD,
            "build_revision": OTHER_HEAD,
            "deploy_revision": HEAD,
            "health_revision": OTHER_HEAD,
            "expected_image_digest": expected_image,
            "image_digest": observed_image,
            "health_status": "degraded",
            "schema_readback": "RECONCILIATION_REQUIRED",
        }
    )

    assert receipt["verdict"] == "DRIFT"
    assert receipt["drift"] == [
        "BUILD_REVISION_DRIFT",
        "HEALTH_REVISION_DRIFT",
        "IMAGE_DIGEST_DRIFT",
        "HEALTH_NOT_OK",
        "SCHEMA_NOT_MATCHED",
    ]
    assert receipt["shouldNotify"] is True


def test_n8n_adapter_is_disabled_read_only_and_has_no_hardcoded_credentials() -> None:
    path = ROOT / "sovereign-toolchain" / "adapters" / "sovereign-ci-evidence-watch.n8n.json"
    workflow = json.loads(path.read_text("utf-8"))
    rendered = json.dumps(workflow, sort_keys=True)
    node_types = {node["type"] for node in workflow["nodes"]}

    assert workflow["active"] is False
    assert "n8n-nodes-base.scheduleTrigger" in node_types
    assert "n8n-nodes-base.httpRequest" in node_types
    assert "sovereign_ci_evidence_receipt" in rendered
    assert "SOVEREIGN_TOOLCHAIN_API_KEY" in rendered
    assert "workflow_dispatch" not in rendered
    assert "merge" not in rendered.lower()
    assert "confirm=true" not in rendered.lower()
    assert "ghp_" not in rendered
    assert "github_pat_" not in rendered
