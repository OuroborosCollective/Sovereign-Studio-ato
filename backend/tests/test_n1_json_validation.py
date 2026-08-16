from __future__ import annotations

from functools import wraps
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# Make sure "flask" stub or module exists in sys.modules
if "flask" not in sys.modules:
    flask_stub = ModuleType("flask")
    flask_stub.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs)
    flask_stub.Response = lambda *args, **kwargs: args
    flask_stub.request = SimpleNamespace()
    sys.modules["flask"] = flask_stub

import flask
flask.request = SimpleNamespace(remote_addr="127.0.0.1", session_user_id=str(uuid.uuid4()))

# Stub requests and psycopg2 to avoid external runtime/C dependencies in isolation
if "requests" not in sys.modules:
    requests_stub = ModuleType("requests")
    requests_stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

if "psycopg2" not in sys.modules:
    psycopg2_stub = ModuleType("psycopg2")
    psycopg2_extras_stub = ModuleType("psycopg2.extras")
    psycopg2_extras_stub.Json = lambda x: x
    psycopg2_stub.extras = psycopg2_extras_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub

from n_plus_one import routes as n1_routes


def mock_require_session(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        flask.request.session_user_id = str(uuid.uuid4())
        return func(*args, **kwargs)
    return wrapper


def mock_require_admin(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        flask.request.session_user_id = str(uuid.uuid4())
        return func(*args, **kwargs)
    return wrapper


def mock_query(*args, **kwargs):
    return None


def mock_audit(*args, **kwargs):
    pass


class MockApp:
    def __init__(self):
        self.routes = {}

    def route(self, rule, **options):
        def decorator(func):
            self.routes[rule] = func
            return func
        return decorator


class TestN1JsonValidation(unittest.TestCase):
    def setUp(self):
        self.old_jsonify = getattr(flask, "jsonify", None)
        flask.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs, 400)

        self.app = MockApp()
        n1_routes.register_n_plus_one_routes(
            self.app,
            require_session=mock_require_session,
            require_admin=mock_require_admin,
            query=mock_query,
            audit=mock_audit,
        )

    def tearDown(self):
        if self.old_jsonify is not None:
            flask.jsonify = self.old_jsonify

    def test_n1_non_dict_payloads_rejected_safely(self):
        endpoints = [
            "/api/n-plus-one/voice/synthesize",
            "/api/n-plus-one/learning-candidates",
            "/api/n-plus-one/linguistic/observe",
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
                flask.request.get_json = lambda *args, **kwargs: malformed

                res = handler()

                self.assertIsInstance(res, tuple, f"Endpoint {path} did not return status code tuple for {malformed}")
                response_body, status_code = res
                self.assertEqual(status_code, 400, f"Endpoint {path} failed to reject non-dict body {malformed}")
                self.assertIn("error", response_body)
                self.assertEqual(response_body["error"], "Malformed payload; dictionary required")


if __name__ == "__main__":
    unittest.main()
