"""Negative and successful adapter-contract tests; NOT host sandbox evidence."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

# Import the actual deployment module used by the backend CI/runtime; do not
# depend on `backend` being importable inside the sovereign-backend pytest job.
ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND_ROOT))
from agent_runtime.openshell_preflight import (
    OpenShellPreflightError,
    prove_policy,
    sandbox_canary,
)

DOMAINS = ["filesystem", "network_l4", "network_rest", "process", "landlock"]


class OpenShellPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pinned_policy = Path(__file__).resolve().parents[3] / "config/openshell/agent-readonly-policy.yaml"
        self.policy = Path(self.temp.name) / "policy.yaml"
        self.boundary = Path(self.temp.name) / "boundary.yaml"
        self.policy.write_text("version: 1\nnetwork_policies: {}\n", encoding="utf-8")
        self.boundary.write_text("version: 1\nnetwork_policies: {}\n", encoding="utf-8")
        import hashlib
        self.digest = hashlib.sha256(self.policy.read_bytes()).hexdigest()
        self.boundary_digest = hashlib.sha256(self.boundary.read_bytes()).hexdigest()

    def _runner(self, argv, **kwargs):
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, stdout="openshell 0.1.5\n", stderr="")
        if argv[0] == "openshell-prover":
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"result": "within_boundary", "coverage": {"domains": DOMAINS}}), stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="OPENSHELL_EGRESS_DENIED_BY_PROXY\n", stderr="")

    def test_policy_check_passes_complete_coverage(self):
        receipt = prove_policy(self.policy, self.boundary, self.digest, self.boundary_digest, "0.1.5", run=self._runner)
        self.assertEqual(receipt["result"], "within_boundary")
        self.assertEqual(receipt["coverage"], sorted(DOMAINS))
        self.assertEqual(receipt["policy_sha256"], self.digest)

    def test_hash_mismatch_fails_before_external_execution(self):
        with patch("agent_runtime.openshell_preflight.subprocess.run") as runner:
            with self.assertRaises(OpenShellPreflightError):
                prove_policy(self.policy, self.boundary, "0"*64, self.boundary_digest, "0.1.5")
            runner.assert_not_called()

    def test_symlink_policy_rejected(self):
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.policy)
        with self.assertRaises(OpenShellPreflightError):
            prove_policy(link, self.boundary, self.digest, self.boundary_digest, "0.1.5", run=self._runner)

    def test_missing_binary_is_blocker(self):
        def no_binary(*args, **kwargs):
            raise FileNotFoundError("no openshell")
        with self.assertRaises(OpenShellPreflightError):
            prove_policy(self.policy, self.boundary, self.digest, self.boundary_digest, "0.1.5", run=no_binary)

    def test_wrong_binary_version_is_blocker(self):
        with self.assertRaises(OpenShellPreflightError):
            prove_policy(self.policy, self.boundary, self.digest, self.boundary_digest, "0.1.4", run=self._runner)

    def test_unsupported_and_missing_domains_are_blockers(self):
        for result, domains, code in (("unsupported", DOMAINS, 3), ("within_boundary", ["filesystem"], 0), ("exceeds_boundary", DOMAINS, 1)):
            def runner(argv, **kwargs):
                if argv[-1] == "--version":
                    return self._runner(argv, **kwargs)
                return subprocess.CompletedProcess(argv, code, stdout=json.dumps({"result": result, "coverage": {"domains": domains}}), stderr="")
            with self.subTest(result=result, domains=domains), self.assertRaises(OpenShellPreflightError):
                prove_policy(self.policy, self.boundary, self.digest, self.boundary_digest, "0.1.5", run=runner)

    def test_non_object_json_is_blocked(self):
        def invalid(argv, **kwargs):
            if argv[-1] == "--version":
                return self._runner(argv, **kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")
        with self.assertRaises(OpenShellPreflightError):
            prove_policy(self.policy, self.boundary, self.digest, self.boundary_digest, "0.1.5", run=invalid)

    def test_invalid_json_or_prover_timeout_blocks(self):
        def broken(argv, **kwargs):
            if argv[-1] == "--version":
                return self._runner(argv, **kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout="not json", stderr="")
        with self.assertRaises(OpenShellPreflightError):
            prove_policy(self.policy, self.boundary, self.digest, self.boundary_digest, "0.1.5", run=broken)
        def timed_out(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], 10)
        with self.assertRaises(OpenShellPreflightError):
            prove_policy(self.policy, self.boundary, self.digest, self.boundary_digest, "0.1.5", run=timed_out)

    def test_pinned_policy_and_mirror_have_exact_checked_in_bytes(self):
        from agent_runtime.openshell_preflight import EXPECTED_POLICY_SHA256, EXPECTED_BOUNDARY_SHA256
        import hashlib
        root = Path(__file__).resolve().parents[3]
        self.assertEqual(hashlib.sha256(self.pinned_policy.read_bytes()).hexdigest(), EXPECTED_POLICY_SHA256)
        self.assertEqual(hashlib.sha256((root / "config/openshell/agent-readonly-boundary.yaml").read_bytes()).hexdigest(), EXPECTED_BOUNDARY_SHA256)
        self.assertEqual((root / "backend/agent_runtime/openshell_preflight.py").read_bytes(), (root / "scripts/sovereign-backend/agent_runtime/openshell_preflight.py").read_bytes())

    def test_canary_only_accepts_explicit_proxy_denial(self):
        for stdout, exit_code in (("OPENSHELL_EGRESS_DENIED_BY_PROXY", 1), ("sandbox ready", 0), ("", 0)):
            def fake(argv, **kwargs):
                return subprocess.CompletedProcess(argv, exit_code, stdout=stdout, stderr="")
            with self.subTest(stdout=stdout, exit_code=exit_code), self.assertRaises(OpenShellPreflightError):
                sandbox_canary(self.pinned_policy, run=fake)

    def test_canary_arguments_never_include_shell_user_input(self):
        args = []
        def runner(argv, **kwargs):
            args.extend(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="OPENSHELL_EGRESS_DENIED_BY_PROXY", stderr="")
        receipt = sandbox_canary(self.pinned_policy, run=runner)
        self.assertEqual(receipt["result"], "sandbox_canary_completed")
        self.assertIn("--no-auto-providers", args)
        self.assertIn("--no-keep", args)
        self.assertIn("--policy", args)
        self.assertNotIn("--privileged", args)
        self.assertNotIn("--gpu", args)


if __name__ == "__main__":
    unittest.main()
