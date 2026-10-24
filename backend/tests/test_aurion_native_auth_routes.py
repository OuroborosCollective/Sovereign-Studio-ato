"""Real Flask owner routes and protected state; external broker/queue adapters only."""
import ast
from functools import wraps
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask, g, jsonify, request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/sovereign-backend"))
import aurion_native_auth_routes as routes
from aurion_native_auth import NativeAuthRepair, NativeAuthState
from command_queue import HostCommandQueueClient

OWNER_TEST_KEY = "SYNTHETIC_OWNER_BEARER_SECRET"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_ID", "configured-owner")
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_BACKEND_PUBLIC_URL", "https://sovereign-backend.arelorian.de")
    tmp_path.chmod(0o700)
    current = {"id": "configured-owner"}
    snapshot = {"target": "echoes-of-aurion/aurion", "revision": "a" * 40, "containerId": "b" * 64,
        "imageId": "sha256:" + "c" * 64, "metadataFingerprint": "d" * 64, "configurationFingerprint": "e" * 64,
        "schemaVerified": True, "healthy": True,
        "configuration": {"releaseEnabled": False, "stateSealKeyPresent": False, "stateSealKeyValid": False}}
    calls, jobs = [], []
    def broker(action, arguments, **kwargs):
        calls.append((action, arguments))
        if action == "aurion_native_auth_readback":
            return {"operationId": arguments["operation_id"], "phase": "APPROVAL_PENDING"}
        return {"snapshot": snapshot, "planHash": "synthetic-non-authority"}
    monkeypatch.setattr(routes, "_broker_call", broker)
    class Queue(HostCommandQueueClient):
        def __init__(self):
            super().__init__(str(tmp_path / "queue"))
        def enqueue(self, action, arguments):
            jobs.append((action, arguments))
            return super().enqueue(action, arguments)
    monkeypatch.setattr(routes, "HostCommandQueueClient", Queue)
    monkeypatch.setattr(os, "fchown", lambda *args: None)
    original = os.fstat
    def fstat(fd):
        result = original(fd)
        fields = {k: getattr(result, k) for k in dir(result) if k.startswith("st_")}
        fields.update(st_uid=0, st_gid=0)
        if stat.S_ISDIR(result.st_mode):
            fields["st_mode"] &= ~0o022
        return SimpleNamespace(**fields)
    monkeypatch.setattr(os, "fstat", fstat)
    app = Flask(__name__)
    # Execute the actual app auth functions, without starting unrelated app
    # services. Only external credential DB/bootstrap lookups are substituted.
    source = ROOT / "scripts/sovereign-backend/app.py"
    tree = ast.parse(source.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name in {"require_admin", "get_current_admin"}]
    assert len(selected) == 2
    auth = {"wraps": wraps, "g": g, "jsonify": jsonify, "request": request,
            "_lookup_admin_api_key": lambda token: current if token == OWNER_TEST_KEY else None,
            "_lookup_bootstrap_admin": lambda token: None}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), auth)
    routes.register_aurion_native_auth_routes(app, require_admin=auth["require_admin"], get_current_admin=auth["get_current_admin"])
    return app.test_client(), current, calls, jobs, snapshot, tmp_path


def headers():
    return {"Authorization": "Bearer " + OWNER_TEST_KEY, "Origin": "https://sovereign-backend.arelorian.de", "X-Sovereign-Owner-Action": "aurion-native-auth"}


def plan(api):
    response = api.post("/api/admin/aurion-native-auth/plan", json={"expectedRevision": "a" * 40}, headers=headers())
    assert response.status_code == 200
    return response.json


def test_authenticated_same_origin_plan_approval_queues_metadata_only(client):
    api, _, calls, jobs, _, root = client
    preview = plan(api)
    assert list(root.iterdir()) == []  # plan is read-only
    response = api.post("/api/admin/aurion-native-auth/approve", json={"expectedRevision": "a" * 40,
                        "planHash": preview["planHash"]}, headers=headers())
    assert response.status_code == 202
    operation = response.json["operationId"]
    assert jobs == [("aurion_native_auth_apply", {"operation_id": operation})]
    assert response.json["queueStatus"] == "QUEUED"
    readback = api.get("/api/admin/aurion-native-auth/readback/" + operation, headers=headers())
    assert readback.status_code == 200 and readback.json["operationId"] == operation
    assert OWNER_TEST_KEY not in response.text + readback.text
    for record_file in root.rglob("*.json"):
        assert OWNER_TEST_KEY not in record_file.read_text()
    record = NativeAuthState(root).read("approval", operation)
    assert record["plan"] == preview
    assert record["target"] == "echoes-of-aurion/aurion"
    assert len(calls) == 3  # independent fresh plan at approval plus readback
    assert "no-store" in response.headers["Cache-Control"]


