from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-primary-llm-bridge.yml"
WORKER_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-worker.yml"


def test_legacy_primary_bridge_is_a_read_only_tombstone() -> None:
    source = WORKFLOW.read_text("utf-8")
    assert "Legacy Primary LLM Bridge Disabled" in source
    assert "permissions:\n  contents: read" in source
    assert "App -> Sovereign Backend -> direct OpenRouter Paid or direct FreeLLM Free" in source
    assert "wrangler" not in source
    assert "workers.dev" not in source
    assert "VITE_SOVEREIGN_LLM_PROXY_URL" not in source
    assert "CLOUDFLARE_API_TOKEN" not in source
    assert "actions: write" not in source


def test_legacy_cloudflare_worker_workflow_is_a_read_only_tombstone() -> None:
    source = WORKER_WORKFLOW.read_text("utf-8")
    assert "Legacy Cloudflare Worker AI Proxy Disabled" in source
    assert "workflow_dispatch:" in source
    assert "App -> Sovereign Backend -> direct OpenRouter Paid or direct FreeLLM Free" in source
    assert "wrangler" not in source
    assert "workers.dev" not in source
    assert "CLOUDFLARE_API_TOKEN" not in source
    assert "CF_AI_TOKEN" not in source
