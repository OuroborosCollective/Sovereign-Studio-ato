from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "sovereign-openrouter-activation.yml"
RUNTIME = ROOT / "scripts" / "sovereign-backend" / "openrouter_provider_runtime.py"


def test_openrouter_activation_workflow_is_exact_revision_and_secret_free() -> None:
    workflow = WORKFLOW.read_text("utf-8")

    assert "workflow_dispatch:" in workflow
    assert "confirm_bounded_provider_canary:" in workflow
    assert "expected_backend_revision:" in workflow
    assert "expected_backend_image_digest:" in workflow
    assert "expected_mcp_revision:" in workflow
    assert "expected_mcp_image_digest:" in workflow
    assert "test \"${GITHUB_REF}\" = 'refs/heads/main'" in workflow
    assert "ghcr.io/ouroboroscollective/sovereign-backend@${EXPECTED_BACKEND_IMAGE_DIGEST}" in workflow
    assert "ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp@${EXPECTED_MCP_IMAGE_DIGEST}" in workflow
    assert "server.provider_runtime.openrouter_activate(route_id)" in workflow
    assert "server.provider_runtime.openrouter_status()" in workflow
    assert "openrouter-paid-gpt-5-4-mini" in workflow
    assert "selectableModels" in workflow
    assert "secret_argument_accepted" in workflow
    assert "rawResponsePersisted" in workflow
    assert "git push --force" not in workflow
    assert "curl " not in workflow
    assert "openrouter_api_key" not in workflow.casefold()
    assert "authorization: bearer" not in workflow.casefold()


def test_openrouter_status_fails_honestly_when_catalog_is_not_selectable() -> None:
    runtime = RUNTIME.read_text("utf-8")

    assert 'effective_status = "catalog_refresh_required"' in runtime
    assert 'blocker = blocker or "openrouter_catalog_refresh_required"' in runtime
    assert '"deploymentStatus": deployment_status' in runtime
    assert "upstream_model_id=%s" in runtime
