import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
APP_SOURCE = REPO_ROOT / "scripts" / "sovereign-backend" / "app.py"
DOCKERFILE = REPO_ROOT / "scripts" / "sovereign-backend" / "Dockerfile"
IMAGE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "sovereign-backend-image.yml"
MAIN_SOURCE = REPO_ROOT / "src" / "main.tsx"
ADMIN_PANEL = REPO_ROOT / "src" / "features" / "admin" / "AdminPanel.tsx"
FREE_REVOLVER = (
    REPO_ROOT
    / "src"
    / "features"
    / "admin"
    / "components"
    / "FreeRevolverControlCenter.tsx"
)
PRODUCTION_E2E = REPO_ROOT / "tests" / "e2e" / "admin-production-dom.spec.ts"
OPEN_ISSUES = REPO_ROOT / "docs" / "architecture" / "SOVEREIGN_MANIFEST_OPEN_ISSUES.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_admin_route_has_one_fail_closed_react_producer() -> None:
    source = _read(APP_SOURCE)
    assert "ENTERPRISE_ADMIN_HTML" not in source
    assert "from enterprise_admin_ui import" not in source
    assert 'SOVEREIGN_ADMIN_WEB_ROOT' in source
    assert 'send_from_directory(_ADMIN_WEB_ROOT, normalized)' in source
    assert '"blocker": "react_admin_artifact_missing"' in source
    assert 'response.headers["X-Sovereign-Admin-Surface"] = "react"' in source
    assert 'response.headers["X-Sovereign-Source-Revision"]' in source
    assert 'return _admin_web_response("index.html")' in source
    assert "def admin_panel_asset(asset_path: str):" in source


def test_backend_image_contains_admin_build_from_same_revision_context() -> None:
    dockerfile = _read(DOCKERFILE)
    workflow = _read(IMAGE_WORKFLOW)
    assert "FROM node:22-bookworm-slim AS admin-web-build" in dockerfile
    assert "pnpm install --frozen-lockfile --ignore-scripts" in dockerfile
    assert "pnpm exec vite build --base=/admin/" in dockerfile
    assert "COPY --from=admin-web-build /workspace/dist/ /app/admin-web/" in dockerfile
    assert "rm -f /app/enterprise_admin_ui.py" in dockerfile
    assert "test -s /app/admin-web/index.html" in dockerfile
    assert "context: ." in workflow
    assert "context: scripts/sovereign-backend" not in workflow
    assert "- 'src/features/admin/**'" in workflow


def test_react_bootstrap_and_required_admin_dom_contract_exist() -> None:
    main = _read(MAIN_SOURCE)
    panel = _read(ADMIN_PANEL)
    revolver = _read(FREE_REVOLVER)
    assert "isAdminRoute" in main
    assert "isAdminRoute ? <AdminPanel /> : <App />" in main
    assert 'data-testid="sovereign-react-admin"' in panel
    assert 'data-testid="free-revolver-control-center"' in revolver
    assert 'data-testid="freellm-provider-registration"' in revolver
    assert 'data-testid="freellm-managed-provider-select"' in revolver
    assert "FreeLLM API 0.5.0 · interner Docker" in revolver
    assert "managed-bearer" in revolver


def test_manifest_issue_bundle_remains_valid_json() -> None:
    bundle = json.loads(_read(OPEN_ISSUES))
    issue = next(
        item for item in bundle["issues"]
        if item["key"] == "remove-dead-legacy-admin-html"
    )
    assert "React-Control-Center" in issue["title"]
    assert "FreeRevolverControlCenter" in issue["evidence"]
    assert "Produktions-DOM-Gate" in " ".join(issue["workflow"])


def test_production_gate_binds_revision_headers_and_visible_dom() -> None:
    e2e = _read(PRODUCTION_E2E)
    assert "SOVEREIGN_EXPECTED_REVISION" in e2e
    assert "SOVEREIGN_ADMIN_E2E_KEY" in e2e
    assert "health.sourceRevision" in e2e
    assert "x-sovereign-admin-surface" in e2e
    assert "x-sovereign-source-revision" in e2e
    assert "free-revolver-control-center" in e2e
    assert "freellm-provider-registration" in e2e
    assert "freellm-managed-provider-select" in e2e
    assert "name: 'Free Revolver'" in e2e
    assert "Sovereign Enterprise Admin" in e2e
    assert "page.route(" not in e2e
