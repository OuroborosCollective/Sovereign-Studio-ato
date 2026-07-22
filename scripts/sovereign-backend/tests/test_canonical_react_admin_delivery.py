from __future__ import annotations

from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parents[1]


def test_backend_serves_only_revision_bound_react_admin() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    dockerfile = (BACKEND / "Dockerfile").read_text("utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "sovereign-backend-image.yml").read_text("utf-8")
    wrapper = (REPO_ROOT / "src" / "SovereignAppWrapper.tsx").read_text("utf-8")

    assert "from enterprise_admin_ui import ENTERPRISE_ADMIN_HTML" not in app
    assert "make_response(ENTERPRISE_ADMIN_HTML)" not in app
    assert 'redirect("/admin/", code=308)' in app
    assert 'send_from_directory(ADMIN_DIST_DIR, "index.html")' in app
    assert '"X-Sovereign-Admin-Producer"] = "CANONICAL_REACT_ADMIN"' in app
    assert 'os.getenv("SOVEREIGN_SOURCE_REVISION", "unverified")' in app
    assert 'except NotFound:' in app
    assert 'components["adminUi"]' in app
    assert 'and components["adminUi"].get("ok")' in app
    assert "COPY admin-dist/ ./admin-dist/" in dockerfile
    assert "Build revision-bound React admin" in workflow
    assert "Stage canonical admin artifact for backend image" in workflow
    assert "VITE_SOVEREIGN_SOURCE_REVISION: ${{ github.sha }}" in workflow
    assert "corepack prepare pnpm@9.12.2 --activate" in workflow
    assert "cache: pnpm" not in workflow
    assert "CANONICAL_REACT_ADMIN" in wrapper
    assert 'data-sovereign-free-revolver="enabled"' in wrapper


def test_android_admin_recovery_never_overwrites_a_mounted_shell_and_remains_scrollable() -> None:
    fallback = (REPO_ROOT / "scripts" / "release-html-runtime-fix.mjs").read_text("utf-8")
    admin_css = (REPO_ROOT / "src" / "features" / "admin" / "AdminPanel.css").read_text("utf-8")

    assert '[data-sovereign-admin-producer]' in fallback
    assert ".admin-shell,.admin-auth-shell" in fallback
    assert "if(!root||hasMountedShell())return;" in fallback
    assert "setTimeout(function(){bootFallback(lastBootError||'startup timeout')},15000)" in fallback
    assert "startup timeout')},2200" not in fallback
    assert "window.addEventListener('error',function(event)" in fallback
    assert "bootFallback('runtime error')" not in fallback

    assert '[data-sovereign-admin-producer="CANONICAL_REACT_ADMIN"]' in admin_css
    assert "height: 100dvh;" in admin_css
    assert "min-height: 100dvh;" in admin_css
    assert "overflow-y: auto;" in admin_css
    assert "touch-action: pan-y;" in admin_css
    assert "-webkit-overflow-scrolling: touch;" in admin_css


def test_pr_image_is_loaded_without_release_attestations_for_runtime_inspection() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "sovereign-backend-image.yml").read_text("utf-8")

    assert "load: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "provenance: ${{ github.event_name == 'pull_request' && 'false' || 'mode=max' }}" in workflow
    assert "sbom: ${{ github.event_name != 'pull_request' }}" in workflow
    assert "Verify canonical admin inside PR image" in workflow
