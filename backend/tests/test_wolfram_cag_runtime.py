from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
import importlib.util
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load(
    ROOT / "backend" / "agent_runtime" / "adapters" / "wolfram_agenttools.py",
    "wolfram_agenttools_runtime_test",
)
ledger = _load(
    ROOT / "backend" / "agent_runtime" / "wolfram_cag_partner_ledger.py",
    "wolfram_cag_partner_ledger_runtime_test",
)

agent_runtime_pkg = ModuleType("agent_runtime")
agent_runtime_pkg.__path__ = []
adapters_pkg = ModuleType("agent_runtime.adapters")
adapters_pkg.__path__ = []
for name in (
    "WOLFRAM_CAG_COMPONENT_MAP",
    "WolframCagError",
    "execute_live_cag_request",
    "resolve_cag_credentials",
):
    setattr(adapters_pkg, name, getattr(adapter, name))

_STUBBED_MODULE_KEYS = (
    "agent_runtime",
    "agent_runtime.adapters",
    "agent_runtime.adapters.wolfram_agenttools",
    "agent_runtime.wolfram_cag_partner_ledger",
    "flask",
)
_saved_sys_modules = {key: sys.modules.get(key) for key in _STUBBED_MODULE_KEYS}

sys.modules["agent_runtime"] = agent_runtime_pkg
sys.modules["agent_runtime.adapters"] = adapters_pkg
sys.modules["agent_runtime.adapters.wolfram_agenttools"] = adapter
sys.modules["agent_runtime.wolfram_cag_partner_ledger"] = ledger

fake_request = SimpleNamespace(headers={}, get_json=lambda silent=True: {})
flask_module = ModuleType("flask")
flask_module.jsonify = lambda value=None, **kwargs: value if value is not None else kwargs
flask_module.request = fake_request
sys.modules["flask"] = flask_module

runtime = _load(ROOT / "backend" / "wolfram_cag_runtime.py", "wolfram_cag_runtime_test")

# The stubs are only needed while the runtime module executes its top-level
# imports. Restore the previous sys.modules state so this file stays
# collection-safe inside the shared CI pytest process; the loaded modules
# keep working through their own bound references.
for _key, _original in _saved_sys_modules.items():
    if _original is None:
        sys.modules.pop(_key, None)
    else:
        sys.modules[_key] = _original
del _key, _original

WolframCagError = adapter.WolframCagError
WolframCagErrorFamily = adapter.WolframCagErrorFamily

REV = "a" * 40


class _Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _receipt(component: str):
    return SimpleNamespace(
        status=SimpleNamespace(value="SUCCEEDED_UNVERIFIED"),
        response_status=200,
        request_hash="b" * 64,
        response_hash="c" * 64,
        response_uuid="uuid-1",
        request_id="request-1",
        rate_limit_remaining="9",
        quota_remaining="99",
        credential_hash="d" * 64,
    )


