from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "frontend_endpoint_contracts.py"
SPEC = importlib.util.spec_from_file_location("frontend_endpoint_contracts", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_template_fetch_binds_to_real_flask_method(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/api.ts",
        """
        const API_BASE = '';
        export async function updateItem(itemId: string) {
          return fetch(`${API_BASE}/api/items/${encodeURIComponent(itemId)}?view=full`, {
            method: 'PATCH',
            credentials: 'include',
          });
        }
        """,
    )
    _write(
        tmp_path,
        "scripts/sovereign-backend/app.py",
        """
        @app.route('/api/items/<item_id>', methods=['PATCH'])
        def update_item(item_id):
            return {'itemId': item_id}
        """,
    )
    _write(
        tmp_path,
        "src/api.test.ts",
        "expect(fetch).toHaveBeenCalledWith('/api/items/item-1', expect.any(Object));",
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "pass"
    assert report["summary"]["activeRequestCount"] == 1
    binding = next(
        item for item in report["bindings"]
        if item["call"]["source_kind"] == "request-call"
    )
    assert binding["call"]["path"] == "/api/items/<p>"
    assert binding["call"]["method"] == "PATCH"
    assert binding["status"] == "BOUND"
    assert binding["backendRoutes"][0]["methods"] == ("PATCH",)
    assert binding["testReferences"]["unit"] == ["src/api.test.ts"]


def test_blueprint_prefix_and_query_are_normalized(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/platform.ts",
        "fetch('/api/admin/platform/v1/identity?fresh=1', { credentials: 'include' });",
    )
    _write(
        tmp_path,
        "backend/enterprise/routes.py",
        """
        bp = Blueprint('enterprise', __name__, url_prefix='/api/admin/platform/v1')

        @bp.get('/identity')
        def identity():
            return {'ok': True}
        """,
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "pass"
    assert report["summary"]["boundActiveRequestCount"] == 1
    binding = next(item for item in report["bindings"] if item["call"]["source_kind"] == "request-call")
    assert binding["call"]["path"] == "/api/admin/platform/v1/identity"
    assert binding["status"] == "BOUND"


def test_custom_fetch_defaults_to_get_and_transformer_is_not_an_http_call(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/security.ts",
        """
        async function tcFetch(path: string, options?: RequestInit) {
          return fetch(path, options);
        }
        function requestOptions(value: unknown) {
          return value;
        }
        export async function loadManifest() {
          const manifest = await tcFetch('/api/toolchain/manifest');
          const options = await tcFetch('/api/security/options', { method: 'POST' });
          requestOptions(options);
          return manifest;
        }
        """,
    )
    _write(
        tmp_path,
        "backend/routes.py",
        """
        @app.get('/api/toolchain/manifest')
        def manifest():
            return {'ok': True}

        @app.post('/api/security/options')
        def options():
            return {'challenge': 'bounded'}
        """,
    )
    _write(
        tmp_path,
        "src/security.test.ts",
        "expect(fetch).toHaveBeenCalledWith('/api/security/options', expect.objectContaining({ method: 'POST' }));",
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "pass", report["errors"]
    requests = [item for item in report["bindings"] if item["call"]["source_kind"] == "request-call"]
    assert [(item["call"]["path"], item["call"]["method"]) for item in requests] == [
        ("/api/security/options", "POST"),
        ("/api/toolchain/manifest", "GET"),
    ]
    assert all(item["call"]["call_name"] != "requestOptions" for item in requests)


def test_injected_fetcher_defaults_external_read_to_get(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/github.ts",
        """
        export async function readPullRequest(fetcher: typeof fetch) {
          return fetcher('https://api.github.com/repos/acme/repo/pulls/7', { headers: {} });
        }
        """,
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "pass", report["errors"]
    assert report["externalCalls"][0]["method"] == "GET"
    assert report["externalCalls"][0]["call_name"] == "fetcher"
    assert report["summary"]["externalMethodUnknownCount"] == 0


def test_external_absolute_request_is_inventoried_without_backend_promotion(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/external.ts",
        "fetch('https://identity@partner.example:8443/api/analyze', { method: 'POST' });",
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "pass"
    assert report["summary"]["activeRequestCount"] == 0
    assert report["summary"]["externalRequestCount"] == 1
    assert report["summary"]["activeExternalRequestCount"] == 1
    assert report["summary"]["externalMethodUnknownCount"] == 0
    assert report["externalCalls"] == [{
        "url": "https://partner.example:8443/api/analyze",
        "host": "partner.example",
        "path": "/api/analyze",
        "method": "POST",
        "file": "src/external.ts",
        "line": 1,
        "call_name": "fetch",
        "surface_status": "active",
        "active_surface": True,
    }]
    assert report["truthBoundary"]["externalTargetReachabilityProven"] is False


def test_non_active_surface_is_inventoried_but_not_promoted(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/legacy.ts",
        """
        // sovereign-endpoint-surface: legacy-unreferenced
        export const callLegacy = () => fetch('/api/legacy/worker');
        """,
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "pass"
    assert report["summary"]["activeRequestCount"] == 0
    binding = next(item for item in report["bindings"] if item["call"]["source_kind"] == "request-call")
    assert binding["status"] == "NON_ACTIVE"
    assert binding["call"]["active_surface"] is False


def test_active_import_cannot_reactivate_legacy_endpoint_surface(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/legacy.ts",
        """
        // sovereign-endpoint-surface: legacy-unreferenced
        export const callLegacy = () => fetch('/api/legacy/worker');
        """,
    )
    _write(
        tmp_path,
        "src/active.ts",
        """
        import { callLegacy } from './legacy';
        export const run = callLegacy;
        """,
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "fail"
    assert report["summary"]["legacyImportViolationCount"] == 1
    violation = next(
        item for item in report["errors"]
        if item["family"] == "ACTIVE_IMPORTS_NON_ACTIVE_ENDPOINT_SURFACE"
    )
    assert violation == {
        "family": "ACTIVE_IMPORTS_NON_ACTIVE_ENDPOINT_SURFACE",
        "source": "src/active.ts",
        "target": "src/legacy.ts",
        "sourceStatus": "active",
        "targetStatus": "legacy-unreferenced",
        "line": 1,
        "dynamic": False,
    }


def test_typescript_alias_import_cannot_bypass_legacy_gate(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/legacy.ts",
        """
        // sovereign-endpoint-surface: legacy-unreferenced
        export const legacy = 1;
        """,
    )
    _write(
        tmp_path,
        "src/active.ts",
        """
        import { legacy } from '@/legacy';
        export const value = legacy;
        """,
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "fail"
    assert report["summary"]["legacyImportViolationCount"] == 1
    assert report["errors"][0]["source"] == "src/active.ts"
    assert report["errors"][0]["target"] == "src/legacy.ts"


def test_type_only_import_does_not_reactivate_legacy_surface(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/legacy.ts",
        """
        // sovereign-endpoint-surface: legacy-unreferenced
        export interface LegacyShape { value: string }
        """,
    )
    _write(
        tmp_path,
        "src/active.ts",
        """
        import type { LegacyShape } from './legacy';
        export const value: LegacyShape = { value: 'bounded' };
        """,
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "pass", report["errors"]
    assert report["summary"]["legacyImportViolationCount"] == 0
    assert report["importEdges"] == []


def test_bound_mutation_without_test_evidence_fails_closed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/api.ts",
        "fetch('/api/items', { method: 'POST' });",
    )
    _write(
        tmp_path,
        "backend/routes.py",
        """
        @app.post('/api/items')
        def create_item():
            return {'ok': True}
        """,
    )

    missing = MODULE.build_report(tmp_path)

    assert missing["status"] == "fail"
    assert missing["summary"]["activeMutationRequestCount"] == 1
    assert missing["summary"]["activeMutationWithoutTestEvidenceCount"] == 1
    assert missing["errors"] == [{
        "family": "FRONTEND_MUTATION_TEST_EVIDENCE_MISSING",
        "method": "POST",
        "path": "/api/items",
        "file": "src/api.ts",
        "line": 1,
    }]

    _write(
        tmp_path,
        "src/api.test.ts",
        "expect(fetch).toHaveBeenCalledWith('/api/items', expect.objectContaining({ method: 'POST' }));",
    )
    covered = MODULE.build_report(tmp_path)
    assert covered["status"] == "pass", covered["errors"]
    assert covered["summary"]["activeMutationWithoutTestEvidenceCount"] == 0


def test_unmatched_and_method_mismatch_fail_closed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/api.ts",
        """
        export const missing = () => fetch('/api/missing');
        export const wrongMethod = () => fetch('/api/items', { method: 'DELETE' });
        """,
    )
    _write(
        tmp_path,
        "scripts/sovereign-backend/app.py",
        """
        @app.get('/api/items')
        def items():
            return {'items': []}
        """,
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "fail"
    families = {item["family"] for item in report["errors"]}
    assert families == {
        "FRONTEND_ENDPOINT_METHOD_MISMATCH",
        "FRONTEND_ENDPOINT_UNMATCHED",
    }


def test_concatenated_dynamic_route_is_bound_without_partial_prefix(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/rescue.ts",
        """
        export const capsule = (repairId: string) => fetch(
          '/api/user/agent/rescue/repairs/' + encodeURIComponent(repairId) + '/capsule',
          { method: 'POST' },
        );
        """,
    )
    _write(
        tmp_path,
        "backend/routes.py",
        """
        @app.post('/api/user/agent/rescue/repairs/<repair_id>/capsule')
        def capsule(repair_id):
            return {'repairId': repair_id}
        """,
    )
    _write(
        tmp_path,
        "src/rescue.test.ts",
        "expect(fetch).toHaveBeenCalledWith('/api/user/agent/rescue/repairs/repair-1/capsule', expect.objectContaining({ method: 'POST' }));",
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "pass", report["errors"]
    requests = [item for item in report["bindings"] if item["call"]["source_kind"] == "request-call"]
    assert len(requests) == 1
    assert requests[0]["call"]["path"] == "/api/user/agent/rescue/repairs/<p>/capsule"
    assert requests[0]["status"] == "BOUND"


def test_static_asset_is_not_misclassified_as_backend_runtime(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/coverage.ts",
        "fetch('/generated/test-coverage-map.json', { cache: 'no-store' });",
    )

    report = MODULE.build_report(tmp_path)

    assert report["status"] == "pass"
    binding = next(item for item in report["bindings"] if item["call"]["source_kind"] == "request-call")
    assert binding["status"] == "STATIC_ASSET"
    assert report["summary"]["activeRequestCount"] == 0


def test_symlinked_source_is_not_followed_outside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside.ts"
    _write(tmp_path, "outside.ts", "fetch('/api/escaped');")
    source = repository / "src" / "escaped.ts"
    source.parent.mkdir(parents=True, exist_ok=True)
    try:
        source.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    report = MODULE.build_report(repository)

    assert report["status"] == "pass"
    assert report["summary"]["frontendCallCount"] == 0
    assert report["summary"]["activeRequestCount"] == 0


def test_cli_writes_report_and_fails_closed_on_drift(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/client.ts",
        "fetch('/api/health');",
    )
    _write(
        tmp_path,
        "backend/routes.py",
        """
        @app.get('/api/health')
        def health():
            return {'ok': True}
        """,
    )
    report_path = tmp_path / "report.json"

    success = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--repo",
            str(tmp_path),
            "--report",
            str(report_path),
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert success.returncode == 0, success.stderr
    summary = json.loads(success.stdout)
    persisted = json.loads(report_path.read_text("utf-8"))
    assert summary["status"] == "pass"
    assert persisted["status"] == "pass"
    assert summary["reportSha256"] == persisted["reportSha256"]
    assert summary["runtimeReachabilityProven"] is False

    _write(tmp_path, "src/client.ts", "fetch('/api/missing');")
    failure = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--repo",
            str(tmp_path),
            "--report",
            str(report_path),
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert failure.returncode == 1
    assert json.loads(report_path.read_text("utf-8"))["status"] == "fail"

    outside_report = tmp_path.parent / f"{tmp_path.name}-outside-report.json"
    outside_report.unlink(missing_ok=True)
    escaped = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--repo",
            str(tmp_path),
            "--report",
            str(outside_report),
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert escaped.returncode == 2
    assert not outside_report.exists()


def test_current_repository_has_no_active_frontend_backend_contract_gap() -> None:
    repository = Path(__file__).resolve().parents[2]

    report = MODULE.build_report(repository)

    assert report["status"] == "pass", json.dumps(report["errors"][:40], indent=2)
    assert report["summary"]["frontendModuleCount"] >= 100
    assert report["summary"]["importEdgeCount"] >= 100
    assert report["summary"]["legacyImportViolationCount"] == 0
    assert report["summary"]["activeRequestCount"] >= 20
    assert report["summary"]["boundActiveRequestCount"] == report["summary"]["activeRequestCount"], json.dumps(report["warnings"][:40], indent=2)
    assert report["summary"]["activeMutationRequestCount"] >= 1
    assert report["summary"]["activeMutationWithoutTestEvidenceCount"] == 0
    assert report["summary"]["activeReadRequestCount"] >= 1
    assert report["summary"]["activeReadWithoutTestEvidenceCount"] == 0, json.dumps(report["warnings"][:80], indent=2)
    assert report["summary"]["backendRouteCount"] >= 100
    assert report["summary"]["externalRequestCount"] >= 1
    assert report["summary"]["externalMethodUnknownCount"] == 0
    assert report["truthBoundary"] == {
        "repositoryContractEvidence": True,
        "networkRequestsPerformed": False,
        "runtimeReachabilityProven": False,
        "authenticationProven": False,
        "targetEffectProven": False,
        "externalTargetReachabilityProven": False,
    }
