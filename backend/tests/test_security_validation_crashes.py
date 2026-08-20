from __future__ import annotations

from functools import wraps
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
import uuid
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# Make sure "flask" stub or module exists in sys.modules
if "flask" not in sys.modules:
    flask_stub = ModuleType("flask")
    flask_stub.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs)
    flask_stub.make_response = lambda response: response
    flask_stub.request = SimpleNamespace()
    sys.modules["flask"] = flask_stub

import flask  # noqa: F401 - guarantees a flask module exists (stub installed above if missing)

# Stub psycopg2 to avoid external C dependencies
if "psycopg2" not in sys.modules:
    psycopg2_stub = ModuleType("psycopg2")
    psycopg2_extras_stub = ModuleType("psycopg2.extras")
    psycopg2_stub.extras = psycopg2_extras_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub

import security_runtime

# security_runtime binds flask.jsonify/request at import time
# (`from flask import jsonify, request`). Patch those bound module names
# directly instead of mutating the shared flask module, so the tests work
# regardless of whether a real Flask or the import stub was bound first in
# this pytest session.
security_runtime.request = SimpleNamespace(remote_addr="127.0.0.1")
security_runtime.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs)


def mock_require_session(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        security_runtime.request.session_user_id = str(uuid.uuid4())
        return func(*args, **kwargs)
    return wrapper


def mock_set_session_cookie(response, user_id):
    return response


class MockCursor:
    def execute(self, *args, **kwargs):
        pass

    def fetchone(self, *args, **kwargs):
        return None

    def fetchall(self, *args, **kwargs):
        return []


class MockConnection:
    def cursor(self):
        return MockCursor()

    def commit(self):
        pass

    def rollback(self):
        pass


def mock_get_connection():
    return MockConnection()


class MockApp:
    def __init__(self):
        self.routes = {}

    def route(self, rule, **options):
        def decorator(func):
            self.routes[rule] = func
            return func
        return decorator


class TestSecurityValidationCrashes(unittest.TestCase):
    def setUp(self):
        self.old_jsonify = security_runtime.jsonify
        security_runtime.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs)

        self.app = MockApp()
        security_runtime.register_security_routes(
            self.app,
            require_session=mock_require_session,
            get_connection=mock_get_connection,
            set_session_cookie=mock_set_session_cookie,
        )

    def tearDown(self):
        if self.old_jsonify is not None:
            security_runtime.jsonify = self.old_jsonify

    def test_non_dict_payloads_rejected_safely(self):
        # List of endpoints that parse JSON body using request.get_json
        endpoints = [
            "/api/security/policy",
            "/api/security/passkeys/register/verify",
            "/api/auth/passkey/options",
            "/api/auth/passkey/verify",
            "/api/security/account-keys",
            "/api/auth/account-key",
            "/api/security/step-up/options",
            "/api/security/step-up/verify",
            "/api/security/step-up/account-key",
        ]

        malformed_bodies = [
            [],                      # JSON list
            [1, 2, 3],               # JSON list with elements
            "string_payload",        # JSON string
            12345,                   # JSON integer
            None,                    # JSON null
        ]

        for path in endpoints:
            handler = self.app.routes.get(path)
            self.assertTrue(callable(handler), f"Handler not registered for path {path}")

            for malformed in malformed_bodies:
                # Set up mock request body directly on the module-bound request
                security_runtime.request.get_json = lambda *args, **kwargs: malformed

                # Call route handler and get the tuple/response returned by jsonify/Flask
                res = handler()

                # Check that we received a tuple representing a response and the 400 status code
                self.assertIsInstance(res, tuple, f"Endpoint {path} did not return status code tuple for {malformed}")
                response_body, status_code = res
                self.assertEqual(status_code, 400, f"Endpoint {path} failed to reject non-dict body {malformed}")
                self.assertIn("error", response_body)
                self.assertEqual(response_body["error"], "Malformed payload; dictionary required")

    def test_unexpected_exceptions_fail_safely_with_generic_errors(self):
        # Verify that unexpected exceptions in passkey/step-up verify routes return generic errors instead of leaking stack traces
        handler = self.app.routes.get("/api/security/passkeys/register/verify")
        security_runtime.request.get_json = lambda *args, **kwargs: {"challengeId": "invalid-uuid", "credential": {}}

        # Mock _webauthn to return dummy functions so execution reaches challenge/credential verification logic
        old_webauthn = security_runtime._webauthn
        security_runtime._webauthn = lambda: {
            "verify_registration_response": lambda **kwargs: None,
            "verify_authentication_response": lambda **kwargs: None,
            "base64url_to_bytes": lambda s: b"bytes",
        }
        try:
            res = handler()
            self.assertIsInstance(res, tuple)
            response_body, status_code = res
            self.assertEqual(status_code, 400)
            self.assertIn("error", response_body)
            # Should be generic message or expected validation error, not an unhandled raw traceback leakage
            self.assertIn(response_body["error"], [
                "Security challenge is invalid, expired or already used",
                "Passkey registration failed",
                "Passkey backend dependency 'webauthn' is not installed",
            ])
        finally:
            security_runtime._webauthn = old_webauthn


if __name__ == "__main__":
    unittest.main()