def test_status_is_secret_free_and_not_runtime_verified(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", REV)
    monkeypatch.setattr(runtime, "resolve_cag_credentials", lambda **kwargs: SimpleNamespace())
    result = runtime.cag_runtime_status()
    assert result["ok"] is True
    assert result["sourceRevision"] == REV
    assert result["providerCanaryExecuted"] is False
    assert result["runtimeVerified"] is False
    assert result["secretValuesReturned"] is False
    assert len(result["components"]) == 4


def test_canary_success_is_documented_but_stays_unverified(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", REV)
    connection = _Connection()
    persisted = []

    monkeypatch.setattr(runtime, "execute_live_cag_request", lambda **kwargs: _receipt(kwargs["capability_id"]))
    monkeypatch.setattr(runtime, "persist_partner_analysis", lambda conn, record: persisted.append(record) or record["analysisId"])

    result = runtime.run_cag_canaries(
        get_connection=lambda: connection,
        components=["wolfram.cag.compute"],
    )

    assert result["ok"] is True
    assert result["status"] == "WOLFRAM_CAG_CANARIES_SUCCEEDED_UNVERIFIED"
    assert result["runtimeVerified"] is False
    assert result["documentationPersisted"] is True
    assert len(persisted) == 1
    assert persisted[0]["verdict"] == "INCONCLUSIVE"
    assert persisted[0]["documentationClass"] == "PARTNER_REPORTABLE"
    assert "credentialFingerprintSha256" not in result["results"][0]["analysis"]
    assert connection.closed is True


def test_failed_provider_canary_is_persisted_as_unavailable(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", REV)
    connection = _Connection()
    persisted = []

    def fail(**kwargs):
        raise WolframCagError("auth failed", family=WolframCagErrorFamily.AUTH)

    monkeypatch.setattr(runtime, "execute_live_cag_request", fail)
    monkeypatch.setattr(runtime, "persist_partner_analysis", lambda conn, record: persisted.append(record) or record["analysisId"])

    result = runtime.run_cag_canaries(
        get_connection=lambda: connection,
        components=["wolfram.cag.hints"],
    )
    assert result["ok"] is False
    assert result["status"] == "WOLFRAM_CAG_CANARIES_INCOMPLETE"
    assert result["documentationPersisted"] is True
    assert persisted[0]["verdict"] == "UNAVAILABLE"
    assert persisted[0]["failureFamily"] == "AUTH"
    assert result["results"][0]["error"]["family"] == "AUTH"
    assert result["secretValuesReturned"] is False


def test_canary_binds_quota_and_rate_limit_observations_only_when_observed(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", REV)
    connection = _Connection()
    persisted = []

    monkeypatch.setattr(runtime, "execute_live_cag_request", lambda **kwargs: _receipt(kwargs["capability_id"]))
    monkeypatch.setattr(runtime, "persist_partner_analysis", lambda conn, record: persisted.append(record) or record["analysisId"])

    runtime.run_cag_canaries(get_connection=lambda: connection, components=["wolfram.cag.compute"])
    assert persisted[0]["quotaMetadata"] == {"quotaRemaining": "99"}
    assert persisted[0]["rateLimitMetadata"] == {"rateLimitRemaining": "9"}

    persisted.clear()
    receipt = _receipt("wolfram.cag.compute")
    receipt.quota_remaining = ""
    receipt.rate_limit_remaining = ""
    monkeypatch.setattr(runtime, "execute_live_cag_request", lambda **kwargs: receipt)
    runtime.run_cag_canaries(get_connection=lambda: connection, components=["wolfram.cag.compute"])
    assert persisted[0]["quotaMetadata"] == {}
    assert persisted[0]["rateLimitMetadata"] == {}


class _App:
    def __init__(self):
        self.routes = {}

    def route(self, path, methods):
        def decorator(func):
            self.routes[(path, tuple(methods))] = func
            return func
        return decorator


def test_runtime_routes_require_owner_bridge_and_reject_arbitrary_input(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    app = _App()
    runtime.register_wolfram_cag_runtime(app, get_connection=lambda: _Connection())
    status_route = app.routes[("/api/internal/wolfram-cag/status", ("GET",))]
    canary_route = app.routes[("/api/internal/wolfram-cag/canary", ("POST",))]
    report_route = app.routes[("/api/internal/wolfram-cag/partner-report", ("GET",))]

    runtime.request.headers = {}
    denied_body, denied_status = status_route()
    assert denied_status == 401
    assert denied_body["error"] == "service_unauthorized"
    denied_report_body, denied_report_status = report_route()
    assert denied_report_status == 401
    assert denied_report_body["error"] == "service_unauthorized"

    runtime.request.headers = {"X-Sovereign-Owner-Request-Key": "bridge-key"}
    runtime.request.get_json = lambda silent=True: {"prompt": "arbitrary provider input is forbidden"}
    invalid_body, invalid_status = canary_route()
    assert invalid_status == 400
    assert invalid_body["error"] == "invalid_request"

    runtime.request.get_json = lambda silent=True: {"components": ["wolfram.cag.agent-one"]}
    invalid_component_body, invalid_component_status = canary_route()
    assert invalid_component_status == 400
    assert "unknown CAG capability" in invalid_component_body["error"]


class _ReportCursor:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class _ReportConnection:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def cursor(self):
        return _ReportCursor(self.rows)

    def close(self):
        self.closed = True


def _persisted_row(record):
    return (
        record["analysisId"], record["schemaVersion"], record["analysisRecordSha256"], REV, REV,
        None, None, record["cagComponent"], record["cagContractVersion"],
        record["normalizedQuestion"], record["normalizedInputSha256"], "request-1",
        "uuid-1", record["providerResponseSha256"], None, record["verdict"],
        record["documentationClass"], record["derivedConclusion"], None,
        record["quotaMetadata"], record["rateLimitMetadata"],
        record["assumptions"], record["limitations"], record["sourceRefs"],
        None, None, None, None,
    )


def test_partner_report_is_deterministic_secret_free_projection(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", REV)
    record = ledger.build_partner_analysis_record(
        component="WolframLanguageComputation",
        normalized_question='{"code":"2+2"}',
        normalized_input_sha256="a" * 64,
        provider_response_sha256="b" * 64,
        credential_fingerprint_sha256="d" * 64,
        verdict="INCONCLUSIVE",
        derived_conclusion="Transport canary succeeded; no semantic claim evaluated.",
        documentation_class="PARTNER_REPORTABLE",
        quota_metadata={"quotaRemaining": "99"},
        limitations=["Provider success is not runtime verification."],
        source_refs=["wolfram-official-cag-v1-contract"],
        created_at="2026-08-22T00:00:00Z",
    )
    connection = _ReportConnection([_persisted_row(record)])
    app = _App()
    runtime.register_wolfram_cag_runtime(app, get_connection=lambda: connection)
    report_route = app.routes[("/api/internal/wolfram-cag/partner-report", ("GET",))]
    runtime.request.headers = {"X-Sovereign-Owner-Request-Key": "bridge-key"}

    first_body, first_status = report_route()
    connection.closed = False
    second_body, second_status = report_route()
    assert first_status == 200 and second_status == 200
    assert first_body["ok"] is True
    assert first_body["status"] == "WOLFRAM_CAG_PARTNER_REPORT"
    assert first_body["recordCount"] == 1
    assert first_body["pack"]["packSha256"] == second_body["pack"]["packSha256"]
    assert first_body["secretValuesReturned"] is False
    rendered = repr(first_body)
    assert "credentialFingerprintSha256" not in rendered
    assert "Wolfram CAG Partner Handoff Pack" in first_body["markdown"]
    assert first_body["pack"]["analyses"][0]["quotaMetadata"] == {"quotaRemaining": "99"}


def test_partner_report_fails_closed_on_readback_error(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")

    class _BrokenConnection:
        def cursor(self):
            raise RuntimeError("database unavailable")

        def close(self):
            pass

    app = _App()
    runtime.register_wolfram_cag_runtime(app, get_connection=lambda: _BrokenConnection())
    report_route = app.routes[("/api/internal/wolfram-cag/partner-report", ("GET",))]
    runtime.request.headers = {"X-Sovereign-Owner-Request-Key": "bridge-key"}
    body, status = report_route()
    assert status == 500
    assert body["ok"] is False
    assert body["errorFamily"] == "ANALYSIS_LEDGER_READBACK"
    assert body["secretValuesReturned"] is False


def test_runtime_and_deployment_mirror_match_compile_and_app_registers_routes():
    canonical_path = ROOT / "backend" / "wolfram_cag_runtime.py"
    mirror_path = ROOT / "scripts" / "sovereign-backend" / "wolfram_cag_runtime.py"
    canonical = canonical_path.read_bytes()
    mirror = mirror_path.read_bytes()
    assert canonical == mirror
    compile(canonical, str(canonical_path), "exec")
    compile(mirror, str(mirror_path), "exec")

    app_source = (ROOT / "scripts" / "sovereign-backend" / "app.py").read_text("utf-8")
    assert "from wolfram_cag_runtime import register_wolfram_cag_runtime" in app_source
    assert "register_wolfram_cag_runtime(" in app_source
    assert "get_connection=get_agent_runtime_connection" in app_source
