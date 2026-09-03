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
from sovereign_toolchain.core import TOOL_DEFINITIONS, dispatch_tool


HEAD = "a" * 40
OTHER_HEAD = "b" * 40


def observation(*, head_sha: str = HEAD, status: str = "completed", conclusion: str | None = "failure") -> dict:
    return {
        "repository": "OuroborosCollective/Sovereign-Studio-ato",
        "workflow_id": 123456,
        "workflow_name": "Sovereign Coordinated Release Gate",
        "workflow_selector": "sovereign-coordinated-release.yml",
        "branch": "main",
        "branch_head_sha": HEAD,
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
    assert receipt_a["deliveryCursorPresent"] is False
    assert receipt_a["stateChanged"] is False
    assert receipt_a["shouldNotify"] is False


def test_previous_fingerprint_suppresses_duplicate_delivery_not_truth() -> None:
    receipt = build_ci_evidence_receipt(observation())
    repeated = observation()
    repeated["previous_fingerprint"] = receipt["stateFingerprint"]

    duplicate = build_ci_evidence_receipt(repeated)

    assert duplicate["deliveryCursorPresent"] is True
    assert duplicate["stateChanged"] is False
    assert duplicate["shouldNotify"] is False
    assert duplicate["verdict"] == "COMPLETED_NON_SUCCESS"
    assert duplicate["requiresIndependentReadback"] is True


def test_revision_drift_notifies_even_while_workflow_is_running() -> None:
    running = observation(head_sha=OTHER_HEAD, status="in_progress", conclusion=None)
    running["previous_fingerprint"] = "c" * 64
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
    assert receipt["deliveryCursorPresent"] is True
    assert receipt["stateChanged"] is True
    assert receipt["shouldNotify"] is True


def test_running_change_with_cursor_does_not_notify_without_revision_drift() -> None:
    running = observation(status="in_progress", conclusion=None)
    running["previous_fingerprint"] = "d" * 64
    running["jobs"] = [
        {
            "id": 1,
            "name": "backend",
            "status": "in_progress",
            "conclusion": None,
            "steps": [
                {
                    "number": 1,
                    "name": "Build",
                    "status": "in_progress",
                    "conclusion": None,
                }
            ],
        }
    ]

    receipt = build_ci_evidence_receipt(running)

    assert receipt["revisionMatches"] is True
    assert receipt["deliveryCursorPresent"] is True
    assert receipt["stateChanged"] is True
    assert receipt["shouldNotify"] is False


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


def test_public_ci_evidence_manifest_schema_matches_runtime_contract() -> None:
    tool = next(
        definition
        for definition in TOOL_DEFINITIONS
        if definition["name"] == "sovereign_ci_evidence_receipt"
    )
    schema = tool["input_schema"]
    required = {
        "repository",
        "workflow_id",
        "workflow_name",
        "workflow_selector",
        "branch",
        "branch_head_sha",
        "run_id",
        "head_sha",
        "status",
        "jobs",
    }

    assert set(schema["required"]) == required
    assert required <= set(schema["properties"])


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
    assert receipt["deliveryCursorPresent"] is False
    assert receipt["stateChanged"] is False
    assert receipt["shouldNotify"] is False
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
            "previous_fingerprint": "e" * 64,
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


def test_workflow_identity_is_part_of_the_delivery_fingerprint() -> None:
    first = observation()
    second = observation()
    second["workflow_id"] = 654321
    second["workflow_name"] = "Another Workflow"
    second["workflow_selector"] = "another.yml"

    assert build_ci_evidence_receipt(first)["stateFingerprint"] != build_ci_evidence_receipt(second)["stateFingerprint"]


@pytest.mark.parametrize(
    (
        "filename",
        "repository",
        "workflow_selector",
        "workflow_file",
        "credential_name",
        "credential_id",
    ),
    [
        (
            "sovereign-ci-evidence-watch.n8n.json",
            "OuroborosCollective/Sovereign-Studio-ato",
            "sovereign-coordinated-release.yml",
            "sovereign-coordinated-release.yml",
            "Sovereign Toolchain Evidence",
            "__SOVEREIGN_TOOLCHAIN_EVIDENCE_CREDENTIAL_ID__",
        ),
        (
            "aurion-ci-evidence-watch.n8n.json",
            "OuroborosCollective/Echoes_of_Aurion",
            "340269357",
            "deploy-aurion-zone-runtime.yml",
            "Aurion Toolchain Evidence",
            "__AURION_TOOLCHAIN_EVIDENCE_CREDENTIAL_ID__",
        ),
    ],
)
def test_n8n_adapters_are_disabled_narrow_and_credential_bound(
    filename: str,
    repository: str,
    workflow_selector: str,
    workflow_file: str,
    credential_name: str,
    credential_id: str,
) -> None:
    path = ROOT / "sovereign-toolchain" / "adapters" / filename
    workflow = json.loads(path.read_text("utf-8"))
    rendered = json.dumps(workflow, sort_keys=True)
    node_types = {node["type"] for node in workflow["nodes"]}

    assert workflow["active"] is False
    assert node_types == {
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.httpRequest",
    }
    schedule_nodes = [
        node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.scheduleTrigger"
    ]
    assert len(schedule_nodes) == 1
    assert schedule_nodes[0]["name"] == "Evidence Schedule"
    assert schedule_nodes[0]["parameters"]["rule"]["interval"] == [
        {"field": "minutes", "minutesInterval": 15}
    ]
    assert "Evidence Schedule" in workflow["connections"]

    http_nodes = [
        node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.httpRequest"
    ]
    assert len(http_nodes) == 1
    http_node = http_nodes[0]
    direct_body = json.loads(http_node["parameters"]["jsonBody"])
    assert "args" not in direct_body
    assert f'{direct_body["owner"]}/{direct_body["repo"]}' == repository
    assert direct_body["branch"] == "main"
    assert direct_body["previous_fingerprint"] is None
    assert str(direct_body["workflow_id"]) == workflow_selector
    assert http_node["parameters"]["url"] == (
        "http://host.docker.internal:8002/api/v1/n8n/ci-evidence"
    )
    assert http_node["credentials"]["httpHeaderAuth"] == {
        "id": credential_id,
        "name": credential_name,
    }

    assert workflow_selector in rendered
    assert workflow_file in rendered
    assert "http://host.docker.internal:8001/v1/n8n/" not in rendered
    assert "$env" not in rendered
    assert "api.github.com" not in rendered
    assert "/api/v1/tools/" not in rendered
    assert "X-Toolchain-Key" not in rendered
    assert "workflow_dispatch" not in rendered
    assert "merge" not in rendered.lower()
    assert "confirm=true" not in rendered.lower()
    assert "ghp_" not in rendered
    assert "github_pat_" not in rendered