@pytest.mark.parametrize("kind", ["wrong-owner", "no-origin", "cross-origin", "no-header"])
def test_owner_and_csrf_fail_before_broker_or_persistence(client, kind):
    api, current, calls, jobs, _, root = client
    selected = headers()
    if kind == "wrong-owner": current["id"] = "not-owner"
    if kind == "no-origin": selected.pop("Origin")
    if kind == "cross-origin": selected["Origin"] = "https://other.invalid"
    if kind == "no-header": selected.pop("X-Sovereign-Owner-Action")
    response = api.post("/api/admin/aurion-native-auth/approve", json={"expectedRevision": "a" * 40,
                        "planHash": "a" * 64}, headers=selected)
    assert response.status_code == 403
    assert calls == jobs == [] and list(root.iterdir()) == []


def test_plan_drift_denies_without_queue(client):
    api, _, _, jobs, snapshot, root = client
    preview = plan(api)
    snapshot["imageId"] = "sha256:" + "0" * 64
    response = api.post("/api/admin/aurion-native-auth/approve", json={"expectedRevision": "a" * 40,
                        "planHash": preview["planHash"]}, headers=headers())
    assert response.status_code == 409
    assert jobs == [] and not list(root.glob("*approval*"))


def test_client_owner_assertion_cannot_create_action(client):
    api, _, calls, jobs, _, _ = client
    response = api.post("/api/admin/aurion-native-auth/approve", json={"expectedRevision": "a" * 40,
        "planHash": "a" * 64, "owner_approved": True}, headers=headers())
    assert response.status_code == 409 and calls == jobs == []


def test_secret_exception_is_not_in_http_response(client, monkeypatch):
    api, *_ = client
    def fail(*args, **kwargs):
        raise ValueError("SYNTHETIC_PRIVATE_HTTP_BODY")
    monkeypatch.setattr(routes, "_broker_call", fail)
    response = api.post("/api/admin/aurion-native-auth/plan", json={"expectedRevision": "a" * 40}, headers=headers())
    assert response.status_code == 409
    assert "SYNTHETIC_PRIVATE_HTTP_BODY" not in response.text


def test_owner_page_shows_risks_and_has_no_auto_approval(client):
    api, current, calls, jobs, *_ = client
    response = api.get("/owner-aurion-native-auth")
    assert response.status_code == 200 and calls == jobs == []
    assert 'id="approve" disabled' in response.text
    assert "kurzlebige" in response.text and "Rücknahme" in response.text
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "Authorization:'Bearer '+admin" in response.text
    assert "sessionStorage" not in response.text and "localStorage" not in response.text
    assert 'type="password"' in response.text and "redirect:'error'" in response.text


@pytest.mark.parametrize("path,method", [("plan", "post"), ("approve", "post"), ("readback/" + "a" * 32, "get")])
@pytest.mark.parametrize("authorization", [None, "Bearer invalid", "Basic invalid"])
def test_real_bearer_boundary_denies_before_any_action(client, path, method, authorization):
    api, _, calls, jobs, _, root = client
    selected = headers()
    if authorization is None: selected.pop("Authorization")
    else: selected["Authorization"] = authorization
    response = getattr(api, method)("/api/admin/aurion-native-auth/" + path, headers=selected)
    assert response.status_code == 401
    assert calls == jobs == [] and list(root.iterdir()) == []


