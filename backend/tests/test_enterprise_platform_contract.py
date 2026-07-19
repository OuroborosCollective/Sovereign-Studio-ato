from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_ROOT = REPOSITORY_ROOT / "scripts" / "sovereign-backend"
MIRROR_ROOT = REPOSITORY_ROOT / "backend"


def read(relative: str) -> str:
    return (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")


def test_enterprise_platform_python_modules_parse() -> None:
    for root in (CANONICAL_ROOT, MIRROR_ROOT):
        for path in (root / "enterprise_platform").glob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_enterprise_platform_deployment_mirror_is_exact() -> None:
    for relative in (
        "enterprise_platform/__init__.py",
        "enterprise_platform/contracts.py",
        "enterprise_platform/service.py",
        "enterprise_platform/routes.py",
        "migrations/025_enterprise_platform_runtime_evidence.sql",
    ):
        assert (CANONICAL_ROOT / relative).read_bytes() == (MIRROR_ROOT / relative).read_bytes()


def test_canonical_backend_registers_modular_platform_with_existing_admin_auth() -> None:
    source = read("scripts/sovereign-backend/app.py")
    assert "register_enterprise_platform_routes(" in source
    assert "require_admin=require_admin" in source
    assert "query=query" in source
    assert "litellm_completion_canary=litellm_completion_canary" in source
    assert '@app.route("/api/admin/system/health", methods=["GET"])' in source
    assert "enterprise_platform_service.overview()" in source


def test_container_and_workflow_bind_runtime_to_exact_source_revision() -> None:
    dockerfile = read("scripts/sovereign-backend/Dockerfile")
    compose = read("scripts/sovereign-backend/docker-compose.yml")
    workflow = read(".github/workflows/sovereign-backend-image.yml")

    assert "ARG SOVEREIGN_SOURCE_REVISION=unverified" in dockerfile
    assert "SOVEREIGN_SOURCE_REVISION=${SOVEREIGN_SOURCE_REVISION}" in dockerfile
    assert "COPY enterprise_platform/ ./enterprise_platform/" in dockerfile
    assert "STOPSIGNAL SIGTERM" in dockerfile
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose and "- ALL" in compose
    assert "pids_limit: 256" in compose
    assert "SOVEREIGN_SOURCE_REVISION: ${SOVEREIGN_SOURCE_REVISION:-unverified}" in compose
    assert "SOVEREIGN_SOURCE_REVISION=${{ github.sha }}" in workflow
    assert "enterprise_platform/*.py" in workflow


def test_runtime_evidence_migration_is_bounded_and_auditable() -> None:
    migration = read("scripts/sovereign-backend/migrations/025_enterprise_platform_runtime_evidence.sql")
    assert "CREATE TABLE IF NOT EXISTS platform_runtime_evidence" in migration
    assert "CHECK (scope IN ('readiness', 'completion'))" in migration
    assert "CHECK (status IN ('verified', 'degraded', 'blocked'))" in migration
    assert "CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$')" in migration
    assert "INSERT INTO schema_migrations" in migration


def test_android_admin_surface_uses_real_api_and_large_touch_contracts() -> None:
    panel = read("src/features/admin/components/EnterpriseBackendPanel.tsx")
    css = read("src/features/admin/components/EnterpriseBackendPanel.css")
    admin_panel = read("src/features/admin/AdminPanel.tsx")
    client = read("src/features/admin/api/adminApiClient.ts")

    for endpoint in (
        "/api/admin/platform/v1/overview",
        "/api/admin/platform/v1/evidence",
        "/api/admin/platform/v1/canaries",
        "/api/admin/platform/v1/openapi.json",
    ):
        assert endpoint in client
    assert "credentials: 'omit'" in client
    assert "AbortController" in client
    assert "window.confirm(" in panel
    assert "activeModelIds" in panel
    assert "Runtime Control Center" in panel
    assert "min-height: 48px" in css
    assert "@media (min-width: 620px)" in css
    assert "@media (min-width: 980px)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "EnterpriseBackendPanel" in admin_panel
    assert "useState<Tab>('platform')" in admin_panel


def test_admin_key_remains_memory_only_and_is_never_rendered() -> None:
    client = read("src/features/admin/api/adminApiClient.ts")
    panel = read("src/features/admin/components/EnterpriseBackendPanel.tsx")

    assert "let adminKeyInMemory = ''" in client
    assert "localStorage" not in client
    assert "sessionStorage" not in client
    assert "getAdminKey" not in panel
    assert "Authorization: `Bearer ${key}`" in client
