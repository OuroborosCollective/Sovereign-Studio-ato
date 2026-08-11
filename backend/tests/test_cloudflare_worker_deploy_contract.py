from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "cloudflare-worker-ai-proxy"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-worker.yml"
FRONTEND_CONFIG = ROOT / "src" / "features" / "product" / "llm" / "primaryBridgeConfig.ts"


def test_retired_worker_toolchain_remains_pinned_for_a_safe_tombstone() -> None:
    package = json.loads((WORKER / "package.json").read_text(encoding="utf-8"))
    dependencies = package["devDependencies"]

    assert package["version"] == "1.2.0"
    assert dependencies["wrangler"] == "4.110.0"
    assert dependencies["@cloudflare/workers-types"] == "5.20260712.1"
    assert package["scripts"]["typecheck"] == "tsc --noEmit"


def test_worker_workflow_is_a_read_only_tombstone() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "Legacy Cloudflare Worker AI Proxy Disabled" in workflow
    assert "workflow_dispatch:" in workflow
    assert "App -> Sovereign Backend -> direct OpenRouter Paid or direct FreeLLM Free" in workflow
    assert "wrangler" not in workflow
    assert "workers.dev" not in workflow
    assert "CF_AI_TOKEN" not in workflow
    assert "CLOUDFLARE_API_TOKEN" not in workflow


def test_worker_handler_and_package_are_fail_closed() -> None:
    worker_source = (WORKER / "src" / "index.ts").read_text(encoding="utf-8")
    package = json.loads((WORKER / "package.json").read_text(encoding="utf-8"))
    frontend_config = FRONTEND_CONFIG.read_text(encoding="utf-8")

    assert "const LEGACY_WORKER_RETIRED = true" in worker_source
    assert "status: 410" in worker_source
    assert worker_source.index("LEGACY_WORKER_RETIRED") < worker_source.index("const url = new URL")
    assert package["scripts"]["deploy"] != "wrangler deploy"
    assert "workers.dev" not in frontend_config


def test_retired_worker_cannot_reactivate_an_embedding_runtime() -> None:
    worker_source = (WORKER / "src" / "index.ts").read_text(encoding="utf-8")
    readme = (WORKER / "README.md").read_text(encoding="utf-8")
    secrets_script = (WORKER / "scripts" / "setup-secrets.sh").read_text(encoding="utf-8")

    assert "legacy_cloudflare_worker_retired" in worker_source
    assert "Cache-Control': 'no-store'" in worker_source
    assert "must not be deployed" in readme
    assert "wrangler" not in secrets_script
