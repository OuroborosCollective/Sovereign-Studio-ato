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
    flask_stub.request = SimpleNamespace()
    sys.modules["flask"] = flask_stub

import flask  # noqa: F401

if "psycopg2" not in sys.modules:
    psycopg2_stub = ModuleType("psycopg2")
    psycopg2_extras_stub = ModuleType("psycopg2.extras")
    psycopg2_stub.extras = psycopg2_extras_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub

import knowledge_library

knowledge_library.request = SimpleNamespace(remote_addr="127.0.0.1", session_user_id=str(uuid.uuid4()))
knowledge_library.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs)


def mock_require_session(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        knowledge_library.request.session_user_id = str(uuid.uuid4())
        return func(*args, **kwargs)
    return wrapper


def mock_require_admin(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        knowledge_library.request.session_user_id = str(uuid.uuid4())
        return func(*args, **kwargs)
    return wrapper


def mock_get_connection():
    return None


def mock_get_admin_user_id():
    return str(uuid.uuid4())


class MockApp:
    def __init__(self):
        self.routes = {}

    def route(self, rule, **options):
        def decorator(func):
            self.routes[rule] = func
            return func
        return decorator


class TestKnowledgeJsonValidation(unittest.TestCase):
    def setUp(self):
        self.old_jsonify = knowledge_library.jsonify
        knowledge_library.jsonify = lambda value=None, **kwargs: (value if value is not None else kwargs)

        self.app = MockApp()
        knowledge_library.register_knowledge_routes(
            self.app,
            require_session=mock_require_session,
            get_connection=mock_get_connection,
        )
        knowledge_library.register_admin_knowledge_routes(
            self.app,
            require_admin=mock_require_admin,
            get_connection=mock_get_connection,
            get_admin_user_id=mock_get_admin_user_id,
        )

    def tearDown(self):
        if self.old_jsonify is not None:
            knowledge_library.jsonify = self.old_jsonify

    def test_knowledge_non_dict_payloads_rejected_safely(self):
        endpoints = [
            "/api/knowledge/sources/url",
            "/api/knowledge/sources/upload-ticket",
            "/api/knowledge/sources/upload-confirm",
            "/api/knowledge/search",
            "/api/admin/knowledge/sources/url",
            "/api/admin/knowledge/repair",
            "/api/admin/knowledge/search",
        ]

        malformed_bodies = [
            [],                      # JSON list
            [1, 2, 3],               # JSON list with elements
            "string_payload",        # JSON string
            12345,                   # JSON integer
            True,                    # JSON boolean
            None,                    # JSON null
        ]

        for path in endpoints:
            handler = self.app.routes.get(path)
            self.assertTrue(callable(handler), f"Handler not registered for path {path}")

            for malformed in malformed_bodies:
                knowledge_library.request.get_json = lambda *args, **kwargs: malformed

                res = handler()

                self.assertIsInstance(res, tuple, f"Endpoint {path} did not return status code tuple for {malformed}")
                response_body, status_code = res
                self.assertEqual(status_code, 400, f"Endpoint {path} failed to reject non-dict body {malformed}")
                self.assertIn("error", response_body)
                self.assertEqual(response_body["error"], "Malformed payload; dictionary required")


if __name__ == "__main__":
    unittest.main()
