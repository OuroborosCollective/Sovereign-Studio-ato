from __future__ import annotations

from functools import wraps
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

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

if "requests" not in sys.modules:
    sys.modules["requests"] = ModuleType("requests")

import proven_learning_runtime

# proven_learning_runtime binds flask.jsonify/request at import time
# (`from flask import jsonify, request`). Patch those bound module names
# directly instead of mutating the shared flask module, so the tests work
# regardless of whether a real Flask or the import stub was bound first in
# this pytest session.
proven_learning_runtime.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs)


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

    def close(self):
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


class TestProvenLearningValidationCrashes(unittest.TestCase):
    def setUp(self):
        self.old_request = proven_learning_runtime.request
        proven_learning_runtime.request = SimpleNamespace(headers={}, get_json=lambda *args, **kwargs: {})

        self.old_jsonify = proven_learning_runtime.jsonify
        proven_learning_runtime.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs)

        # Mock service authorization to return True so route logic reaches payload processing
        self.old_service_authorized = proven_learning_runtime._service_authorized
        proven_learning_runtime._service_authorized = lambda: True

        self.app = MockApp()
        proven_learning_runtime.register_proven_learning_routes(
            self.app,
            get_connection=mock_get_connection,
        )

    def tearDown(self):
        if self.old_request is not None:
            proven_learning_runtime.request = self.old_request
        if self.old_jsonify is not None:
            proven_learning_runtime.jsonify = self.old_jsonify
        proven_learning_runtime._service_authorized = self.old_service_authorized

    def test_non_dict_payloads_rejected_safely(self):
        endpoints = [
            "/api/internal/proven-learning/plan",
            "/api/internal/proven-learning/apply",
        ]

        malformed_bodies = [
            [],                      # JSON list
            [1, 2, 3],               # JSON list with elements
            "string_payload",        # JSON string
            12345,                   # JSON integer
            None,                    # JSON null
            True,                    # JSON boolean
        ]

        for path in endpoints:
            handler = self.app.routes.get(path)
            self.assertTrue(callable(handler), f"Handler not registered for path {path}")

            for malformed in malformed_bodies:
                proven_learning_runtime.request.get_json = lambda *args, **kwargs: malformed

                res = handler()

                self.assertIsInstance(res, tuple, f"Endpoint {path} did not return status code tuple for {malformed}")
                response_body, status_code = res
                self.assertEqual(status_code, 400, f"Endpoint {path} failed to reject non-dict body {malformed}")
                self.assertIn("error", response_body)
                self.assertEqual(response_body["error"], "Malformed payload; dictionary required")


if __name__ == "__main__":
    unittest.main()
