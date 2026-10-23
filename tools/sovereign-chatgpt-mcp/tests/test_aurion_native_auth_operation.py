"""Real coordinator/storage, temporary files, simulated external host adapter."""
import copy
import json
import os
import traceback
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aurion_native_auth as repair
import test_aurion_native_auth_files as file_tests


class OperationContracts(unittest.TestCase):
    def setUp(self):
        ownership = patch.object(os, "fchown", return_value=None)
        ownership.start()
        self.addCleanup(ownership.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.metadata = file_tests.FilesystemContracts.root_metadata(self, protect_test_ancestors=True)
        self.metadata.start()
        self.addCleanup(self.metadata.stop)
        self.addCleanup(self.tmp.cleanup)
        self.now = 1000
        self.snapshot = {"target": repair.TARGET, "revision": "a" * 40,
                         "containerId": "b" * 64, "imageId": "sha256:" + "c" * 64,
                         "metadataFingerprint": "d" * 64, "configurationFingerprint": "e" * 64,
                         "schemaVerified": True, "healthy": True,
                         "configuration": {"releaseEnabled": False, "stateSealKeyPresent": False,
                                           "stateSealKeyValid": False}}
        self.adapter = Mock()
        self.adapter.snapshot.side_effect = lambda revision: copy.deepcopy(self.snapshot)
        self.adapter.backup.return_value = "f" * 64
        self.adapter.readback.return_value = {k: True for k in (
            "sameImage", "sameRevision", "healthy", "releaseEnabled", "stateSealKeyPresent",
            "stateSealKeyValid", "configurationBound", "validStart200", "invalidBody400")}
        self.adapter.rollback_readback.return_value = {
            "sameImage": True, "sameRevision": True, "healthy": True, "configurationRestored": True}
        self.state = repair.NativeAuthState(self.root)
        self.runtime = repair.NativeAuthRepair(self.adapter, self.state, clock=lambda: self.now)

    def approve(self):
        plan = self.runtime.plan("a" * 40)
        return self.runtime.issue(plan["planHash"], "a" * 40)["operationId"]

    def test_plan_has_no_persistence_or_effect(self):
        plan = self.runtime.plan("a" * 40)
        self.assertTrue(plan["generateKey"])
        self.assertEqual(list(self.root.iterdir()), [])
        self.adapter.backup.assert_not_called()

    def test_wrong_target_fails_before_adapter(self):
        with self.assertRaisesRegex(repair.RepairBlocked, "TARGET_OR_REVISION_INVALID"):
            self.runtime.plan("a" * 40, target="other")
        self.adapter.snapshot.assert_not_called()

    def test_schema_mismatch_cannot_be_approved(self):
        self.snapshot["schemaVerified"] = False
        with self.assertRaisesRegex(repair.RepairBlocked, "SCHEMA_MISMATCH"):
            self.runtime.issue("a" * 64, "a" * 40)
        self.adapter.backup.assert_not_called()

    def test_expired_approval_no_effect(self):
        operation = self.approve()
        self.now += 300
        with self.assertRaisesRegex(repair.RepairBlocked, "APPROVAL_EXPIRED_OR_INVALID"):
            self.runtime.apply(operation)
        self.adapter.backup.assert_not_called()

    def test_caller_boolean_is_not_authority(self):
        with self.assertRaises(repair.RepairBlocked):
            self.runtime.apply("a" * 32, owner_approved=True)
        with self.assertRaisesRegex(repair.RepairBlocked, "APPROVAL_EXPIRED_OR_INVALID"):
            self.runtime.apply("a" * 32)
        self.adapter.backup.assert_not_called()

    def test_bound_image_container_config_metadata_drift(self):
        for key, value in (("imageId", "sha256:" + "0" * 64), ("containerId", "0" * 64),
                           ("configurationFingerprint", "0" * 64), ("metadataFingerprint", "0" * 64)):
            with self.subTest(key=key):
                operation = self.approve()
                original = self.snapshot[key]
                self.snapshot[key] = value
                with self.assertRaisesRegex(repair.RepairBlocked, "PLAN_DRIFT"):
                    self.runtime.apply(operation)
                self.snapshot[key] = original
        self.adapter.backup.assert_not_called()

    def test_consumed_before_first_effect(self):
        operation = self.approve()
        def backup(plan, op):
            self.assertIsNone(self.state.read("approval", op))
            self.assertEqual(self.state.read("receipt", op)["phase"], "PREPARED")
            return "f" * 64
        self.adapter.backup.side_effect = backup
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "VERIFIED")
        self.assertEqual(result["deviceFlow"], "UNVERIFIED")

    def test_replay_is_readback_only(self):
        operation = self.approve()
        self.runtime.apply(operation)
        self.runtime.apply(operation)
        self.adapter.apply_configuration.assert_called_once()
        self.adapter.recreate_same_image.assert_called_once()

    def test_worker_crash_blocks_other_action_after_restart(self):
        first, second = self.approve(), self.approve()
        self.adapter.recreate_same_image.side_effect = TimeoutError("synthetic adapter outage")
        self.adapter.readback.side_effect = TimeoutError("synthetic adapter outage")
        with self.assertRaisesRegex(repair.RepairBlocked, "HOST_ADAPTER_FAILED"):
            self.runtime.apply(first)
        self.adapter.readback.side_effect = None
        restarted = repair.NativeAuthRepair(self.adapter, repair.NativeAuthState(self.root), clock=lambda: self.now)
        result = restarted.apply(first)
        self.assertEqual(result["phase"], "CONFIGURATION_WRITTEN")
        with self.assertRaisesRegex(repair.RepairBlocked, "PREVIOUS_OUTCOME_UNCERTAIN"):
            restarted.apply(second)
        self.adapter.apply_configuration.assert_called_once()
        self.adapter.recreate_same_image.assert_called_once()

    def test_failure_between_active_intent_and_receipt_has_no_effect_recovery(self):
        operation = self.approve()
        original = self.state.create
        def fail_receipt(kind, op, record):
            if kind == "receipt":
                raise OSError("synthetic interrupted receipt write")
            return original(kind, op, record)
        with patch.object(self.state, "create", side_effect=fail_receipt):
            with self.assertRaisesRegex(repair.RepairBlocked, "NATIVE_AUTH_OPERATION_UNAVAILABLE"):
                self.runtime.apply(operation)
        restarted = repair.NativeAuthRepair(self.adapter, repair.NativeAuthState(self.root), clock=lambda: self.now)
        self.assertEqual(restarted.readback(operation)["phase"], "NO_EFFECT_PREPARATION_INCOMPLETE")
        self.assertTrue(restarted.apply(operation)["noTargetEffects"])
        self.adapter.backup.assert_not_called()
        plan = restarted.plan("a" * 40)
        new = restarted.issue(plan["planHash"], "a" * 40)
        self.assertNotEqual(new["operationId"], operation)
        self.assertEqual(self.state.read("receipt", operation)["phase"], "NO_EFFECT_PREPARATION_INCOMPLETE")
        self.assertIsNone(self.state.read("approval", operation))
        self.adapter.apply_configuration.assert_not_called()

    def test_secret_adapter_exceptions_have_fixed_public_traceback(self):
        for method in ("snapshot", "backup", "apply_configuration", "readback"):
            with self.subTest(method=method):
                # Each case uses its own independent operation state directory.
                marker = "SYNTHETIC_PRIVATE_EXCEPTION_" + method
                if method == "snapshot":
                    call = lambda: self.runtime.plan("a" * 40)
                else:
                    operation = self.approve()
                    call = lambda: self.runtime.apply(operation)
                old = getattr(self.adapter, method).side_effect
                getattr(self.adapter, method).side_effect = ValueError(marker)
                try:
                    call()
                except repair.RepairBlocked as exc:
                    self.assertEqual(str(exc), "HOST_ADAPTER_FAILED")
                    self.assertNotIn(marker, "".join(traceback.format_exception(exc)))
                else:
                    self.fail("adapter exception accepted")
                getattr(self.adapter, method).side_effect = old
                for path in self.root.glob("*.json"):
                    self.assertNotIn(marker, path.read_text())
                # Remove only test fixtures between independent failure cases.
                for path in self.root.iterdir():
                    path.unlink()

    def test_unsafe_ancestor_rejected(self):
        self.metadata.stop()
        with file_tests.FilesystemContracts.root_metadata(self):
            with self.assertRaisesRegex(repair.RepairBlocked, "STATE_ANCESTOR_PROTECTION"):
                with self.state.directory():
                    self.fail("writable /tmp ancestor admitted")
        self.metadata.start()

    def test_locked_state_uses_pinned_directory_after_path_swap(self):
        operation = self.approve()
        displaced = self.root.with_name(self.root.name + "-displaced")
        try:
            with self.state.lock():
                self.root.rename(displaced)
                self.root.mkdir(mode=0o700)
                # A root-level filesystem substitution is simulated here;
                # every state operation must still address the original inode.
                self.assertIsNotNone(self.state.read("approval", operation))
                self.state.create("receipt", operation, {"phase": "synthetic"})
                self.assertEqual(list(self.root.iterdir()), [])
                self.assertTrue((displaced / self.state.name("receipt", operation)).exists())
        finally:
            self.root.rmdir()
            displaced.rename(self.root)

    def test_concurrent_lock_is_denied(self):
        operation = self.approve()
        with self.state.lock():
            with self.assertRaisesRegex(repair.RepairBlocked, "CONCURRENT_OPERATION"):
                self.runtime.apply(operation)
        self.adapter.backup.assert_not_called()

    def test_same_image_failure_is_not_success_or_automatic_rollback(self):
        operation = self.approve()
        self.adapter.readback.return_value["sameImage"] = False
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "APPLIED_UNVERIFIED")
        self.adapter.rollback.assert_not_called()

    def test_rollback_requires_independent_restore_readback(self):
        operation = self.approve()
        self.adapter.readback.return_value["healthy"] = False
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "ROLLED_BACK")
        self.adapter.rollback.assert_called_once()
        self.adapter.rollback_readback.assert_called_once()

    def test_failed_rollback_keeps_mutations_blocked(self):
        operation, second = self.approve(), self.approve()
        self.adapter.readback.return_value["healthy"] = False
        self.adapter.rollback_readback.return_value["configurationRestored"] = False
        self.assertEqual(self.runtime.apply(operation)["phase"], "ROLLBACK_UNVERIFIED")
        with self.assertRaisesRegex(repair.RepairBlocked, "PREVIOUS_OUTCOME_UNCERTAIN"):
            self.runtime.apply(second)

    def test_untrusted_readback_fields_are_removed(self):
        operation = self.approve()
        marker = "synthetic-private-output"
        self.adapter.readback.return_value.update(cookies=marker, token=marker, body=marker)
        result = self.runtime.apply(operation)
        self.assertNotIn(marker, json.dumps(result))
        for record in self.root.glob("*.json"):
            self.assertNotIn(marker, record.read_text())

    def test_untrusted_backup_identity_not_persisted(self):
        operation = self.approve()
        marker = "synthetic-private-output"
        self.adapter.backup.return_value = marker
        with self.assertRaisesRegex(repair.RepairBlocked, "BACKUP_IDENTITY_INVALID"):
            self.runtime.apply(operation)
        for record in self.root.glob("*.json"):
            self.assertNotIn(marker, record.read_text())
        self.adapter.apply_configuration.assert_not_called()


if __name__ == "__main__":
    unittest.main()
