from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "cloudflare-worker-ai-proxy"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-worker.yml"
BACKEND_EMBEDDING = ROOT / "backend" / "vector_embedding.py"
FRONTEND_BRIDGE = ROOT / "src" / "features" / "product" / "runtime" / "devChatWorkerBridge.ts"


def test_worker_toolchain_versions_are_exact_and_peer_compatible() -> None:
    package = json.loads((WORKER / "package.json").read_text(encoding="utf-8"))
    dependencies = package["devDependencies"]

    assert package["version"] == "1.2.0"
    assert dependencies["wrangler"] == "4.110.0"
    assert dependencies["@cloudflare/workers-types"] == "5.20260712.1"
    assert package["scripts"]["typecheck"] == "tsc --noEmit"


def test_worker_workflow_does_not_float_wrangler_or_bypass_peer_resolution() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "wrangler@4\n" not in workflow
    assert "--legacy-peer-deps" not in workflow
    assert "--force" not in workflow
    assert "npm install --no-audit --no-fund" in workflow
    assert "*4.110.0*)" in workflow
    assert "npm run typecheck" in workflow


def test_worker_secrets_are_used_without_being_embedded_in_frontend() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    worker_source = (WORKER / "src" / "index.ts").read_text(encoding="utf-8")
    backend_embedding = BACKEND_EMBEDDING.read_text(encoding="utf-8")
    frontend_bridge = FRONTEND_BRIDGE.read_text(encoding="utf-8")

    for name in (
        "CF_AI_TOKEN",
        "CF_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
    ):
        assert name in workflow

    assert "secret put CF_AI_TOKEN" in workflow
    assert "secret put CF_ACCOUNT_ID" in workflow
    assert 'env.CF_AI_TOKEN' in worker_source
    assert 'env.CF_ACCOUNT_ID' in worker_source

    assert 'os.getenv("WORKER_AI_PROXY_KEY"' in backend_embedding
    assert 'headers["Authorization"] = f"Bearer {proxy_key}"' in backend_embedding

    # The current Android/WebView direct bridge intentionally sends no shared
    # system secret. PROXY_API_KEY therefore remains optional until chat traffic
    # is moved behind the authenticated backend.
    assert "Authorization" not in frontend_bridge
    assert 'if [[ -n "${PROXY_API_KEY:-}" ]]' in workflow


def test_worker_cors_and_embedding_runtime_contract_remain_explicit() -> None:
    worker_source = (WORKER / "src" / "index.ts").read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "'Access-Control-Allow-Origin': '*'" in worker_source
    assert "'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'" in worker_source
    assert "Content-Type, Authorization, X-API-Key, X-Sovereign-Client" in worker_source
    assert "url.pathname === '/v1/embeddings'" in worker_source
    assert "embeddingDimensions: EMBEDDING_DIMENSIONS" in worker_source
    assert "embeddingPath: '/v1/embeddings'" in worker_source

    assert "EXPECTED_WORKER_VERSION: '1.2.0'" in workflow
    assert "payload.providers?.embeddings !== true" in workflow
    assert "payload.embeddingDimensions !== 768" in workflow
    assert "payload.embeddingPath !== '/v1/embeddings'" in workflow
    assert "vector.length !== 768" in workflow
