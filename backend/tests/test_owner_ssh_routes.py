"""Exercise the real Flask owner routes; auth/queue/filesystem are external adapters."""
from pathlib import Path
import json
import os
import sys
from types import SimpleNamespace
import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/sovereign-backend"))
import owner_ssh_routes as routes

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_ID", "configured-owner")
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    current = {"id": "configured-owner"}
    writes, jobs = [], []
    def atomic(target, content):
        writes.append((dict(target), json.loads(bytes(content))))
    monkeypatch.setattr(routes, "_atomic_write", atomic)
    class Queue:
        def submit(self, action, arguments, **kwargs):
            jobs.append((action, arguments))
            return {"ok": True, "status": "SSH_CONNECTED", "sessionId": "a" * 32}
        def status(self, request_id):
            return {"ok": True, "status": "SSH_INSPECTION_COMPLETE"}
    monkeypatch.setattr(routes, "HostCommandQueueClient", Queue)
    monkeypatch.setattr(routes, "_broker_call", lambda *a, **k: {"ok": True, "status": "SSH_NOT_CONNECTED"})
    app = Flask(__name__)
    routes.register_owner_ssh_routes(app, require_admin=lambda fn: fn,
                                     get_current_admin=lambda: current)
    return app.test_client(), current, writes, jobs

def headers(origin="https://sovereign-backend.arelorian.de"):
    return {"X-Sovereign-Owner-Action": "ssh-console", "Origin": origin}

def test_owner_and_cross_origin_boundary(client):
    api, current, writes, jobs = client
    current["id"] = "different-owner"
    assert api.get("/api/admin/owner-ssh/status").status_code == 403
    assert api.post("/api/admin/owner-ssh/action", json={"action": "close"}, headers=headers()).status_code == 403
    current["id"] = "configured-owner"
    assert api.post("/api/admin/owner-ssh/action", json={"action": "close"}, headers=headers("https://different.invalid")).status_code == 403
    assert api.post("/api/admin/owner-ssh/action", json={"action": "close"}).status_code == 403
    assert writes == [] and jobs == []

def test_queue_accepts_metadata_only_and_owner_receipt(client):
    api, current, writes, jobs = client
    response = api.post("/api/admin/owner-ssh/action",
                        json={"action": "grant", "sessionId": "a" * 32, "operations": ["disk"], "ttl": 30},
                        headers=headers())
    assert response.status_code == 200
    assert jobs[0][0] == "ssh_console_owner_action"
    assert set(jobs[0][1]) == {"operation_id"}
    target, record = writes[0]
    assert target["ownerUid"] == target["ownerGid"] == 0
    assert target["kind"] == "root_owned_credential"
    assert record["sessionId"] == "a" * 32 and record["operations"] == ["disk"]
    assert record["operationId"] == jobs[0][1]["operation_id"]

@pytest.mark.parametrize("body", [
    {"action": "shell", "command": "synthetic-command"},
    {"action": "grant", "sessionId": "a" * 32, "operations": ["shell"], "ttl": 30},
    {"action": "grant", "sessionId": "a" * 32, "operations": ["disk"], "ttl": 10000},
    {"action": "inspect", "sessionId": "../invalid", "operation": "disk"},
    {"action": "connect", "profile": {"host": "localhost"}},
])
def test_invalid_owner_actions_never_enter_queue(client, body):
    api, current, writes, jobs = client
    response = api.post("/api/admin/owner-ssh/action", json=body, headers=headers())
    assert response.status_code == 400 and writes == [] and jobs == []
    assert "profile" not in response.get_data(as_text=True)

def test_explicit_shell_grant_is_owner_scoped_and_metadata_only(client):
    api, current, writes, jobs = client
    response = api.post("/api/admin/owner-ssh/action", json={
        "action": "grant", "sessionId": "a" * 32, "operations": ["shell"], "ttl": 300
    }, headers=headers())
    assert response.status_code == 200
    assert writes[0][1]["operations"] == ["shell"]
    assert set(jobs[0][1]) == {"operation_id"}
    assert "command" not in str(jobs)


def test_async_action_is_reported_without_resubmission(client, monkeypatch):
    api, current, writes, jobs = client
    class Queue:
        def submit(self, action, arguments, **kwargs):
            return {"ok": False, "status": "IN_PROGRESS", "request_id": "b" * 32}
    monkeypatch.setattr(routes, "HostCommandQueueClient", Queue)
    response = api.post("/api/admin/owner-ssh/action", json={"action": "close", "sessionId": "a" * 32}, headers=headers())
    assert response.status_code == 200
    assert response.json["status"] == "IN_PROGRESS"

def test_owner_page_is_protected_from_embedding_and_storage(client):
    api, *_ = client
    response = api.get("/owner-ssh")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "no-store" in response.headers["Cache-Control"]
    assert "localStorage" not in response.get_data(as_text=True)

def test_probe_is_owner_guarded_and_contains_no_credential(client):
    api, current, writes, jobs = client
    response = api.post("/api/admin/owner-ssh/action",
        json={"action": "probe", "host": "8.8.8.8", "port": 22}, headers=headers())
    assert response.status_code == 200
    assert jobs[0][0] == "ssh_console_owner_action"
    assert set(jobs[0][1]) == {"operation_id"}
    target, record = writes[0]
    assert record["action"] == "probe"
    assert record["host"] == "8.8.8.8" and record["port"] == 22
    assert "password" not in record and "privateKey" not in record
    assert "sessionId" not in record and "profileSha256" not in record


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "169.254.169.254"])
def test_probe_rejects_non_public_host_before_queue(client, host):
    api, current, writes, jobs = client
    response = api.post("/api/admin/owner-ssh/action",
        json={"action": "probe", "host": host, "port": 22}, headers=headers())
    assert response.status_code == 400
    assert writes == [] and jobs == []


def test_password_first_page_has_host_identity_confirmation(client):
    api, *_ = client
    page = api.get("/owner-ssh").get_data(as_text=True)
    assert '<option value="password" selected>' in page
    assert 'id="probeHost"' in page and 'id="hostConfirmed"' in page
    assert "ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub" in page
    assert "knownHostKey:$('hostKey')" not in page


def test_workspace_grant_is_one_owner_action_for_15_to_60_minutes(client):
    api, current, writes, jobs = client
    for ttl in (900, 1800, 3600):
        response = api.post('/api/admin/owner-ssh/action', json={'action':'grant','sessionId':'a'*32,
                            'operations':['workspace'],'ttl':ttl}, headers=headers())
        assert response.status_code == 200
        assert writes[-1][1]['operations'] == ['workspace'] and writes[-1][1]['ttl'] == ttl
        assert set(jobs[-1][1]) == {'operation_id'}
    for ttl in (30, 899, 3601, True):
        assert api.post('/api/admin/owner-ssh/action', json={'action':'grant','sessionId':'a'*32,
                        'operations':['workspace'],'ttl':ttl}, headers=headers()).status_code == 400


def test_revoke_persists_immediate_marker_before_queue(client):
    api, current, writes, jobs = client
    response = api.post('/api/admin/owner-ssh/action', json={'action':'revoke','sessionId':'a'*32}, headers=headers())
    assert response.status_code == 200
    assert writes[0][0]['path'].name == 'ssh_console_revocation.json'
    assert writes[0][1]['sessionId'] == 'a'*32 and 'at' in writes[0][1]
    assert writes[1][0]['path'].name == 'ssh_console_action.json'
