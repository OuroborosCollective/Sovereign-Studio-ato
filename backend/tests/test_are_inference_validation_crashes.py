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

# Stub flask if not already present
if "flask" not in sys.modules:
    flask_stub = ModuleType("flask")
    flask_stub.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs)
    flask_stub.make_response = lambda response: response
    flask_stub.request = SimpleNamespace()
    sys.modules["flask"] = flask_stub

import flask
try:
    if not hasattr(flask.request, "remote_addr"):
        flask.request.remote_addr = "127.0.0.1"
except RuntimeError:
    # Real flask proxy without context, ignore during collection
    pass

# Stub psycopg2 to avoid external C dependencies
if "psycopg2" not in sys.modules:
    psycopg2_stub = ModuleType("psycopg2")
    psycopg2_extras_stub = ModuleType("psycopg2.extras")
    psycopg2_stub.extras = psycopg2_extras_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub

import are_inference


def mock_require_session(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        flask.request.session_user_id = str(uuid.uuid4())
        return func(*args, **kwargs)
    return wrapper


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


class TestAreInferenceValidationCrashes(unittest.TestCase):
    def setUp(self):
        self.old_jsonify = getattr(flask, "jsonify", None)
        flask.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs, 400)

        self.app = MockApp()
        are_inference.register_are_inference_routes(
            self.app,
            require_session=mock_require_session,
            get_connection=mock_get_connection,
        )

    def tearDown(self):
        if self.old_jsonify is not None:
            flask.jsonify = self.old_jsonify

    def test_non_dict_payloads_rejected_safely(self):
        # List of endpoints that parse JSON body using request.get_json
        endpoints = [
            "/api/inference/are/evaluate",
            "/api/inference/are/repair",
            "/api/inference/are/quarantine",
            "/api/inference/are/quarantine/<candidate_id>/promote",
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
                # Set up mock request body directly on the global flask.request
                flask.request.get_json = lambda *args, **kwargs: malformed

                if path == "/api/inference/are/quarantine/<candidate_id>/promote":
                    res = handler(candidate_id=str(uuid.uuid4()))
                else:
                    res = handler()

                # Check that we received a tuple representing a response and the 400 status code
                self.assertIsInstance(res, tuple, f"Endpoint {path} did not return status code tuple for {malformed}")
                response_body, status_code = res
                self.assertEqual(status_code, 400, f"Endpoint {path} failed to reject non-dict body {malformed}")
                self.assertFalse(response_body["ok"])
                self.assertEqual(response_body["error"], "Malformed payload; dictionary required")


if __name__ == "__main__":
    unittest.main()
