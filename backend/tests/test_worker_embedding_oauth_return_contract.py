"""Cross-surface contracts for the retired Worker and GitHub OAuth return flow.

These checks prevent repository truth from drifting away from deployment and UI
truth. They inspect the canonical deployed backend, mirrored support modules,
the Worker deployment workflow, and the browser callback transport.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_legacy_worker_is_fail_closed_before_any_historical_route_handling():
    source = read("cloudflare-worker-ai-proxy/src/index.ts")

    assert "const LEGACY_WORKER_RETIRED = true" in source
    assert "legacy_cloudflare_worker_retired" in source
    assert "status: 410" in source
    assert source.index("LEGACY_WORKER_RETIRED") < source.index("const url = new URL")


def test_worker_deploy_is_explicitly_disabled():
    workflow = read(".github/workflows/deploy-worker.yml")

    for secret in (
        "CF_AI_TOKEN",
        "CF_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
    ):
        assert secret not in workflow
    worker_package = read("cloudflare-worker-ai-proxy/package.json")
    assert '"wrangler": "4.110.0"' in worker_package
    assert '"deploy": "wrangler deploy"' not in worker_package
    assert "Legacy Cloudflare Worker AI Proxy Disabled" in workflow
    assert "wrangler" not in workflow
    assert "workers.dev" not in workflow


def test_deployment_embedding_adapter_has_no_cloudflare_runtime_fallback():
    source = read("scripts/sovereign-backend/vector_embedding.py")

    assert "DEFAULT_WORKER_AI_PROXY_URL" not in source
    assert "CLOUDFLARE_ACCOUNT_ID" not in source
    assert "CLOUDFLARE_API_TOKEN" not in source
    assert "WORKER_AI_PROXY_URL" not in source
    assert "http://freellmapi:3001/v1" in source


def test_oauth_callback_uses_state_bound_opener_origin():
    frontend = read("src/features/github/githubOAuthLogin.ts")
    callback = read("public/auth/github/callback.html")

    assert "opener_origin: openerOrigin" in frontend
    assert "event.origin !== initialized.callbackOrigin" in frontend
    assert "event.source !== popup" in frontend
    assert "/api/auth/github/callback-context?state=" in callback
    assert "postMessage(message, context.openerOrigin)" in callback
    assert "postMessage(message, '*')" not in callback


def test_canonical_backend_validates_and_preserves_oauth_return_contract():
    for path in ("scripts/sovereign-backend/app.py",):
        source = read(path)
        assert "def auth_github_callback_context" in source
        assert "_peek_oauth_state(state)" in source
        assert '"opener_origin": opener_origin' in source
        assert '"callbackOrigin": _github_oauth_callback_origin()' in source
        assert "github_oauth_opener_origin_not_allowed" in source
        assert "INSERT INTO github_oauth_states" in source
        assert "DELETE FROM github_oauth_states" in source
        assert "RETURNING payload" in source
        assert "hashlib.sha256(normalized.encode()).hexdigest()" in source

    migration = read("scripts/sovereign-backend/migrations/013_github_oauth_state_runtime.sql")
    assert "CREATE TABLE IF NOT EXISTS github_oauth_states" in migration
    assert "CHECK (state_hash ~ '^[0-9a-f]{64}$')" in migration
    assert "idx_github_oauth_states_expires_at" in migration

    for path in ("backend/security_oauth.py", "scripts/sovereign-backend/security_oauth.py"):
        source = read(path)
        assert "def _peek_oauth_state" in source
        assert '"_peek_oauth_state"' in source
