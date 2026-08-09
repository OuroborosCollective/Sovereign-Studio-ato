from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-primary-llm-bridge.yml"
WORKER_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-worker.yml"
WORKER_SOURCE = ROOT / "cloudflare-worker-ai-proxy" / "src" / "index.ts"
WORKER_PACKAGE = ROOT / "cloudflare-worker-ai-proxy" / "package.json"
WORKER_README = ROOT / "cloudflare-worker-ai-proxy" / "README.md"
WORKER_SECRETS = ROOT / "cloudflare-worker-ai-proxy" / "scripts" / "setup-secrets.sh"
WORKER_TEST = ROOT / "cloudflare-worker-ai-proxy" / "scripts" / "test-proxy.sh"


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


def test_legacy_cloudflare_worker_package_is_fail_closed() -> None:
    source = WORKER_SOURCE.read_text("utf-8")
    package = WORKER_PACKAGE.read_text("utf-8")
    readme = WORKER_README.read_text("utf-8")

    assert "const LEGACY_WORKER_RETIRED = true" in source
    assert "status: 410" in source
    assert source.index("LEGACY_WORKER_RETIRED") < source.index("const url = new URL")
    assert '"deploy": "wrangler deploy"' not in package
    assert "Cloudflare Worker AI proxy is retired" in readme
    assert "npm run deploy" not in readme
    assert "workers.dev" not in readme
    assert "wrangler" not in WORKER_SECRETS.read_text("utf-8")
    assert "workers.dev" not in WORKER_TEST.read_text("utf-8")
