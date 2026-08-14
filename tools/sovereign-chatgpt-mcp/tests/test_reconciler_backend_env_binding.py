from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/reconcile-main-release.py"


def _load():
    spec = importlib.util.spec_from_file_location("reconciler_backend_env_binding", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReconcilerBackendEnvBindingTests(unittest.TestCase):
    def test_reconciler_exposes_canonical_control_plane_and_allowlist_constants(self) -> None:
        module = _load()
        source = SCRIPT.read_text("utf-8")
        self.assertEqual(
            module.CONTROL_PLANE_ENV,
            Path("/opt/sovereign-chatgpt-tools/runtime.env"),
        )
        self.assertEqual(
            module.BACKEND_MANAGED_ENV_FILE,
            Path("/opt/sovereign-chatgpt-tools/backend-runtime.env"),
        )
        self.assertEqual(
            module.ALLOWED_BACKEND_ENV_FILES,
            frozenset(
                {
                    Path("/run/secrets/sovereign-backend.env"),
                    Path("/opt/sovereign-backend/.env"),
                }
            ),
        )
        self.assertIn("SOVEREIGN_RELEASE_CONTROL_PLANE_ENV_FILE", source)
        self.assertIn("SOVEREIGN_BACKEND_MANAGED_ENV_FILE", source)

    def test_backend_env_pointer_uses_only_managed_allowlisted_path_without_reading_secret_contents(self) -> None:
        module = _load()
        source = SCRIPT.read_text("utf-8")
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
        self.assertIn("SOVEREIGN_BACKEND_ENV_FILE=", source)
        self.assertIn("CONTROL_PLANE_ENV.read_text(\"utf-8\")", source)
        self.assertNotIn("selected.read_text(", source)
        self.assertNotIn("backend_env_file.read_text(", source)

    def test_backend_env_pointer_rejects_unapproved_and_ambiguous_paths(self) -> None:
        module = _load()
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
                with self.assertRaisesRegex(module.ReconcileError, "outside the canonical allowlist"):
                    module._backend_env_file()
                control.write_text(
                    f"SOVEREIGN_BACKEND_ENV_FILE={approved}\nSOVEREIGN_BACKEND_ENV_FILE={approved}\n",
                    "utf-8",
                )
                with self.assertRaisesRegex(module.ReconcileError, "missing or ambiguous"):
                    module._backend_env_file()
                control.write_text("UNRELATED=value\n", "utf-8")
                with self.assertRaisesRegex(module.ReconcileError, "missing or ambiguous"):
                    module._backend_env_file()

    def test_backend_env_pointer_rejects_symlink_target(self) -> None:
        module = _load()
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
                with self.assertRaisesRegex(module.ReconcileError, "not a regular file"):
                    module._backend_env_file()

    def test_backend_deploy_environment_exports_only_resolved_path_and_canonical_repository(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "runtime.env"
            backend = root / "backend.env"
            backend.write_text("SECRET=value\n", "utf-8")
            control.write_text(f"SOVEREIGN_BACKEND_ENV_FILE={backend}\n", "utf-8")
            os.chmod(control, 0o600)
            os.chmod(backend, 0o600)
            module.CONTROL_PLANE_ENV = control
            module.ALLOWED_BACKEND_ENV_FILES = frozenset({backend})
            module.BACKEND_MANAGED_ENV_FILE = Path(root / "backend-runtime.env")
            module.BACKEND_REPOSITORY = "ghcr.io/ouroboroscollective/sovereign-backend"
            with patch.object(module, "_assert_root_private", return_value=None):
                environment = module._backend_deploy_environment()
            self.assertEqual(environment["SOVEREIGN_BACKEND_ENV_FILE"], str(backend))
            self.assertEqual(
                environment["SOVEREIGN_BACKEND_MANAGED_ENV_FILE"],
                str(root / "backend-runtime.env"),
            )
            self.assertEqual(
                environment["SOVEREIGN_BACKEND_IMAGE_REPOSITORY"],
                "ghcr.io/ouroboroscollective/sovereign-backend",
            )
            self.assertIn("PATH", environment)
            # The bounded environment must not inherit ambient reconciler state.
            self.assertNotIn("SOVEREIGN_EXPECTED_REVISION", environment)
            self.assertNotIn("SOVEREIGN_RELEASE_GITHUB_TOKEN_FILE", environment)
            # No secret values are copied into the subprocess environment.
            for value in environment.values():
                self.assertNotIn("SECRET=value", value)

    def test_deploy_and_rollback_receive_the_same_bounded_environment_transitively(self) -> None:
        module = _load()
        source = SCRIPT.read_text("utf-8")
        # The deploy block resolves the bounded environment exactly once and
        # the rollback after MCP failure reuses the same binding object.
        self.assertIn("deploy_environment = _backend_deploy_environment()", source)
        self.assertRegex(
            source,
            r"stage=\"backend_deploy\",\s*\n\s*environment=deploy_environment,",
        )
        self.assertRegex(
            source,
            r'stage="backend_rollback_after_mcp_failure",\s*\n\s*environment=deploy_environment,',
        )
        # The ambient os.environ.copy() must not be used for deploy or rollback.
        deploy_block = source.split("deploy_environment = _backend_deploy_environment()", 1)[1]
        rollback_block = deploy_block.split("stage=\"backend_rollback_after_mcp_failure\"", 1)[1]
        self.assertNotIn("os.environ.copy()", deploy_block[: rollback_block.__len__() + 1])

    def test_bounded_environment_does_not_serialize_secret_contents(self) -> None:
        source = SCRIPT.read_text("utf-8")
        self.assertNotIn("backend_env_file.read_text(", source)
        self.assertNotIn("selected.read_text(", source)
        self.assertIn("secretValuesReturned\": False", source)


if __name__ == "__main__":
    unittest.main()
