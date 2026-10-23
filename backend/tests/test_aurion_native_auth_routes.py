"""Real Flask owner routes and protected state; external broker/queue adapters only."""
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/sovereign-backend"))
import aurion_native_auth_routes as routes
from aurion_native_auth import NativeAuthRepair, NativeAuthState


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
        return {"snapshot": snapshot, "planHash": "synthetic-non-authority"}
    monkeypatch.setattr(routes, "_broker_call", broker)
    class Queue:
        def submit(self, action, arguments, **kwargs):
            jobs.append((action, arguments))
            return {"request_id": "f" * 32, "status": "IN_PROGRESS"}
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
    routes.register_aurion_native_auth_routes(app, require_admin=lambda fn: fn, get_current_admin=lambda: current)
    return app.test_client(), current, calls, jobs, snapshot, tmp_path


def headers():
    return {"Origin": "https://sovereign-backend.arelorian.de", "X-Sovereign-Owner-Action": "aurion-native-auth"}


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
    record = NativeAuthState(root).read("approval", operation)
    assert record["plan"] == preview
    assert record["target"] == "echoes-of-aurion/aurion"
    assert len(calls) == 2  # independent fresh plan at approval
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
    current["id"] = "other"
    assert api.get("/owner-aurion-native-auth").status_code == 403
