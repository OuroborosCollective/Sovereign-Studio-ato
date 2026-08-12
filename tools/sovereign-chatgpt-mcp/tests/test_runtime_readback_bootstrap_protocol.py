from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
ENTRYPOINT = ROOT / "deploy/run-coordinated-release-readback.py"
BOOTSTRAP_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/sovereign-release-readback-bootstrap.yml"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("runtime_readback_bootstrap_protocol", ENTRYPOINT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _scope() -> dict[str, object]:
    return {
        "revision": "a" * 40,
        "releaseGateRunId": 123456,
        "backendDigest": "sha256:" + "b" * 64,
        "mcpDigest": "sha256:" + "c" * 64,
        "manifestEvidenceSha256": "d" * 64,
    }


def _stdin(payload: bytes) -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8")


class RuntimeReadbackBootstrapProtocolTests(unittest.TestCase):
    def test_forced_readback_accepts_legacy_two_line_framing(self) -> None:
        module = _load_entrypoint()
        token = "ghs_ephemeral_runtime_token_abcdefghijklmnopqrstuvwxyz"
        payload = json.dumps(_scope(), separators=(",", ":")).encode() + b"\n" + token.encode() + b"\n"
        with patch.object(sys, "stdin", _stdin(payload)):
            scope, observed_token, username = module._read_input()
        self.assertEqual(scope["revision"], "a" * 40)
        self.assertEqual(observed_token, token)
        self.assertEqual(username, "OuroborosCollective")

    def test_forced_readback_accepts_current_three_line_framing(self) -> None:
        module = _load_entrypoint()
        token = "ghs_ephemeral_runtime_token_abcdefghijklmnopqrstuvwxyz"
        payload = (
            json.dumps(_scope(), separators=(",", ":")).encode()
            + b"\n"
            + token.encode()
            + b"\nOuroborosCollective\n"
        )
        with patch.object(sys, "stdin", _stdin(payload)):
            _scope_value, observed_token, username = module._read_input()
        self.assertEqual(observed_token, token)
        self.assertEqual(username, "OuroborosCollective")

    def test_forced_readback_rejects_unbounded_extra_framing(self) -> None:
        module = _load_entrypoint()
        token = "ghs_ephemeral_runtime_token_abcdefghijklmnopqrstuvwxyz"
        payload = (
            json.dumps(_scope(), separators=(",", ":")).encode()
            + b"\n"
            + token.encode()
            + b"\nOuroborosCollective\nunexpected\n"
        )
        with patch.object(sys, "stdin", _stdin(payload)):
            with self.assertRaisesRegex(module.ReadbackError, "input framing is invalid"):
                module._read_input()

    def test_target_reconcile_environment_binds_canonical_backend_repository(self) -> None:
        module = _load_entrypoint()
        source = ENTRYPOINT.read_text("utf-8")
        self.assertEqual(
            module.BACKEND_IMAGE_REPOSITORY,
            "ghcr.io/ouroboroscollective/sovereign-backend",
        )
        self.assertRegex(module.BACKEND_IMAGE_REPOSITORY, module.IMAGE_REPOSITORY_RE)
        self.assertIn(
            '"SOVEREIGN_BACKEND_IMAGE_REPOSITORY": BACKEND_IMAGE_REPOSITORY',
            source,
        )
        self.assertIn('"SOVEREIGN_EXPECTED_BACKEND_DIGEST": scope["backendDigest"]', source)
        self.assertIn('"SOVEREIGN_EXPECTED_MCP_DIGEST": scope["mcpDigest"]', source)
        self.assertIn(
            '"SOVEREIGN_EXPECTED_MANIFEST_EVIDENCE_SHA256": scope["manifestEvidenceSha256"]',
            source,
        )
        self.assertNotIn('SOVEREIGN_BACKEND_IMAGE_REPOSITORY": "latest"', source)

    def test_control_plane_bootstrap_is_exact_main_path_scoped_hash_bound_and_container_free(self) -> None:
        workflow = BOOTSTRAP_WORKFLOW.read_text("utf-8")
        self.assertIn("push:", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn("tools/sovereign-chatgpt-mcp/deploy/run-coordinated-release-readback.py", workflow)
        self.assertIn(".github/workflows/sovereign-release-readback-bootstrap.yml", workflow)
        self.assertIn(
            "EXPECTED_REVISION: ${{ github.event_name == 'workflow_dispatch' && inputs.expected_revision || github.sha }}",
            workflow,
        )
        self.assertIn("SOURCE_REVISION_IS_NOT_CURRENT_MAIN", workflow)
        self.assertIn("KNOWN_PREVIOUS_REVISION: 738c0ac6616b2b2fadfd554706ac678c90e80e7a", workflow)
        self.assertIn("UNEXPECTED_READBACK_ENTRYPOINT_HASH", workflow)
        self.assertIn("/opt/sovereign-chatgpt-tools/bin/run-coordinated-release-readback", workflow)
        self.assertIn("containersChanged': False", workflow)
        self.assertIn("servicesRestarted': False", workflow)
        self.assertIn("authorizedKeysChanged': False", workflow)
        self.assertIn("capture_stdout: true", workflow)
        self.assertIn("RECEIPT_HEX: ${{ steps.receipt.outputs.stdout }}", workflow)
        self.assertIn("print(payload.hex())", workflow)
        self.assertIn("raw = bytes.fromhex(encoded)", workflow)
        self.assertNotIn("RECEIPT_BASE64:", workflow)
        self.assertNotIn("base64.b64decode", workflow)
        self.assertNotIn("source: .sovereign-release-readback-bootstrap/bootstrap-receipt.json", workflow)
        self.assertNotIn("deploy/install-on-vps.sh", workflow)
        self.assertNotIn("docker restart", workflow)
        self.assertNotIn("docker run", workflow)
        self.assertNotIn("systemctl restart", workflow)
        self.assertNotIn("packages: write", workflow)
        self.assertNotIn("deployments: write", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
