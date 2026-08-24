"""Regression contract for the complete active frontend endpoint surface.

The scanner under test is the production repository assurance implementation.
These tests never contact a live endpoint; live reachability is owned by the
Playwright runtime smoke lane.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = REPO_ROOT / "scripts" / "frontend_endpoint_assurance.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("frontend_endpoint_assurance", SCANNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_frontend_has_no_unbound_active_internal_endpoints():
    assurance = _load_scanner()
    report = assurance.build_report()

    assert report["status"] == "PASS", "\n" + "\n".join(
        f"{item['normalized']} <- {item['source']}:{item['line']}"
        for item in report["unbound"]
    )
    assert report["counts"]["uniqueActiveInternalEndpoints"] > 0
    assert report["counts"]["uniqueUnboundActiveInternalEndpoints"] == 0
    assert report["authoritativeRuntime"] is False
    assert report["runtimeConnectivityProven"] is False


def test_removed_phantom_billing_routes_do_not_reappear():
    assurance = _load_scanner()
    report = assurance.build_report()
    endpoints = {item["normalized"] for item in report["references"]}

    assert "/api/billing/cancel" not in endpoints
    assert "/api/billing/restore" not in endpoints


def test_dynamic_frontend_and_flask_parameters_normalize_to_same_contract():
    assurance = _load_scanner()

    frontend = assurance.normalize_endpoint(
        "/api/user/agent/jobs/${encodeURIComponent(jobId)}/projections?limit=100"
    )
    backend = assurance.normalize_endpoint("/api/user/agent/jobs/<job_id>/projections")

    assert frontend == "/api/user/agent/jobs/<p>/projections"
    assert backend == frontend


def test_colon_parameter_normalizes_to_backend_parameter_contract():
    assurance = _load_scanner()

    assert assurance.normalize_endpoint('/api/llm/routes/:id') == '/api/llm/routes/<p>'
    assert assurance.normalize_endpoint('/api/llm/routes/<route_id>') == '/api/llm/routes/<p>'


def test_blueprint_url_prefix_is_part_of_backend_route_ownership(tmp_path):
    assurance = _load_scanner()
    assurance.ROOT = tmp_path

    frontend = tmp_path / 'src' / 'admin.ts'
    frontend.parent.mkdir(parents=True)
    frontend.write_text("const endpoint='/api/admin/platform/v1/overview';\n", 'utf-8')
    backend = tmp_path / 'backend' / 'routes.py'
    backend.parent.mkdir(parents=True)
    backend.write_text(
        "from flask import Blueprint\n"
        "blueprint = Blueprint('platform', __name__, url_prefix='/api/admin/platform/v1')\n"
        "@blueprint.get('/overview')\n"
        "def overview(): return {}\n",
        'utf-8',
    )

    report = assurance.build_report()

    assert report['status'] == 'PASS', report['unbound']
    ref = next(item for item in report['references'] if item['normalized'].endswith('/overview'))
    assert ref['backend_sources'] == ('backend/routes.py',)


def test_comments_and_import_fragments_do_not_invent_endpoint_dependencies(tmp_path):
    assurance = _load_scanner()
    assurance.ROOT = tmp_path

    frontend = tmp_path / 'src' / 'feature.ts'
    frontend.parent.mkdir(parents=True)
    frontend.write_text(
        "import thing from './api/adminApiClient';\n"
        "// historical /api/not-a-live-call\n"
        "/* old /api/also-not-live */\n"
        "const endpoint='/api/real';\n",
        'utf-8',
    )
    backend = tmp_path / 'backend' / 'app.py'
    backend.parent.mkdir(parents=True)
    backend.write_text("@app.route('/api/real')\ndef real(): return {}\n", 'utf-8')

    report = assurance.build_report()
    endpoints = {item['normalized'] for item in report['references']}

    assert report['status'] == 'PASS'
    assert endpoints == {'/api/real'}


def test_public_llm_route_is_bound_to_real_deployment_backend_source():
    assurance = _load_scanner()
    routes = assurance.extract_backend_routes()
    sources = {
        route.source
        for route in routes
        if route.normalized == "/api/llm/routes"
    }

    assert "scripts/sovereign-backend/app.py" in sources


def test_unmatched_active_endpoint_fails_closed(tmp_path):
    assurance = _load_scanner()
    assurance.ROOT = tmp_path

    frontend = tmp_path / "src" / "feature.ts"
    frontend.parent.mkdir(parents=True)
    frontend.write_text(
        "export async function broken() { return fetch('/api/not-owned-by-backend'); }\n",
        "utf-8",
    )
    backend = tmp_path / "backend" / "app.py"
    backend.parent.mkdir(parents=True)
    backend.write_text(
        "from flask import Flask\napp = Flask(__name__)\n@app.route('/api/owned')\ndef owned(): return {}\n",
        "utf-8",
    )

    report = assurance.build_report()

    assert report["status"] == "FAIL"
    assert report["counts"]["uniqueUnboundActiveInternalEndpoints"] == 1
    assert report["unbound"][0]["normalized"] == "/api/not-owned-by-backend"


def test_external_and_retired_bridges_cannot_masquerade_as_internal_runtime_green(tmp_path):
    assurance = _load_scanner()
    assurance.ROOT = tmp_path

    frontend = tmp_path / "src" / "feature.ts"
    frontend.parent.mkdir(parents=True)
    frontend.write_text(
        "const memory='/api/sovereign-memory/search';\n"
        "const retired='/api/vps/connect';\n"
        "const gemini='/api/ai/gemini';\n",
        "utf-8",
    )
    (tmp_path / "backend").mkdir()

    report = assurance.build_report()
    refs = {item["normalized"]: item for item in report["references"]}

    assert report["status"] == "PASS"
    assert refs["/api/sovereign-memory/search"]["classification"] == "EXTERNAL_SERVICE"
    assert refs["/api/vps/connect"]["classification"] == "RETIRED_OR_NONCANONICAL"
    assert refs["/api/ai/gemini"]["classification"] == "RETIRED_OR_NONCANONICAL"
    assert refs["/api/sovereign-memory/search"]["owner"] != "sovereign-backend"
    assert refs["/api/sovereign-memory/search"]["backed"] is False
    assert refs["/api/vps/connect"]["backed"] is False
    assert refs["/api/ai/gemini"]["backed"] is False


def test_test_and_spec_files_do_not_inflate_product_endpoint_inventory(tmp_path):
    assurance = _load_scanner()
    assurance.ROOT = tmp_path

    src = tmp_path / "src"
    src.mkdir()
    (src / "real.ts").write_text("const e='/api/real';\n", "utf-8")
    (src / "fake.test.ts").write_text("const e='/api/test-only';\n", "utf-8")
    backend = tmp_path / "backend" / "app.py"
    backend.parent.mkdir(parents=True)
    backend.write_text("@app.route('/api/real')\ndef real(): return {}\n", "utf-8")

    report = assurance.build_report()
    endpoints = {item["normalized"] for item in report["references"]}

    assert endpoints == {"/api/real"}