def test_busy_worker_does_not_cancel_approved_job(client, monkeypatch):
    api, _, _, jobs, _, root = client
    preview = plan(api)
    response = api.post("/api/admin/aurion-native-auth/approve", json={"expectedRevision": "a" * 40,
        "planHash": preview["planHash"]}, headers=headers())
    identifier = response.json["requestId"]
    queue = HostCommandQueueClient(str(root / "queue"))
    # Advance beyond the former one-second timeout with no worker available.
    monkeypatch.setattr("command_queue.time.monotonic", lambda: 1000000)
    assert queue.status(identifier)["status"] == "QUEUED"
    assert (queue.inbox / (identifier + ".json")).is_file()
    assert len(jobs) == 1
    (queue.inbox / (identifier + ".json")).rename(queue.processing / (identifier + ".json"))
    assert queue.status(identifier)["status"] == "IN_PROGRESS"
    assert len(jobs) == 1


def test_lost_enqueue_response_remains_uncertain_and_never_resubmits(client, monkeypatch):
    api, _, _, jobs, _, root = client
    preview = plan(api)
    original = routes.HostCommandQueueClient.enqueue
    def uncertain(self, action, arguments):
        queued = original(self, action, arguments)
        (self.inbox / (queued["request_id"] + ".json")).rename(self.processing / (queued["request_id"] + ".json"))
        raise TimeoutError("SYNTHETIC_QUEUE_SECRET")
    monkeypatch.setattr(routes.HostCommandQueueClient, "enqueue", uncertain)
    response = api.post("/api/admin/aurion-native-auth/approve", json={"expectedRevision": "a" * 40,
        "planHash": preview["planHash"]}, headers=headers())
    assert response.status_code == 202
    assert response.json["status"] == "QUEUE_OUTCOME_UNCERTAIN"
    assert "SYNTHETIC_QUEUE_SECRET" not in response.text
    assert len(jobs) == 1 and len(list((root / "queue/processing").glob("*.json"))) == 1
    operation = response.json["operationId"]
    assert api.get("/api/admin/aurion-native-auth/readback/" + operation, headers=headers()).status_code == 200
    assert len(jobs) == 1


@pytest.mark.parametrize("blocker,expected", [
    ("SCHEMA_MISMATCH", "SCHEMA_MISMATCH"),
    ("NATIVE_AUTH_PRIVATE_OPERATOR_REQUIRED", "NATIVE_AUTH_PRIVATE_OPERATOR_REQUIRED"),
    ("SYNTHETIC_SECRET_BODY", "NATIVE_AUTH_PLAN_UNAVAILABLE"),
    ("SCHEMA_MISMATCH SYNTHETIC_SECRET_BODY", "NATIVE_AUTH_PLAN_UNAVAILABLE"),
    ({"secret": "SYNTHETIC_SECRET_BODY"}, "NATIVE_AUTH_PLAN_UNAVAILABLE"),
])
def test_plan_preserves_only_exact_diagnostic_codes(client, monkeypatch, caplog, blocker, expected):
    api, _, _, jobs, _, root = client
    monkeypatch.setattr(routes, "_broker_call", lambda *a, **k:
        {"ok": False, "status": "BLOCKED", "blocker": blocker, "detail": "SYNTHETIC_SECRET_BODY"})
    response = api.post("/api/admin/aurion-native-auth/plan",
        json={"expectedRevision": "a" * 40}, headers=headers())
    assert response.status_code == 409 and response.json == {"error": expected}
    assert "SYNTHETIC_SECRET_BODY" not in response.text + caplog.text
    assert jobs == [] and list(root.iterdir()) == []


@pytest.mark.parametrize("family,expected", [
    ("BROKER_RPC_TIMEOUT", "BROKER_RPC_TIMEOUT"),
    ("SYNTHETIC_SECRET_TRANSPORT", "NATIVE_AUTH_PLAN_UNAVAILABLE"),
])
def test_transport_family_is_allowlisted_without_details(client, monkeypatch, caplog, family, expected):
    api, _, _, jobs, _, root = client
    def fail(*args, **kwargs):
        raise routes.ReceiptIdentityBlocked(family, "SYNTHETIC_SECRET_TRANSPORT")
    monkeypatch.setattr(routes, "_broker_call", fail)
    response = api.post("/api/admin/aurion-native-auth/plan",
        json={"expectedRevision": "a" * 40}, headers=headers())
    assert response.status_code == 409 and response.json == {"error": expected}
    assert "SYNTHETIC_SECRET_TRANSPORT" not in response.text + caplog.text
    assert jobs == [] and list(root.iterdir()) == []
