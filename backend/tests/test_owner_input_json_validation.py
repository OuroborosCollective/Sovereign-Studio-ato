from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_BACKEND = ROOT / "scripts" / "sovereign-backend"
if str(SCRIPTS_BACKEND) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_BACKEND))


class MockResponse(dict):
    def __init__(self, data):
        super().__init__(data if isinstance(data, dict) else {"data": data})
        self.headers = {}


def _build_stubs():
    stubs = {}

    if "flask" not in sys.modules:
        flask_stub = ModuleType("flask")
        flask_stub.jsonify = lambda value=None, **kwargs: MockResponse(value if value is not None else kwargs)
        flask_stub.make_response = lambda response: response
        flask_stub.request = SimpleNamespace()
        stubs["flask"] = flask_stub
    else:
        flask_mod = sys.modules["flask"]
        if not hasattr(flask_mod, "make_response"):
            setattr(flask_mod, "make_response", lambda response: response)

    if "cryptography" not in sys.modules:
        stubs["cryptography"] = ModuleType("cryptography")
        stubs["cryptography.hazmat"] = ModuleType("cryptography.hazmat")

        primitives_stub = ModuleType("cryptography.hazmat.primitives")
        primitives_stub.hashes = SimpleNamespace(SHA256=lambda: None)
        primitives_stub.serialization = SimpleNamespace(Encoding=SimpleNamespace(Raw=None), PublicFormat=SimpleNamespace(Raw=None))
        stubs["cryptography.hazmat.primitives"] = primitives_stub

        stubs["cryptography.hazmat.primitives.asymmetric"] = ModuleType("cryptography.hazmat.primitives.asymmetric")

        x25519_stub = ModuleType("cryptography.hazmat.primitives.asymmetric.x25519")
        x25519_stub.X25519PrivateKey = SimpleNamespace()
        x25519_stub.X25519PublicKey = SimpleNamespace()
        stubs["cryptography.hazmat.primitives.asymmetric.x25519"] = x25519_stub

        stubs["cryptography.hazmat.primitives.ciphers"] = ModuleType("cryptography.hazmat.primitives.ciphers")

        aead_stub = ModuleType("cryptography.hazmat.primitives.ciphers.aead")
        aead_stub.AESGCM = SimpleNamespace()
        stubs["cryptography.hazmat.primitives.ciphers.aead"] = aead_stub

        stubs["cryptography.hazmat.primitives.kdf"] = ModuleType("cryptography.hazmat.primitives.kdf")

        hkdf_stub = ModuleType("cryptography.hazmat.primitives.kdf.hkdf")
        hkdf_stub.HKDF = SimpleNamespace()
        stubs["cryptography.hazmat.primitives.kdf.hkdf"] = hkdf_stub

    if "freellm_provider_credentials" not in sys.modules:
        freellm_stub = ModuleType("freellm_provider_credentials")
        freellm_stub.FREELLM_PROVIDER_SPECS = {}
        freellm_stub.FREELLM_RUNTIME_GID = 1000
        freellm_stub.FREELLM_RUNTIME_UID = 1000
        freellm_stub.provider_secret_path = lambda root, pid: root / f"{pid}.txt"
        freellm_stub.provider_target_id = lambda pid: pid
        stubs["freellm_provider_credentials"] = freellm_stub

    return stubs


class MockApp:
    def __init__(self):
        self.routes = {}

    def route(self, rule, **options):
        def decorator(func):
            self.routes[rule] = func
            return func
        return decorator


class TestOwnerInputJsonValidation(unittest.TestCase):
    def setUp(self):
        self.stubs = _build_stubs()
        self.patcher = patch.dict("sys.modules", self.stubs)
        self.patcher.start()

        import owner_input_runtime
        self.owner_input_runtime = owner_input_runtime

        self.old_request = owner_input_runtime.request
        owner_input_runtime.request = SimpleNamespace(headers={}, get_json=lambda *args, **kwargs: {})

        self.old_jsonify = owner_input_runtime.jsonify
        owner_input_runtime.jsonify = lambda value=None, **kwargs: MockResponse(value if value is not None else kwargs)

        self.old_service_authorized = owner_input_runtime._service_authorized
        owner_input_runtime._service_authorized = lambda: True

        self.app = MockApp()
        owner_input_runtime.register_owner_input_routes(
            self.app,
            require_admin=lambda f: f,
            get_connection=lambda: None,
            get_current_admin=lambda: {},
        )

    def tearDown(self):
        if self.old_request is not None:
            self.owner_input_runtime.request = self.old_request
        if self.old_jsonify is not None:
            self.owner_input_runtime.jsonify = self.old_jsonify
        self.owner_input_runtime._service_authorized = self.old_service_authorized
        self.patcher.stop()

    def test_owner_input_non_dict_payloads_rejected_safely(self):
        endpoint = "/api/internal/owner-input/requests"
        malformed_bodies = [
            [],                      # JSON list
            [1, 2, 3],               # JSON list with elements
            "string_payload",        # JSON string
            12345,                   # JSON integer
            None,                    # JSON null
            True,                    # JSON boolean
        ]

        handler = self.app.routes.get(endpoint)
        self.assertTrue(callable(handler), f"Handler not registered for path {endpoint}")

        for malformed in malformed_bodies:
            self.owner_input_runtime.request.get_json = lambda *args, **kwargs: malformed

            res = handler()

            self.assertIsInstance(res, tuple, f"Endpoint {endpoint} did not return status code tuple for {malformed}")
            response_body, status_code = res
            self.assertEqual(status_code, 400, f"Endpoint {endpoint} failed to reject non-dict body {malformed}")
            self.assertIn("error", response_body)
            self.assertEqual(response_body["error"], "Malformed payload; dictionary required")


if __name__ == "__main__":
    unittest.main()
