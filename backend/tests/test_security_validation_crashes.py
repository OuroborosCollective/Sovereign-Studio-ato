"""
Unit tests for security runtime request payload type validation.
Ensures non-dictionary JSON payloads are rejected with HTTP 400 instead of crashing the server with unhandled exceptions.
"""

import sys
import os
import pytest
from flask import Flask, request, jsonify

# Add backend to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security_runtime import register_security_routes

class FakeConnection:
    def cursor(self):
        return self
    def execute(self, *args, **kwargs):
        pass
    def fetchone(self):
        return None
    def fetchall(self):
        return []
    def commit(self):
        pass
    def rollback(self):
        pass
    def close(self):
        pass

def create_test_app():
    app = Flask(__name__)
    app.config["TESTING"] = True

    def require_session(fn):
        def wrapped(*args, **kwargs):
            request.session_user_id = "test-user-id"
            return fn(*args, **kwargs)
        wrapped.__name__ = fn.__name__
        return wrapped

    def dummy_set_cookie(response, user_id):
        return response

    register_security_routes(
        app,
        require_session=require_session,
        get_connection=lambda: FakeConnection(),
        set_session_cookie=dummy_set_cookie,
    )
    return app

def test_policy_update_invalid_json():
    app = create_test_app()
    client = app.test_client()
    response = client.patch("/api/security/policy", json=["invalid", "list"])
    assert response.status_code == 400
    assert response.json["error"] == "Payload must be a dictionary"

def test_passkey_register_verify_invalid_json():
    app = create_test_app()
    client = app.test_client()
    response = client.post("/api/security/passkeys/register/verify", json=["invalid"])
    assert response.status_code == 400
    assert response.json["error"] == "Payload must be a dictionary"

def test_passkey_login_options_invalid_json():
    app = create_test_app()
    client = app.test_client()
    response = client.post("/api/auth/passkey/options", json="string_not_dict")
    assert response.status_code == 400
    assert response.json["error"] == "Payload must be a dictionary"

def test_passkey_login_verify_invalid_json():
    app = create_test_app()
    client = app.test_client()
    response = client.post("/api/auth/passkey/verify", json=1234)
    assert response.status_code == 400
    assert response.json["error"] == "Payload must be a dictionary"

def test_account_key_create_invalid_json():
    app = create_test_app()
    client = app.test_client()
    response = client.post("/api/security/account-keys", json=["list"])
    assert response.status_code == 400
    assert response.json["error"] == "Payload must be a dictionary"

def test_account_key_login_invalid_json():
    app = create_test_app()
    client = app.test_client()
    response = client.post("/api/auth/account-key", json=["list"])
    assert response.status_code == 400
    assert response.json["error"] == "Payload must be a dictionary"

def test_step_up_options_invalid_json():
    app = create_test_app()
    client = app.test_client()
    response = client.post("/api/security/step-up/options", json=["list"])
    assert response.status_code == 400
    assert response.json["error"] == "Payload must be a dictionary"

def test_step_up_verify_invalid_json():
    app = create_test_app()
    client = app.test_client()
    response = client.post("/api/security/step-up/verify", json=["list"])
    assert response.status_code == 400
    assert response.json["error"] == "Payload must be a dictionary"

def test_step_up_account_key_invalid_json():
    app = create_test_app()
    client = app.test_client()
    response = client.post("/api/security/step-up/account-key", json=["list"])
    assert response.status_code == 400
    assert response.json["error"] == "Payload must be a dictionary"
