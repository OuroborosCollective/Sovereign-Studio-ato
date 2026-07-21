from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text("utf-8")


def test_flask_admin_is_react_only_and_fails_closed():
    app = read("scripts/sovereign-backend/app.py")
    assert "from enterprise_admin_ui import" not in app
    assert "ENTERPRISE_ADMIN_HTML" not in app
    assert 'ADMIN_UI_PRODUCER = "react-admin-dist"' in app
    assert '"react_admin_artifact_missing"' in app
    assert 'X-Sovereign-Admin-Producer' in app
    assert 'X-Sovereign-Source-Revision' in app
    assert '@app.route("/admin/<path:asset_path>")' in app
    assert 'redirect("/admin/", code=308)' in app


def test_backend_image_contains_the_canonical_react_artifact():
    dockerfile = read("scripts/sovereign-backend/Dockerfile")
    assert "FROM node:22-bookworm-slim AS admin-web" in dockerfile
    assert "pnpm run build:web" in dockerfile
    assert "COPY --from=admin-web /workspace/dist /app/admin-dist" in dockerfile
    assert "test -f /app/admin-dist/index.html" in dockerfile
    assert "rm -f /app/enterprise_admin_ui.py" in dockerfile
    assert "SOVEREIGN_ADMIN_DIST_ROOT=/app/admin-dist" in dockerfile


def test_react_entry_selects_admin_and_uses_same_origin_api():
    main = read("src/main.tsx")
    panel = read("src/features/admin/AdminPanel.tsx")
    client = read("src/features/admin/api/adminApiClient.ts")
    index = read("index.html")
    assert "/^\\/admin(?:\\/|$)/" in main
    assert "<AdminPanel />" in main
    assert 'data-testid="sovereign-react-admin-root"' in panel
    assert 'data-admin-producer="react-admin-dist"' in panel
    assert "sovereign-backend.arelorian.de" not in client
    assert "VITE_ADMIN_API_BASE" in client
    assert 'data-sovereign-bundle="react-admin-dist"' in index


def test_image_workflow_builds_from_repository_root_and_smokes_exact_image():
    workflow = read(".github/workflows/sovereign-backend-image.yml")
    assert "context: ." in workflow
    assert "file: scripts/sovereign-backend/Dockerfile" in workflow
    assert "SOVEREIGN_SOURCE_REVISION=${{ github.sha }}" in workflow
    assert "Verify React admin inside exact immutable image" in workflow
    assert "X-Sovereign-Admin-Producer: react-admin-dist" in workflow
    assert "adminArtifactReady" in workflow


def test_live_production_dom_gate_is_revision_bound_and_browser_executed():
    workflow = read(".github/workflows/sovereign-admin-production-dom.yml")
    spec = read("tests/e2e/admin-production-dom.spec.ts")
    default_config = read("playwright.config.ts")
    assert "expected_revision" in workflow
    assert "Checkout exact deployed revision" in workflow
    assert "playwright.admin-production.config.ts" in workflow
    assert "SOVEREIGN_EXPECTED_REVISION" in workflow
    assert "data-source-revision" in spec
    assert "FreeLLM API 0.5.0 auswählen" in spec
    assert "Sovereign Enterprise Admin" in spec
    assert "testIgnore: 'admin-production-dom.spec.ts'" in default_config
