from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = REPO_ROOT / "docs/SOVEREIGN_ARCHITECTURE_MANIFEST.md"
CURRENT_BUNDLE = (
    REPO_ROOT
    / "docs/architecture/SOVEREIGN_MANIFEST_OPEN_ISSUES_2026-07-25.json"
)
WORKFLOW = REPO_ROOT / ".github/workflows/create-manifest-open-issues.yml"

CURRENT_REVISION = "5962c80e92cd96ef96eac72476b38cc0455f24fa"
CURRENT_BACKEND_DIGEST = (
    "sha256:de769dcd732b619f3ed4c76683513cb5060abcfe5fc75681b148da034c753f59"
)
CURRENT_MCP_REVISION = "09307359732ec0bbdb579747f494a7add2edee19"
OPEN_ISSUE_NUMBERS = {1013, 1014, 1016, 1017}
RESOLVED_KEYS = {
    "provider-onboarding-gpt54-route",
    "apply-owner-learning-policy-migration",
    "mirror-drift-llm-cost-policy",
    "mirror-drift-proven-learning-runtime",
    "github-app-route-registration",
    "remove-dead-legacy-admin-html",
}


def _manifest_section(text: str, start: str, end: str) -> str:
    assert start in text
    assert end in text
    return text.split(start, 1)[1].split(end, 1)[0]


def test_current_bundle_contains_only_real_open_issues() -> None:
    bundle = json.loads(CURRENT_BUNDLE.read_text("utf-8"))

    assert bundle["schemaVersion"] == "sovereign.manifest-open-issues.v1"
    assert bundle["auditBaseline"] == CURRENT_REVISION
    assert bundle["openIssueCount"] == len(bundle["issues"]) == 4
    assert {item["githubIssueNumber"] for item in bundle["issues"]} == OPEN_ISSUE_NUMBERS

    active_keys = {item["key"] for item in bundle["issues"]}
    assert active_keys.isdisjoint(RESOLVED_KEYS)
    assert RESOLVED_KEYS.issubset(set(bundle["resolvedKeys"]))


def test_bundle_binds_current_runtime_without_global_green_claim() -> None:
    bundle = json.loads(CURRENT_BUNDLE.read_text("utf-8"))
    runtime = bundle["runtimeEvidence"]
    routing = runtime["routing"]

    assert runtime["repositoryRevision"] == CURRENT_REVISION
    assert runtime["backendRevision"] == CURRENT_REVISION
    assert runtime["backendImageDigest"] == CURRENT_BACKEND_DIGEST
    assert runtime["mcpRevision"] == CURRENT_MCP_REVISION
    assert routing == {
        "paidTransport": "openrouter-direct",
        "paidDeploymentStatus": "ready",
        "paidCurrentStatus": "catalog_refresh_required",
        "paidSelectableModels": 0,
        "freeTransport": "freellm-direct",
        "freeReadyRoutes": 5,
        "freeCurrentStatus": "degraded",
        "liteLlmActiveTransport": False,
    }


def test_manifest_current_sections_match_repository_and_runtime_readback() -> None:
    text = MANIFEST.read_text("utf-8")
    active_open_points = _manifest_section(text, "## 24.2 Offen, teilweise oder blockiert", "## 24.3 Langfristig")
    current_snapshot = _manifest_section(text, "## 26.1 Aktueller Readback vom 25. Juli 2026", "## 26.2 Historische Provenance")

    assert CURRENT_REVISION in text
    assert CURRENT_BACKEND_DIGEST in text
    assert CURRENT_MCP_REVISION in text
    assert "SOVEREIGN_MANIFEST_OPEN_ISSUES_2026-07-25.json" in text

    for issue_number in OPEN_ISSUE_NUMBERS:
        assert f"#{issue_number}" in active_open_points
    assert "acht Punkte" not in active_open_points
    assert "Migration `028` und Standing-Owner-Policy" not in active_open_points
    assert "Mirror-Drift der LLM-Kostenpolicy" not in active_open_points
    assert "GitHub-App-Routenregistrierung" not in active_open_points

    assert "Ledger `028=1`" in current_snapshot
    assert "Ledger `041=1`" in current_snapshot
    assert "mismatchCount=0" in current_snapshot
    assert "173 Endpoints" in current_snapshot
    assert "catalog_refresh_required" in current_snapshot
    assert "fünf Ready-Routen" in current_snapshot
    assert "LiteLLM ist nicht aktiv" in current_snapshot
    assert "Kein Gesamtgrün wird behauptet" in current_snapshot


def test_issue_workflow_reuses_bound_open_issues_and_never_reopens() -> None:
    workflow = WORKFLOW.read_text("utf-8")

    assert "SOVEREIGN_MANIFEST_OPEN_ISSUES_2026-07-25.json" in workflow
    assert "item.githubIssueNumber" in workflow
    assert "boundIssue.state !== 'open'" in workflow
    assert "automatic reopen is forbidden" in workflow
    assert "title mismatch" in workflow
