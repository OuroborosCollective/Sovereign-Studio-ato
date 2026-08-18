"""Cross-surface contracts for Worker embeddings and GitHub OAuth return flow.

These checks prevent repository truth from drifting away from deployment and UI
truth. They inspect the canonical deployed backend, mirrored support modules,
the Worker deployment workflow, and the browser callback transport.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_worker_exposes_versioned_768_embedding_route():
    source = read("cloudflare-worker-ai-proxy/src/index.ts")

    assert "url.pathname === '/v1/embeddings'" in source
    assert "const EMBEDDING_DIMENSIONS = 768" in source
    assert "version: '1.2.0'" in source
    assert "embeddingPath: '/v1/embeddings'" in source
    assert "handleEmbeddings(request, env)" in source


def test_worker_deploy_is_permanently_disabled_and_secret_free():
    # Contract drift (production truth): the legacy Cloudflare Worker AI proxy
    # deployment is permanently disabled; embeddings moved to the private
    # FreeLLMAPI Docker runtime. The security contract inverts: the workflow
    # must NOT deploy anything and must NOT reference Cloudflare AI secrets.
    workflow = read(".github/workflows/deploy-worker.yml")

    assert "Legacy Cloudflare Worker AI Proxy Disabled" in workflow
    assert "permanently disabled" in workflow
    assert "workflow_dispatch" in workflow
    for forbidden in (
        "wrangler deploy",
        "CF_AI_TOKEN",
        "CF_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "secrets.",
    ):
        assert forbidden not in workflow, forbidden


def test_backend_mirrors_fail_closed_on_non_private_embedding_route():
    # Contract drift (production truth): the mirrors no longer report worker
    # version drift; they fail closed unless the private FreeLLMAPI Docker
    # endpoint is used and never fall back to the retired Worker path.
    for path in (
        "backend/vector_embedding.py",
        "scripts/sovereign-backend/vector_embedding.py",
    ):
        source = read(path)
        assert "Embeddings require the private FreeLLMAPI Docker endpoint" in source
        assert "retired Cloudflare Worker path" in source
        assert "DEFAULT_FREELLMAPI_BASE_URL" in source
        assert 'provider="freellmapi-private"' in source


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
