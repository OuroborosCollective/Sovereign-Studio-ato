from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import sys
import tempfile
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


def _receipt_markers(stdout: str) -> list[str]:
    return re.findall(r"SOVEREIGN_BOOTSTRAP_RECEIPT_HEX=([0-9a-fA-F]+)", stdout)


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

    def test_forced_readback_treats_signed_failure_receipt_as_transport_success(self) -> None:
        module = _load_entrypoint()
        scope = _scope()
        receipt = json.dumps(
            {
                "schemaVersion": "sovereign.coordinated-release-reconciler-status.v1",
                "ok": False,
                "status": "MCP_UPDATE_FAILED_BACKEND_PRESERVED",
                "secretValuesReturned": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        signature = b"-----BEGIN SSH SIGNATURE-----\nregression\n"
        completed = module.subprocess.CompletedProcess(
            [str(module.RECONCILER)],
            1,
            stdout=b"",
            stderr=b"",
        )
        with (
            patch.object(module.os, "geteuid", return_value=0),
            patch.object(
                module,
                "_read_input",
                return_value=(scope, "ghs_ephemeral_runtime_token_abcdefghijklmnopqrstuvwxyz", "OuroborosCollective"),
            ),
            patch.object(
                module,
                "_backend_env_file",
                return_value=Path("/run/secrets/sovereign-backend.env"),
            ),
            patch.object(module, "_write_token"),
            patch.object(module, "_prepare_registry_auth"),
            patch.object(module.subprocess, "run", return_value=completed),
            patch.object(module, "_read_status", return_value=receipt),
            patch.object(module, "_sign", return_value=signature),
            patch.object(module, "_emit") as emit,
            patch.object(module, "_cleanup_registry_auth"),
        ):
            exit_code = module.main()

        self.assertEqual(exit_code, 0)
        emit.assert_called_once_with(scope, receipt, signature)

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

    def test_backend_env_pointer_uses_only_managed_allowlisted_path_without_reading_secret_contents(self) -> None:
        module = _load_entrypoint()
        source = ENTRYPOINT.read_text("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "runtime.env"
            backend = root / "backend.env"
            backend.write_text("TOP_SECRET_VALUE=must-not-be-read-by-pointer-resolution\n", "utf-8")
            control.write_text(f"SOVEREIGN_BACKEND_ENV_FILE={backend}\n", "utf-8")
            os.chmod(control, 0o600)
            os.chmod(backend, 0o600)
            module.CONTROL_PLANE_ENV = control
            module.ALLOWED_BACKEND_ENV_FILES = frozenset({backend})
            with patch.object(module, "_assert_root_private", return_value=None):
                selected = module._backend_env_file()
            self.assertEqual(selected, backend)
        self.assertIn('"SOVEREIGN_BACKEND_ENV_FILE": str(backend_env_file)', source)
        self.assertIn('CONTROL_PLANE_ENV.read_text("utf-8")', source)
        self.assertNotIn('selected.read_text(', source)
        self.assertNotIn('backend_env_file.read_text(', source)

    def test_backend_env_pointer_rejects_unapproved_and_ambiguous_paths(self) -> None:
        module = _load_entrypoint()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "runtime.env"
            approved = root / "approved.env"
            unapproved = root / "unapproved.env"
            for path in (approved, unapproved):
                path.write_text("VALUE=redacted\n", "utf-8")
                os.chmod(path, 0o600)
            control.write_text("SOVEREIGN_BACKEND_ENV_FILE=/dev/null\n", "utf-8")
            os.chmod(control, 0o600)
            module.CONTROL_PLANE_ENV = control
            module.ALLOWED_BACKEND_ENV_FILES = frozenset({approved})
            with patch.object(module, "_assert_root_private", return_value=None):
                control.write_text(f"SOVEREIGN_BACKEND_ENV_FILE={unapproved}\n", "utf-8")
                with self.assertRaisesRegex(module.ReadbackError, "outside the canonical allowlist"):
                    module._backend_env_file()
                control.write_text(
                    f"SOVEREIGN_BACKEND_ENV_FILE={approved}\nSOVEREIGN_BACKEND_ENV_FILE={approved}\n",
                    "utf-8",
                )
                with self.assertRaisesRegex(module.ReadbackError, "missing or ambiguous"):
                    module._backend_env_file()

    def test_backend_env_pointer_rejects_symlink_target(self) -> None:
        module = _load_entrypoint()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "runtime.env"
            actual = root / "actual.env"
            linked = root / "linked.env"
            actual.write_text("VALUE=redacted\n", "utf-8")
            os.chmod(actual, 0o600)
            linked.symlink_to(actual)
            control.write_text(f"SOVEREIGN_BACKEND_ENV_FILE={linked}\n", "utf-8")
            os.chmod(control, 0o600)
            module.CONTROL_PLANE_ENV = control
            module.ALLOWED_BACKEND_ENV_FILES = frozenset({linked})
            with patch.object(module, "_assert_root_private", return_value=None):
                with self.assertRaisesRegex(module.ReadbackError, "not a regular file"):
                    module._backend_env_file()

    def test_control_plane_bootstrap_uses_exact_two_parent_source_lineage(self) -> None:
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
        self.assertNotIn("KNOWN_PREVIOUS_REVISION", workflow)
        self.assertNotIn("738c0ac6616b2b2fadfd554706ac678c90e80e7a", workflow)
        self.assertIn('PARENT1_REVISION="$(git rev-parse "${EXPECTED_REVISION}^")"', workflow)
        self.assertIn('PARENT2_REVISION="$(git rev-parse "${EXPECTED_REVISION}^^")"', workflow)
        self.assertIn('git cat-file -e "$PARENT1_REVISION:$READBACK_SOURCE"', workflow)
        self.assertIn('git cat-file -e "$PARENT2_REVISION:$READBACK_SOURCE"', workflow)
        self.assertIn('PARENT1_SHA256="$(git show "$PARENT1_REVISION:$READBACK_SOURCE"', workflow)
        self.assertIn('PARENT2_SHA256="$(git show "$PARENT2_REVISION:$READBACK_SOURCE"', workflow)
        self.assertIn('"$EXPECTED_PARENT1_SHA256") MATCHED_LINEAGE=parent1', workflow)
        self.assertIn('"$EXPECTED_PARENT2_SHA256") MATCHED_LINEAGE=parent2', workflow)
        self.assertIn("'allowedPredecessorDepth': 2", workflow)
        self.assertIn("receipt.get('allowedPredecessorDepth') == 2", workflow)
        self.assertNotIn("git log", workflow)
        self.assertNotIn("git rev-list", workflow)
        self.assertNotIn("for revision in", workflow)
        self.assertNotIn("while read", workflow)

    def test_bootstrap_receipt_marker_survives_realistic_ssh_wrapper_text_and_rejects_ambiguity(self) -> None:
        payload = json.dumps({"ok": True, "secretValuesReturned": False}, separators=(",", ":")).encode("utf-8")
        encoded = payload.hex()
        wrapper = (
            "======CMD======\n"
            f"out: SOVEREIGN_BOOTSTRAP_RECEIPT_HEX={encoded}\n"
            "===============================================\n"
            "✅ Successfully executed commands to all hosts.\n"
            "===============================================\n"
        )
        self.assertEqual(_receipt_markers(wrapper), [encoded])
        duplicated = wrapper + f"SOVEREIGN_BOOTSTRAP_RECEIPT_HEX={encoded}\n"
        self.assertEqual(len(_receipt_markers(duplicated)), 2)

    def test_control_plane_bootstrap_remains_container_free_and_marked_hex_receipted(self) -> None:
        workflow = BOOTSTRAP_WORKFLOW.read_text("utf-8")
        self.assertIn("UNEXPECTED_READBACK_ENTRYPOINT_HASH", workflow)
        self.assertIn("/opt/sovereign-chatgpt-tools/bin/run-coordinated-release-readback", workflow)
        self.assertIn("containersChanged': False", workflow)
        self.assertIn("servicesRestarted': False", workflow)
        self.assertIn("authorizedKeysChanged': False", workflow)
        self.assertIn("capture_stdout: true", workflow)
        self.assertIn("RECEIPT_STDOUT: ${{ steps.receipt.outputs.stdout }}", workflow)
        self.assertIn("SOVEREIGN_BOOTSTRAP_RECEIPT_HEX=", workflow)
        self.assertIn("len(matches) != 1", workflow)
        self.assertIn("raw = bytes.fromhex(encoded)", workflow)
        self.assertNotIn("RECEIPT_BASE64:", workflow)
        self.assertNotIn("source: .sovereign-release-readback-bootstrap/bootstrap-receipt.json", workflow)
        self.assertNotIn("deploy/install-on-vps.sh", workflow)
        self.assertNotIn("docker restart", workflow)
        self.assertNotIn("docker run", workflow)
        self.assertNotIn("systemctl restart", workflow)
        self.assertNotIn("packages: write", workflow)
        self.assertNotIn("deployments: write", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
